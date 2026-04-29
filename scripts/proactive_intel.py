#!/usr/bin/env python
"""Proactive intelligence monitor for Nanobot.

Reads configured RSS/web sources, extracts lightweight structured signals, and
writes JSON/Markdown reports. This is deliberately local-first and dependency
light so it remains usable when MCP/web tools are unstable.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OMEGA_ROOT = Path(r"C:\AI\nanobot-omega")
WORKSPACE = OMEGA_ROOT / "workspace"
CONFIG = WORKSPACE / "proactive_sources.json"
STATE = OMEGA_ROOT / "state" / "proactive_intel_state.json"
REPORTS = WORKSPACE / "proactive_reports"
OBSIDIAN_VAULT = Path(r"C:\Users\user\Mon Drive\DriveSyncFiles\ARCHITECTE_SYSTEM")
OBSIDIAN_OUT = OBSIDIAN_VAULT / "99_Système" / "Nanobot" / "Veille"

DEFAULT_CONFIG = {
    "sources": [
        {
            "name": "Nanobot Google Drive changes",
            "type": "web",
            "url": "https://drive.google.com",
            "enabled": False,
            "keywords": ["nanobot", "obsidian", "drive"],
            "opportunity_keywords": ["gratuit", "opportunite", "urgent", "nouveau"],
            "threat_keywords": ["erreur", "expire", "bloque", "supprime"],
        }
    ]
}

PRICE_RE = re.compile(r"(?:(?:€|eur)\s*)?(\d{1,6}(?:[,.]\d{1,2})?)\s*(?:€|eur)?", re.I)
DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/20\d{2})\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d .-]{7,}\d)")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def init_config() -> dict[str, Any]:
    if not CONFIG.exists():
        write_json(CONFIG, DEFAULT_CONFIG)
    return load_json(CONFIG, DEFAULT_CONFIG)


def fetch_url(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "NanobotIntel/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(3_000_000)
        charset = resp.headers.get_content_charset() or "utf-8"
    return data.decode(charset, errors="replace")


def text_from_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def parse_rss(raw: str) -> list[dict[str, Any]]:
    root = ET.fromstring(raw)
    items = []
    for item in root.findall(".//item") or root.findall(".//{*}entry"):
        title = item.findtext("title") or item.findtext("{*}title") or "(sans titre)"
        link = item.findtext("link") or item.findtext("{*}link") or ""
        desc = item.findtext("description") or item.findtext("{*}summary") or ""
        published = item.findtext("pubDate") or item.findtext("{*}updated") or ""
        items.append({"title": text_from_html(title), "url": link, "text": text_from_html(desc), "published": published})
    return items


def parse_web(raw: str, url: str) -> list[dict[str, Any]]:
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    title = text_from_html(title_match.group(1)) if title_match else url
    text = text_from_html(raw)
    return [{"title": title, "url": url, "text": text[:8000], "published": ""}]


def fingerprint(item: dict[str, Any]) -> str:
    key = "|".join(str(item.get(k, "")) for k in ("title", "url", "published"))
    return hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()[:20]


def extract_structured(text: str) -> dict[str, Any]:
    prices = sorted(set(match.group(0).strip() for match in PRICE_RE.finditer(text)))[:10]
    dates = sorted(set(DATE_RE.findall(text)))[:10]
    emails = sorted(set(EMAIL_RE.findall(text)))[:10]
    phones = sorted(set(PHONE_RE.findall(text)))[:10]
    return {"prices": prices, "dates": dates, "emails": emails, "phones": phones}


def score_item(item: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    haystack = " ".join([item.get("title", ""), item.get("text", "")]).lower()
    keywords = [str(k).lower() for k in source.get("keywords", [])]
    opportunities = [str(k).lower() for k in source.get("opportunity_keywords", [])]
    threats = [str(k).lower() for k in source.get("threat_keywords", [])]
    matched = [k for k in keywords if k and k in haystack]
    opp = [k for k in opportunities if k and k in haystack]
    bad = [k for k in threats if k and k in haystack]
    score = len(matched) + len(opp) * 3 + len(bad) * 2
    kind = "opportunity" if opp and len(opp) >= len(bad) else "threat" if bad else "signal"
    return {"score": score, "kind": kind, "matched_keywords": matched, "opportunities": opp, "threats": bad}


def run_monitor(limit: int = 50) -> dict[str, Any]:
    cfg = init_config()
    state = load_json(STATE, {"seen": []})
    seen = set(state.get("seen", []))
    signals = []
    errors = []

    for source in cfg.get("sources", []):
        if not source.get("enabled", True):
            continue
        try:
            raw = fetch_url(str(source["url"]))
            items = parse_rss(raw) if source.get("type") == "rss" else parse_web(raw, str(source["url"]))
            for item in items[:limit]:
                item["source"] = source.get("name")
                item["fingerprint"] = fingerprint(item)
                if item["fingerprint"] in seen:
                    continue
                score = score_item(item, source)
                if score["score"] <= 0:
                    continue
                item.update(score)
                item["structured"] = extract_structured(" ".join([item.get("title", ""), item.get("text", "")]))
                signals.append(item)
                seen.add(item["fingerprint"])
        except Exception as exc:
            errors.append({"source": source.get("name"), "url": source.get("url"), "error": str(exc)})

    state["seen"] = sorted(seen)[-5000:]
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    write_json(STATE, state)

    signals.sort(key=lambda row: row.get("score", 0), reverse=True)
    report = {
        "ok": not errors,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "signal_count": len(signals),
        "signals": signals[:limit],
        "errors": errors,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = REPORTS / f"proactive_intel_{stamp}.json"
    write_json(report_path, report)
    report["report_path"] = str(report_path)
    write_obsidian_report(report)
    return report


def write_obsidian_report(report: dict[str, Any]) -> None:
    if not OBSIDIAN_VAULT.exists():
        return
    OBSIDIAN_OUT.mkdir(parents=True, exist_ok=True)
    path = OBSIDIAN_OUT / f"Veille_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.md"
    lines = [
        "---",
        'title: "Veille proactive Nanobot"',
        'type: "veille"',
        'source: "nanobot-proactive-intel"',
        "tags:",
        '  - "nanobot"',
        '  - "veille"',
        '  - "opportunites"',
        "---",
        "",
        "# Veille proactive Nanobot",
        "",
        f"- Signaux: {report.get('signal_count', 0)}",
        f"- Genere: {report.get('generated_at')}",
        "",
        "## Signaux",
    ]
    for item in report.get("signals", [])[:20]:
        lines.extend([
            "",
            f"### {item.get('title')}",
            f"- Type: {item.get('kind')}",
            f"- Score: {item.get('score')}",
            f"- Source: {item.get('source')}",
            f"- URL: {item.get('url')}",
            f"- Mots: {', '.join(item.get('matched_keywords', [])) or '-'}",
            f"- Prix: {', '.join(item.get('structured', {}).get('prices', [])) or '-'}",
            f"- Dates: {', '.join(item.get('structured', {}).get('dates', [])) or '-'}",
        ])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Veille proactive Nanobot.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    if args.command == "init":
        print(json.dumps({"ok": True, "config": str(CONFIG), "data": init_config()}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        print(json.dumps(run_monitor(limit=args.limit), ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
