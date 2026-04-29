#!/usr/bin/env python
"""
fast-scrape.py — Extracteur de Contenu Pur (HTML -> Markdown)

Extrait le contenu textuel utile d'une page web en ignorant :
- Publicites, trackers, scripts
- Navigation, footers, sidebars
- Balises de style et metadata inutiles

Optimise pour minimiser la consommation de tokens quand le contenu
est injecte dans un prompt LLM.

USAGE (CLI) :
    python fast-scrape.py <URL>
    python fast-scrape.py <URL> --max-chars 5000
    python fast-scrape.py <URL> --raw          # HTML brut sans conversion MD
    python fast-scrape.py <fichier.html>       # Depuis un fichier local

USAGE (importable) :
    from automation_macros.fast_scrape import scrape_url, html_to_markdown

    result = scrape_url("https://example.com")
    print(result["markdown"])   # Contenu Markdown propre
    print(result["title"])      # Titre de la page
    print(result["word_count"]) # Nombre de mots

USAGE (depuis Gemini exec) :
    exec("python C:\\AI\\nanobot-omega\\automation-macros\\fast-scrape.py https://example.com")
"""
from __future__ import annotations

import html
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─── Tags a supprimer completement (contenu inclus) ───
STRIP_TAGS = {
    "script", "style", "noscript", "svg", "canvas", "iframe",
    "object", "embed", "applet", "video", "audio", "source",
    "nav", "footer", "header", "aside", "form",
    "figure",  # souvent des pubs/images
}

# ─── Selecteurs de bruit (classes/ids typiques de pubs/trackers) ───
NOISE_PATTERNS = [
    r'class="[^"]*(?:ad-|ads-|advert|banner|sponsor|promo|social-share|share-bar|cookie|gdpr|consent|popup|modal|overlay|sidebar|widget|newsletter|signup|subscribe)[^"]*"',
    r'id="[^"]*(?:ad-|ads-|advert|banner|sponsor|cookie|consent|popup|modal|sidebar|newsletter)[^"]*"',
    r'role="(?:banner|complementary|navigation|contentinfo)"',
    r'data-ad[^=]*=',
    r'aria-hidden="true"',
]

# ─── User-Agent pour eviter les blocages ───
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def fetch_html(url_or_path: str, timeout: int = 15) -> tuple[str, str]:
    """Telecharge le HTML brut. Retourne (html, url_finale)."""
    path = Path(url_or_path)
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8", errors="replace"), str(path)

    req = urllib.request.Request(url_or_path, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        raw = resp.read()
        return raw.decode(charset, errors="replace"), resp.url


def strip_noise(html_content: str) -> str:
    """Supprime les elements de bruit du HTML."""
    content = html_content

    # 1. Supprimer les tags complets (avec contenu)
    for tag in STRIP_TAGS:
        content = re.sub(
            rf'<{tag}[\s>].*?</{tag}>',
            '', content, flags=re.DOTALL | re.IGNORECASE
        )
        # Tags auto-fermants
        content = re.sub(rf'<{tag}\s[^>]*/>', '', content, flags=re.IGNORECASE)

    # 2. Supprimer les divs qui matchent les patterns de bruit
    for pattern in NOISE_PATTERNS:
        # Supprimer les elements ouvrants matchant
        content = re.sub(
            rf'<[a-z]+\s[^>]*{pattern}[^>]*>.*?</[a-z]+>',
            '', content, flags=re.DOTALL | re.IGNORECASE
        )

    # 3. Supprimer les commentaires HTML
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)

    return content


def extract_title(html_content: str) -> str:
    """Extrait le titre de la page."""
    m = re.search(r'<title[^>]*>(.*?)</title>', html_content, re.DOTALL | re.IGNORECASE)
    if m:
        return html.unescape(m.group(1)).strip()

    # Fallback : premier h1
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html_content, re.DOTALL | re.IGNORECASE)
    if m:
        return re.sub(r'<[^>]+>', '', m.group(1)).strip()

    return "Sans titre"


def extract_meta_description(html_content: str) -> str:
    """Extrait la meta description."""
    m = re.search(
        r'<meta\s[^>]*name=["\']description["\']\s[^>]*content=["\'](.*?)["\']',
        html_content, re.IGNORECASE
    )
    if m:
        return html.unescape(m.group(1)).strip()
    return ""


def html_to_markdown(html_content: str, max_chars: int = 0) -> str:
    """Convertit du HTML nettoye en Markdown lisible."""
    content = html_content

    # Convertir les headings
    for level in range(1, 7):
        prefix = "#" * level
        content = re.sub(
            rf'<h{level}[^>]*>(.*?)</h{level}>',
            lambda m: f"\n\n{prefix} {_clean_inline(m.group(1))}\n\n",
            content, flags=re.DOTALL | re.IGNORECASE
        )

    # Convertir les paragraphes
    content = re.sub(r'<p[^>]*>(.*?)</p>', lambda m: f"\n\n{_clean_inline(m.group(1))}\n", content, flags=re.DOTALL | re.IGNORECASE)

    # Convertir les listes
    content = re.sub(r'<li[^>]*>(.*?)</li>', lambda m: f"\n- {_clean_inline(m.group(1))}", content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'</?[uo]l[^>]*>', '\n', content, flags=re.IGNORECASE)

    # Convertir les liens
    content = re.sub(
        r'<a\s[^>]*href=["\'](.*?)["\'][^>]*>(.*?)</a>',
        lambda m: f"[{_clean_inline(m.group(2))}]({m.group(1)})" if m.group(2).strip() else "",
        content, flags=re.DOTALL | re.IGNORECASE
    )

    # Convertir bold/italic
    content = re.sub(r'<(?:b|strong)[^>]*>(.*?)</(?:b|strong)>', r'**\1**', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<(?:i|em)[^>]*>(.*?)</(?:i|em)>', r'*\1*', content, flags=re.DOTALL | re.IGNORECASE)

    # Convertir les blockquotes
    content = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', lambda m: f"\n> {_clean_inline(m.group(1))}\n", content, flags=re.DOTALL | re.IGNORECASE)

    # Convertir les <br>
    content = re.sub(r'<br\s*/?>', '\n', content, flags=re.IGNORECASE)

    # Convertir les <hr>
    content = re.sub(r'<hr\s*/?>', '\n---\n', content, flags=re.IGNORECASE)

    # Convertir les tables (simplifie)
    content = re.sub(r'<tr[^>]*>(.*?)</tr>', lambda m: "| " + _table_row(m.group(1)) + "\n", content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'</?(?:table|thead|tbody|tfoot)[^>]*>', '\n', content, flags=re.IGNORECASE)

    # Supprimer toutes les balises restantes
    content = re.sub(r'<[^>]+>', '', content)

    # Decoder les entites HTML
    content = html.unescape(content)

    # Nettoyer les espaces multiples
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = re.sub(r'[ \t]+', ' ', content)
    content = re.sub(r' +\n', '\n', content)

    content = content.strip()

    # Tronquer si demande
    if max_chars > 0 and len(content) > max_chars:
        content = content[:max_chars]
        # Couper proprement au dernier paragraphe complet
        last_para = content.rfind('\n\n')
        if last_para > max_chars * 0.7:
            content = content[:last_para]
        content += "\n\n[... contenu tronque a {} caracteres ...]".format(max_chars)

    return content


def _clean_inline(text: str) -> str:
    """Nettoie le texte inline (supprime les tags, decode les entites)."""
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _table_row(row_html: str) -> str:
    """Convertit une ligne de tableau HTML en Markdown."""
    cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row_html, re.DOTALL | re.IGNORECASE)
    return " | ".join(_clean_inline(c) for c in cells) + " |"


def scrape_url(url_or_path: str, max_chars: int = 0, raw: bool = False) -> dict[str, Any]:
    """Scrape complet : telecharge, nettoie, convertit.

    Returns:
        {
            "title": str,
            "description": str,
            "url": str,
            "markdown": str,        # Contenu principal en Markdown
            "word_count": int,
            "char_count": int,
            "truncated": bool,
        }
    """
    html_content, final_url = fetch_html(url_or_path)

    title = extract_title(html_content)
    description = extract_meta_description(html_content)

    # Essayer d'isoler le contenu principal (article, main, content)
    main_content = html_content
    for selector in ['<article[^>]*>(.*?)</article>', '<main[^>]*>(.*?)</main>',
                     r'<div[^>]*(?:class|id)=["\'][^"\']*(?:content|article|post|entry|body)[^"\']*["\'][^>]*>(.*?)</div>']:
        m = re.search(selector, html_content, re.DOTALL | re.IGNORECASE)
        if m and len(m.group(1)) > 200:  # Au moins 200 chars pour etre un vrai contenu
            main_content = m.group(1)
            break

    cleaned = strip_noise(main_content)

    if raw:
        markdown = _clean_inline(re.sub(r'<[^>]+>', ' ', cleaned))
    else:
        markdown = html_to_markdown(cleaned, max_chars=max_chars)

    word_count = len(markdown.split())

    return {
        "title": title,
        "description": description,
        "url": final_url,
        "markdown": markdown,
        "word_count": word_count,
        "char_count": len(markdown),
        "truncated": max_chars > 0 and len(markdown) >= max_chars * 0.95,
    }


# ─── CLI ───
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fast scrape: HTML -> Markdown propre")
    parser.add_argument("url", help="URL ou fichier HTML local")
    parser.add_argument("--max-chars", type=int, default=0, help="Tronquer a N caracteres (0 = illimite)")
    parser.add_argument("--raw", action="store_true", help="Texte brut au lieu de Markdown")
    parser.add_argument("--meta-only", action="store_true", help="Afficher uniquement titre + description")

    args = parser.parse_args()

    try:
        result = scrape_url(args.url, max_chars=args.max_chars, raw=args.raw)

        if args.meta_only:
            print(f"Title: {result['title']}")
            print(f"Description: {result['description']}")
            print(f"URL: {result['url']}")
            print(f"Words: {result['word_count']}")
        else:
            print(f"# {result['title']}")
            if result['description']:
                print(f"> {result['description']}")
            print(f"\n_Source: {result['url']} | {result['word_count']} mots | {result['char_count']} chars_\n")
            print("---\n")
            print(result["markdown"])

    except urllib.error.HTTPError as e:
        print(f"ERREUR HTTP {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERREUR URL: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERREUR: {e}", file=sys.stderr)
        sys.exit(1)
