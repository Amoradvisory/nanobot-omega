#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional dependency path
    pd = None  # type: ignore[assignment]

OMEGA_ROOT = Path(r"C:\AI\nanobot-omega")
FIRE_ROOT = Path(r"C:\Users\user\Desktop\FIRE")
if str(FIRE_ROOT) not in sys.path:
    sys.path.insert(0, str(FIRE_ROOT))

from tools import excel_tools

DEFAULT_TIMEOUT = 45
OUTPUT_ROOT = Path.home() / "Desktop" / "Nanobot_Scrapes"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 NanobotScraper/1.0"
)
PRICE_RE = re.compile(
    r"(?:€|\$|£)\s?\d[\d\s.,]*|(?:gratuit|gratis|free)\b",
    flags=re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?:\+\d{1,3}\s?)?(?:\d[\s().-]?){7,}")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", flags=re.IGNORECASE)
# Reassign with explicit unicode escapes so console/file encoding cannot corrupt currency detection.
PRICE_RE = re.compile(
    r"(?:\u20ac|\$|\u00a3)\s?\d[\d\s.,]*|(?:gratuit|gratis|free)\b",
    flags=re.IGNORECASE,
)
NOISE_WORDS = {
    "cookie",
    "cookies",
    "accept",
    "privacy",
    "navigation",
    "footer",
    "header",
    "menu",
    "home",
    "skip",
    "login",
    "sign in",
    "newsletter",
}


@dataclass
class FetchResult:
    requested_url: str
    final_url: str
    method: str
    status_code: int
    html: str
    content_type: str
    title: str
    screenshot_path: str | None = None
    warnings: list[str] | None = None


def _safe_slug(value: str, default: str = "scrape") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    cleaned = cleaned.strip("._-")
    return (cleaned[:80] or default).strip("._-") or default


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _clean_multiline_text(value: str) -> str:
    lines = []
    for raw in (value or "").splitlines():
        line = _clean_text(raw)
        if line:
            lines.append(line)
    return "\n".join(lines)


def _ensure_url(url: str) -> str:
    raw = (url or "").strip().strip("<>").rstrip(").,;!?")
    if not raw:
        raise ValueError("URL vide.")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raw = "https://" + raw
    return raw


def _default_output_dir(title_hint: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return OUTPUT_ROOT / f"{stamp}_{_safe_slug(title_hint)}"


def _best_title(fetch: FetchResult, soup: BeautifulSoup) -> str:
    title = fetch.title or ""
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = _clean_text(title_tag.get_text(" ", strip=True))
    if not title:
        h1 = soup.find(["h1", "h2"])
        if h1:
            title = _clean_text(h1.get_text(" ", strip=True))
    if not title:
        title = urlparse(fetch.final_url).netloc or "scrape"
    return title


def _strip_noise(soup: BeautifulSoup) -> BeautifulSoup:
    for tag in soup.find_all(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "canvas",
            "iframe",
            "template",
            "form",
        ]
    ):
        tag.decompose()
    for tag in soup.find_all(["nav", "footer", "header", "aside"]):
        text = _clean_text(tag.get_text(" ", strip=True)).lower()
        if not text or any(word in text for word in NOISE_WORDS):
            tag.decompose()
    return soup


def _text_container(soup: BeautifulSoup) -> Tag | BeautifulSoup:
    selectors = [
        "main",
        "article",
        "[role='main']",
        "#content",
        ".content",
        ".article",
        ".post",
        ".entry-content",
    ]
    best: Tag | BeautifulSoup = soup.body or soup
    best_score = 0
    for selector in selectors:
        for candidate in soup.select(selector):
            text = _clean_text(candidate.get_text(" ", strip=True))
            score = len(text)
            if score > best_score:
                best = candidate
                best_score = score
    return best


def _extract_text_blocks(soup: BeautifulSoup) -> list[str]:
    container = _text_container(soup)
    blocks: list[str] = []
    seen: set[str] = set()
    for tag in container.find_all(["h1", "h2", "h3", "p", "li", "blockquote"]):
        text = _clean_text(tag.get_text(" ", strip=True))
        if len(text) < 20:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        blocks.append(text)
        if len(blocks) >= 180:
            break
    return blocks


def _extract_meta(soup: BeautifulSoup, final_url: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for name in ("description", "keywords", "author"):
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            meta[name] = _clean_text(str(tag["content"]))
    for prop in ("og:title", "og:description", "og:type", "og:site_name"):
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            meta[prop] = _clean_text(str(tag["content"]))
    canonical = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
    if canonical and canonical.get("href"):
        meta["canonical"] = urljoin(final_url, str(canonical["href"]))
    return meta


def _link_kind(base_url: str, href: str) -> str:
    base = urlparse(base_url)
    target = urlparse(href)
    if not target.netloc or target.netloc == base.netloc:
        return "internal"
    return "external"


def _extract_links(soup: BeautifulSoup, base_url: str, limit: int = 120) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = _clean_text(str(anchor.get("href") or ""))
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        text = _clean_text(anchor.get_text(" ", strip=True))
        if len(text) < 2:
            continue
        seen.add(absolute)
        links.append(
            {
                "text": text[:180],
                "href": absolute,
                "kind": _link_kind(base_url, absolute),
            }
        )
        if len(links) >= limit:
            break
    return links


def _rows_from_table_tag(table: Tag) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        row = [_clean_text(cell.get_text(" ", strip=True)) for cell in cells]
        if any(row):
            rows.append(row)
    return rows


def _rectangularize(rows: list[list[str]]) -> list[list[str]]:
    width = max((len(row) for row in rows), default=0)
    return [row + [""] * (width - len(row)) for row in rows]


def _table_title(index: int, table: Tag | None = None) -> str:
    if table is not None:
        caption = table.find("caption")
        if caption:
            text = _clean_text(caption.get_text(" ", strip=True))
            if text:
                return text[:40]
    return f"Table {index}"


def _extract_tables(html: str, soup: BeautifulSoup) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()

    if pd is not None:
        try:
            frames = pd.read_html(StringIO(html))
        except Exception:
            frames = []
        for index, frame in enumerate(frames, start=1):
            frame = frame.fillna("")
            headers = [str(value) if str(value).strip() else f"Column {i}" for i, value in enumerate(frame.columns, start=1)]
            rows = [headers]
            for values in frame.itertuples(index=False):
                rows.append([_clean_text(str(value)) for value in values])
            rows = _rectangularize(rows)
            signature = json.dumps(rows[:6], ensure_ascii=False)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            tables.append(
                {
                    "name": f"Table {index}",
                    "headers": rows[0] if rows else [],
                    "rows": rows[1:] if len(rows) > 1 else [],
                }
            )

    for index, table in enumerate(soup.find_all("table"), start=1):
        rows = _rows_from_table_tag(table)
        if len(rows) < 2:
            continue
        rows = _rectangularize(rows)
        signature = json.dumps(rows[:6], ensure_ascii=False)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        headers = rows[0]
        tables.append(
            {
                "name": _table_title(index, table),
                "headers": headers,
                "rows": rows[1:],
            }
        )
    return tables


def _item_title(node: Tag) -> str:
    preferred_selectors = (
        ".text",
        ".title",
        ".name",
        ".product_pod h3 a",
        "[itemprop='name']",
        "[data-testid*='title']",
    )
    for selector in preferred_selectors:
        tag = node.select_one(selector)
        if tag:
            text = _clean_text(tag.get_text(" ", strip=True) or tag.get("alt") or "")
            if len(text) >= 3:
                return text
    image_tag = node.find("img", alt=True)
    if image_tag and image_tag.get("alt"):
        text = _clean_text(str(image_tag.get("alt")))
        if len(text) >= 3:
            return text
    for selector in ("h1", "h2", "h3", "h4", "h5", "h6", "a", "strong", "b"):
        tag = node.find(selector)
        if tag:
            text = _clean_text(tag.get_text(" ", strip=True))
            if len(text) >= 3:
                return text
    return ""


def _item_author(node: Tag) -> str:
    for selector in (".author", "[itemprop='author']", "[class*='author']"):
        tag = node.select_one(selector)
        if tag:
            text = _clean_text(tag.get_text(" ", strip=True))
            if len(text) >= 2:
                return text
    return ""


def _item_summary(node: Tag, title: str) -> str:
    candidates: list[str] = []
    for selector in ("p", "blockquote", "div", "span", "li"):
        for tag in node.find_all(selector, recursive=True):
            text = _clean_text(tag.get_text(" ", strip=True))
            if len(text) < 20 or text == title:
                continue
            if title and title in text and len(text) <= len(title) + 10:
                continue
            candidates.append(text)
        if candidates:
            break
    summary = candidates[0] if candidates else ""
    if len(summary) > 260:
        summary = summary[:257].rstrip() + "..."
    return summary


def _item_secondary_text(node: Tag, title: str, summary: str) -> str:
    raw = _clean_text(node.get_text(" ", strip=True))
    if title:
        raw = raw.replace(title, "", 1).strip(" -|,")
    if summary and summary in raw:
        raw = raw.replace(summary, "", 1).strip(" -|,")
    raw = _clean_text(raw)
    if len(raw) > 180:
        raw = raw[:177].rstrip() + "..."
    return raw


def _extract_repeated_items(soup: BeautifulSoup, base_url: str, limit: int = 80) -> list[dict[str, str]]:
    best_items: list[dict[str, str]] = []
    best_score = 0
    parent_tags = ["main", "section", "div", "ul", "ol", "body"]

    for parent in soup.find_all(parent_tags):
        children = [child for child in parent.find_all(recursive=False) if isinstance(child, Tag)]
        if len(children) < 3:
            continue
        groups: dict[str, list[Tag]] = {}
        for child in children:
            groups.setdefault(child.name, []).append(child)
        for tag_name, group in groups.items():
            if len(group) < 3 or len(group) > 80 or tag_name in {"script", "style", "nav"}:
                continue
            extracted: list[dict[str, str]] = []
            titles: set[str] = set()
            for child in group:
                title = _item_title(child)
                author = _item_author(child)
                href_tag = child.find("a", href=True)
                href = urljoin(base_url, str(href_tag["href"])) if href_tag and href_tag.get("href") else ""
                image_tag = child.find("img", src=True)
                image = urljoin(base_url, str(image_tag["src"])) if image_tag and image_tag.get("src") else ""
                raw_text = _clean_text(child.get_text(" ", strip=True))
                summary = _item_summary(child, title)
                if not summary and author:
                    summary = author
                price_match = PRICE_RE.search(raw_text)
                price = _clean_text(price_match.group(0)) if price_match else ""
                secondary = _item_secondary_text(child, title, summary)
                if not title and not summary:
                    continue
                if len(raw_text) < 20:
                    continue
                if title:
                    titles.add(title.lower())
                extracted.append(
                    {
                        "title": title[:180],
                        "summary": summary,
                        "author": author,
                        "price": price,
                        "href": href,
                        "image": image,
                        "details": secondary,
                    }
                )
            if len(extracted) < 3:
                continue
            avg_text = sum(len((item.get("summary") or "") + (item.get("details") or "")) for item in extracted) / max(len(extracted), 1)
            signal_score = (
                sum(1 for item in extracted if item.get("href"))
                + sum(1 for item in extracted if item.get("price"))
                + sum(1 for item in extracted if item.get("author"))
            )
            long_titles = sum(1 for item in extracted if len(item.get("title") or "") >= 16)
            score = len(extracted) * 3 + len(titles) + int(avg_text / 30) + signal_score + long_titles
            if score > best_score:
                best_score = score
                best_items = extracted[:limit]

    return best_items


def _extract_json_ld(soup: BeautifulSoup) -> list[Any]:
    payloads: list[Any] = []
    for tag in soup.find_all("script", attrs={"type": lambda value: value and "ld+json" in value.lower()}):
        raw = (tag.string or tag.get_text() or "").strip()
        if not raw:
            continue
        try:
            payloads.append(json.loads(raw))
        except Exception:
            continue
        if len(payloads) >= 12:
            break
    return payloads


def _extract_contacts(text: str) -> dict[str, list[str]]:
    emails = sorted(set(EMAIL_RE.findall(text)))[:20]
    phones = sorted({_clean_text(match) for match in PHONE_RE.findall(text) if len(re.sub(r"\D", "", match)) >= 8})[:20]
    return {"emails": emails, "phones": phones}


def _looks_js_heavy(fetch: FetchResult, text_blocks: list[str], tables: list[dict[str, Any]], items: list[dict[str, str]]) -> bool:
    html_lower = fetch.html.lower()
    markers = (
        "enable javascript",
        "please enable javascript",
        "turn javascript on",
        "__next_data__",
        "__nuxt",
        "application/ld+json",
    )
    if any(marker in html_lower for marker in markers) and len(text_blocks) < 8:
        return True
    if len(text_blocks) < 6 and not tables and not items and fetch.html.count("<script") >= 8:
        return True
    if len(text_blocks) < 8 and len("\n".join(text_blocks)) < 180 and not tables and len(items) < 3:
        return True
    return False


def _requests_fetch(url: str, timeout: int) -> FetchResult:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8,nl;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    )
    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    title_match = re.search(r"<title[^>]*>(.*?)</title>", response.text, flags=re.IGNORECASE | re.DOTALL)
    title = _clean_text(title_match.group(1)) if title_match else ""
    return FetchResult(
        requested_url=url,
        final_url=response.url,
        method="requests",
        status_code=response.status_code,
        html=response.text,
        content_type=response.headers.get("content-type", ""),
        title=title,
        warnings=[],
    )


def _chrome_path() -> str | None:
    candidates = [
        r"C:\Users\user\AppData\Local\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Users\user\AppData\Local\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _playwright_fetch(url: str, timeout: int, screenshot_path: Path | None = None) -> FetchResult:
    from playwright.sync_api import sync_playwright

    timeout_ms = max(timeout, 10) * 1000
    warnings: list[str] = []
    final_url = url
    status_code = 200
    html = ""
    content_type = ""
    title = ""
    with sync_playwright() as playwright:
        executable_path = _chrome_path()
        browser = None
        try:
            launch_kwargs: dict[str, Any] = {"headless": True}
            if executable_path:
                launch_kwargs["executable_path"] = executable_path
            browser = playwright.chromium.launch(**launch_kwargs)
        except Exception:
            browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT, viewport={"width": 1440, "height": 2200}, locale="fr-FR")
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 15000))
            except Exception:
                warnings.append("networkidle non atteint; DOM utilise tel quel")
            page.evaluate(
                """
                () => {
                  window.scrollTo(0, document.body.scrollHeight || 0);
                }
                """
            )
            page.wait_for_timeout(700)
            html = page.content()
            title = _clean_text(page.title())
            if screenshot_path is not None:
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot_path), full_page=True)
            final_url = page.url
            status_code = response.status if response is not None else 200
            content_type = ""
            if response is not None:
                try:
                    content_type = response.headers.get("content-type", "")
                except Exception:
                    content_type = ""
        finally:
            browser.close()
    return FetchResult(
        requested_url=url,
        final_url=final_url,
        method="playwright",
        status_code=status_code,
        html=html,
        content_type=content_type,
        title=title,
        screenshot_path=str(screenshot_path) if screenshot_path and screenshot_path.exists() else None,
        warnings=warnings,
    )


def _score_parse(parsed: dict[str, Any]) -> int:
    score = 0
    score += min(len(parsed.get("text_blocks", [])), 40)
    score += len(parsed.get("tables", [])) * 12
    score += len(parsed.get("repeated_items", [])) * 3
    score += min(len(parsed.get("links", [])), 50) // 4
    score += min(len(parsed.get("article_text", "")) // 300, 30)
    return score


def _parse_fetch(fetch: FetchResult) -> dict[str, Any]:
    soup = BeautifulSoup(fetch.html, "lxml")
    json_ld = _extract_json_ld(soup)
    _strip_noise(soup)
    title = _best_title(fetch, soup)
    text_blocks = _extract_text_blocks(soup)
    article_text = _clean_multiline_text("\n\n".join(text_blocks))
    tables = _extract_tables(fetch.html, soup)
    repeated_items = _extract_repeated_items(soup, fetch.final_url)
    if len(article_text) < 120 and repeated_items:
        preview_lines: list[str] = []
        for item in repeated_items[:15]:
            line = item.get("title") or item.get("summary") or ""
            author = item.get("author") or ""
            if author:
                line += f" | {author}"
            if line:
                preview_lines.append(line)
        article_text = "\n".join(preview_lines).strip() or article_text
    links = _extract_links(soup, fetch.final_url)
    meta = _extract_meta(soup, fetch.final_url)
    contacts = _extract_contacts(article_text)
    return {
        "title": title,
        "meta": meta,
        "text_blocks": text_blocks,
        "article_text": article_text,
        "tables": tables,
        "repeated_items": repeated_items,
        "links": links,
        "json_ld": json_ld,
        "contacts": contacts,
    }


def _rows_from_records(records: list[dict[str, Any]]) -> list[list[str]]:
    headers: list[str] = []
    for record in records:
        for key in record:
            if key not in headers:
                headers.append(key)
    rows = [headers]
    for record in records:
        rows.append([_clean_text(str(record.get(header, ""))) for header in headers])
    return rows


def _safe_sheet_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]+", " ", name).strip() or "Donnees"
    base = base[:31].rstrip()
    candidate = base
    index = 2
    while candidate.lower() in used:
        suffix = f" {index}"
        candidate = (base[: 31 - len(suffix)] + suffix).rstrip()
        index += 1
    used.add(candidate.lower())
    return candidate


def _build_workbook_sources(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    items = parsed.get("repeated_items") or []
    if items:
        sources.append(
            {
                "name": "Elements",
                "rows": _rows_from_records(items),
            }
        )
    for index, table in enumerate(parsed.get("tables") or [], start=1):
        headers = table.get("headers") or []
        rows = table.get("rows") or []
        if not headers and not rows:
            continue
        sheet_rows = [headers] + rows if headers else rows
        sources.append(
            {
                "name": table.get("name") or f"Table {index}",
                "rows": sheet_rows,
            }
        )
    links = parsed.get("links") or []
    if links:
        sources.append(
            {
                "name": "Liens",
                "rows": _rows_from_records(links[:200]),
            }
        )
    return sources


def _export_excel(parsed: dict[str, Any], output_path: Path, source_url: str) -> str | None:
    workbook_sources = _build_workbook_sources(parsed)
    if not workbook_sources:
        return None

    excel_tools._require_openpyxl()
    wb = excel_tools.Workbook()  # type: ignore[operator]
    if wb.active is not None:
        wb.remove(wb.active)
    analyses: list[dict[str, Any]] = []
    used_names: set[str] = set()

    for sheet in workbook_sources:
        rows = excel_tools._rectangularize([[str(cell) for cell in row] for row in sheet["rows"]])  # type: ignore[attr-defined]
        prepared = excel_tools.prepare_table(rows)
        ws = wb.create_sheet(title=_safe_sheet_name(str(sheet["name"]), used_names))
        excel_tools._write_prepared_table(ws, prepared)  # type: ignore[attr-defined]
        analyses.append(excel_tools.analyze_worksheet(ws))

    excel_tools._add_governance_sheets(wb, analyses, source_path=source_url)  # type: ignore[attr-defined]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return str(output_path)


def _markdown_report(fetch: FetchResult, parsed: dict[str, Any], artifacts: dict[str, str]) -> str:
    lines = [
        f"# {parsed['title']}",
        "",
        "## Resume",
        f"- URL demandee: {fetch.requested_url}",
        f"- URL finale: {fetch.final_url}",
        f"- Methode gagnante: {fetch.method}",
        f"- HTTP status: {fetch.status_code}",
        f"- Type de contenu: {fetch.content_type or 'inconnu'}",
        f"- Taille texte exploitable: {len(parsed.get('article_text', ''))} caracteres",
        f"- Tables detectees: {len(parsed.get('tables') or [])}",
        f"- Elements repetes detectes: {len(parsed.get('repeated_items') or [])}",
        f"- Liens retenus: {len(parsed.get('links') or [])}",
        "",
    ]

    meta = parsed.get("meta") or {}
    if meta:
        lines.extend(["## Metadonnees"])
        for key, value in meta.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

    contacts = parsed.get("contacts") or {}
    emails = contacts.get("emails") or []
    phones = contacts.get("phones") or []
    if emails or phones:
        lines.extend(["## Contacts detectes"])
        if emails:
            lines.append("- Emails: " + ", ".join(emails))
        if phones:
            lines.append("- Telephones: " + ", ".join(phones))
        lines.append("")

    items = parsed.get("repeated_items") or []
    if items:
        lines.extend(["## Apercu des elements"])
        for item in items[:12]:
            title = item.get("title") or "(sans titre)"
            summary = item.get("summary") or item.get("details") or ""
            price = item.get("price") or ""
            href = item.get("href") or ""
            bullet = f"- {title}"
            if price:
                bullet += f" | {price}"
            if href:
                bullet += f" | {href}"
            lines.append(bullet)
            if summary:
                lines.append(f"  {summary}")
        lines.append("")

    tables = parsed.get("tables") or []
    if tables:
        lines.extend(["## Tables"])
        for table in tables[:8]:
            lines.append(
                f"- {table.get('name', 'Table')} : {len(table.get('rows') or [])} lignes x "
                f"{len(table.get('headers') or [])} colonnes"
            )
        lines.append("")

    links = parsed.get("links") or []
    if links:
        lines.extend(["## Liens importants"])
        for link in links[:20]:
            lines.append(f"- [{link.get('kind')}] {link.get('text')} -> {link.get('href')}")
        lines.append("")

    article_text = parsed.get("article_text") or ""
    if article_text:
        lines.extend(["## Texte extrait", article_text[:20000]])
        lines.append("")

    if artifacts:
        lines.extend(["## Fichiers"])
        for key, value in artifacts.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def scrape_url(
    url: str,
    *,
    render_js: bool = False,
    force_excel: bool = False,
    output_dir: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    target_url = _ensure_url(url)
    request_fetch: FetchResult | None = None
    request_parsed: dict[str, Any] | None = None
    strategy_notes: list[str] = []
    request_error: str | None = None
    try:
        request_fetch = _requests_fetch(target_url, timeout)
        request_parsed = _parse_fetch(request_fetch)
    except Exception as exc:
        request_error = str(exc)
        strategy_notes.append(f"requests en echec: {exc}")

    chosen_fetch = request_fetch
    chosen_parsed = request_parsed

    if render_js or request_fetch is None or (
        request_parsed is not None
        and _looks_js_heavy(
            request_fetch,
            request_parsed["text_blocks"],
            request_parsed["tables"],
            request_parsed["repeated_items"],
        )
    ):
        strategy_notes.append("requests a juge la page potentiellement dynamique")
        screenshot = None
        try:
            rendered_fetch = _playwright_fetch(target_url, timeout, screenshot)
            rendered_parsed = _parse_fetch(rendered_fetch)
            if chosen_fetch is None or chosen_parsed is None or render_js or _score_parse(rendered_parsed) >= _score_parse(chosen_parsed):
                chosen_fetch = rendered_fetch
                chosen_parsed = rendered_parsed
                strategy_notes.append("playwright retenu comme meilleur rendu")
            else:
                strategy_notes.append("playwright lance mais requests a donne un meilleur signal")
        except Exception as exc:
            strategy_notes.append(f"playwright indisponible ou en echec: {exc}")

    if chosen_fetch is None or chosen_parsed is None:
        raise RuntimeError(request_error or "Aucune route de scraping n'a reussi.")

    title_hint = chosen_parsed.get("title") or urlparse(chosen_fetch.final_url).netloc or "scrape"
    target_dir = output_dir or _default_output_dir(title_hint)
    target_dir.mkdir(parents=True, exist_ok=True)
    base_name = _safe_slug(title_hint)

    if chosen_fetch.screenshot_path:
        old_screenshot = Path(chosen_fetch.screenshot_path)
        if old_screenshot.exists():
            new_screenshot = target_dir / f"{base_name}.png"
            if old_screenshot.resolve() != new_screenshot.resolve():
                shutil.move(str(old_screenshot), str(new_screenshot))
            chosen_fetch.screenshot_path = str(new_screenshot)

    html_path = target_dir / f"{base_name}.html"
    html_path.write_text(chosen_fetch.html, encoding="utf-8", errors="replace")

    json_path = target_dir / f"{base_name}.json"
    payload = {
        "requested_url": chosen_fetch.requested_url,
        "final_url": chosen_fetch.final_url,
        "method": chosen_fetch.method,
        "status_code": chosen_fetch.status_code,
        "content_type": chosen_fetch.content_type,
        "title": chosen_parsed.get("title"),
        "meta": chosen_parsed.get("meta"),
        "contacts": chosen_parsed.get("contacts"),
        "tables": chosen_parsed.get("tables"),
        "repeated_items": chosen_parsed.get("repeated_items"),
        "links": chosen_parsed.get("links"),
        "json_ld": chosen_parsed.get("json_ld"),
        "article_text": chosen_parsed.get("article_text"),
        "strategy_notes": strategy_notes,
        "warnings": chosen_fetch.warnings or [],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    artifacts: dict[str, str] = {
        "rapport_markdown": str(target_dir / f"{base_name}.md"),
        "json": str(json_path),
        "html": str(html_path),
    }
    if chosen_fetch.screenshot_path:
        artifacts["screenshot"] = chosen_fetch.screenshot_path

    excel_path = target_dir / f"{base_name}.xlsx"
    if force_excel or chosen_parsed.get("tables") or chosen_parsed.get("repeated_items"):
        exported = _export_excel(chosen_parsed, excel_path, chosen_fetch.final_url)
        if exported:
            artifacts["excel"] = exported

    markdown_path = Path(artifacts["rapport_markdown"])
    markdown_path.write_text(_markdown_report(chosen_fetch, chosen_parsed, artifacts), encoding="utf-8")

    return {
        "ok": True,
        "title": chosen_parsed.get("title"),
        "requested_url": chosen_fetch.requested_url,
        "final_url": chosen_fetch.final_url,
        "method": chosen_fetch.method,
        "status_code": chosen_fetch.status_code,
        "content_type": chosen_fetch.content_type,
        "text_characters": len(chosen_parsed.get("article_text") or ""),
        "tables": len(chosen_parsed.get("tables") or []),
        "repeated_items": len(chosen_parsed.get("repeated_items") or []),
        "links": len(chosen_parsed.get("links") or []),
        "output_dir": str(target_dir),
        "artifacts": artifacts,
        "strategy_notes": strategy_notes,
        "warnings": chosen_fetch.warnings or [],
    }


def _format_result(result: dict[str, Any]) -> str:
    lines = [
        "Scraping OK.",
        f"Titre: {result.get('title') or '-'}",
        f"URL finale: {result.get('final_url')}",
        f"Methode: {result.get('method')}",
        f"Texte exploitable: {result.get('text_characters')} caracteres",
        f"Tables: {result.get('tables')}",
        f"Elements repetes: {result.get('repeated_items')}",
        f"Liens: {result.get('links')}",
        f"Dossier: {result.get('output_dir')}",
    ]
    for key, value in (result.get("artifacts") or {}).items():
        lines.append(f"- {key}: {value}")
    for note in result.get("strategy_notes") or []:
        lines.append(f"- note: {note}")
    for warning in result.get("warnings") or []:
        lines.append(f"- warning: {warning}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Moteur de scraping robuste pour Nanobot.")
    sub = parser.add_subparsers(dest="command", required=True)

    scrape_cmd = sub.add_parser("scrape")
    scrape_cmd.add_argument("url")
    scrape_cmd.add_argument("--render-js", action="store_true", help="Force le rendu JS via Playwright.")
    scrape_cmd.add_argument("--force-excel", action="store_true", help="Force la creation d'un .xlsx si possible.")
    scrape_cmd.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    scrape_cmd.add_argument("--output-dir", help="Dossier cible pour les artefacts.")
    scrape_cmd.add_argument("--json-out", action="store_true", help="Imprime la reponse finale en JSON.")

    args = parser.parse_args(argv or sys.argv[1:])

    if args.command == "scrape":
        output_dir = Path(args.output_dir).expanduser() if args.output_dir else None
        result = scrape_url(
            args.url,
            render_js=bool(args.render_js),
            force_excel=bool(args.force_excel),
            output_dir=output_dir,
            timeout=int(args.timeout),
        )
        if args.json_out:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(_format_result(result))
        return 0

    print("Commande inconnue.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
