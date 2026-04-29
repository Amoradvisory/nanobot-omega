#!/usr/bin/env python
"""
youtube-control.py — Controleur YouTube Avance

Fonctions pour interagir avec YouTube via Playwright MCP :
- Bypass popups de connexion / consentement
- Extraction de metadonnees video (titre, duree, vues, chaine)
- Recherche et lecture de videos
- Gestion des playlists et suggestions

USAGE (CLI) :
    python youtube-control.py search "echecs kasparov"
    python youtube-control.py metadata "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    python youtube-control.py trending
    python youtube-control.py inject-bypass          # Genere le JS a injecter

USAGE (importable) :
    from automation_macros.youtube_control import (
        build_search_url, build_direct_url,
        extract_metadata_from_html, generate_bypass_js,
        generate_search_js, generate_player_control_js,
    )

USAGE (depuis Gemini exec) :
    exec("python C:\\AI\\nanobot-omega\\automation-macros\\youtube-control.py search echecs")
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


# ═══════════════════════════════════════════════
# URL BUILDERS
# ═══════════════════════════════════════════════

def build_search_url(query: str, sort: str = "relevance") -> str:
    """Construit une URL de recherche YouTube.

    Args:
        query: Termes de recherche
        sort: "relevance" | "date" | "views" | "rating"
    """
    params = {"search_query": query}
    sort_map = {"date": "CAI%253D", "views": "CAM%253D", "rating": "CAE%253D"}
    if sort in sort_map:
        params["sp"] = sort_map[sort]
    return f"https://www.youtube.com/results?{urllib.parse.urlencode(params)}"


def build_direct_url(video_id: str, timestamp: int = 0) -> str:
    """Construit une URL directe vers une video.

    Args:
        video_id: ID de la video (11 chars)
        timestamp: Timestamp en secondes (0 = debut)
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    if timestamp > 0:
        url += f"&t={timestamp}s"
    return url


def build_channel_url(channel_name: str) -> str:
    """URL vers une chaine YouTube."""
    return f"https://www.youtube.com/@{channel_name}/videos"


def build_trending_url(category: str = "now") -> str:
    """URL tendances YouTube.

    Args:
        category: "now" | "music" | "gaming" | "movies"
    """
    tab_map = {"music": "4gINGgt5dG1hX2NoYXJ0cw", "gaming": "4gIcGhpZ2FtaW5n",
               "movies": "4gIKGgh0cmFpbGVycw"}
    url = "https://www.youtube.com/feed/trending"
    if category in tab_map:
        url += f"?bp={tab_map[category]}"
    return url


def extract_video_id(url_or_id: str) -> str | None:
    """Extrait l'ID video depuis une URL YouTube ou un ID brut."""
    if re.match(r'^[A-Za-z0-9_-]{11}$', url_or_id):
        return url_or_id

    patterns = [
        r'(?:youtube\.com/watch\?.*v=|youtu\.be/)([A-Za-z0-9_-]{11})',
        r'youtube\.com/embed/([A-Za-z0-9_-]{11})',
        r'youtube\.com/shorts/([A-Za-z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url_or_id)
        if m:
            return m.group(1)
    return None


# ═══════════════════════════════════════════════
# METADATA EXTRACTION (from HTML/oEmbed)
# ═══════════════════════════════════════════════

def extract_metadata_from_html(html_content: str) -> dict[str, Any]:
    """Extrait les metadonnees d'une page video YouTube depuis le HTML."""
    meta = {
        "title": "", "channel": "", "duration": "",
        "views": "", "date": "", "description": "",
        "likes": "", "video_id": "", "thumbnail": "",
    }

    # Titre
    m = re.search(r'<meta\s+name="title"\s+content="(.*?)"', html_content)
    if m:
        meta["title"] = m.group(1)
    else:
        m = re.search(r'"title":\s*"(.*?)"', html_content)
        if m:
            meta["title"] = m.group(1)

    # Chaine
    m = re.search(r'"ownerChannelName":\s*"(.*?)"', html_content)
    if m:
        meta["channel"] = m.group(1)
    else:
        m = re.search(r'<link\s+itemprop="name"\s+content="(.*?)"', html_content)
        if m:
            meta["channel"] = m.group(1)

    # Duree
    m = re.search(r'"lengthSeconds":\s*"(\d+)"', html_content)
    if m:
        secs = int(m.group(1))
        mins, s = divmod(secs, 60)
        hrs, mins = divmod(mins, 60)
        meta["duration"] = f"{hrs}:{mins:02d}:{s:02d}" if hrs else f"{mins}:{s:02d}"

    # Vues
    m = re.search(r'"viewCount":\s*"(\d+)"', html_content)
    if m:
        count = int(m.group(1))
        if count >= 1_000_000:
            meta["views"] = f"{count/1_000_000:.1f}M"
        elif count >= 1_000:
            meta["views"] = f"{count/1_000:.1f}K"
        else:
            meta["views"] = str(count)

    # Date
    m = re.search(r'"publishDate":\s*"([\d-]+)"', html_content)
    if m:
        meta["date"] = m.group(1)

    # Description (premiers 500 chars)
    m = re.search(r'"shortDescription":\s*"(.*?)"', html_content)
    if m:
        desc = m.group(1).replace("\\n", "\n")[:500]
        meta["description"] = desc

    # Video ID
    m = re.search(r'"videoId":\s*"([A-Za-z0-9_-]{11})"', html_content)
    if m:
        meta["video_id"] = m.group(1)

    # Thumbnail
    vid = meta["video_id"]
    if vid:
        meta["thumbnail"] = f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"

    return meta


def get_oembed_metadata(video_id: str) -> dict[str, Any]:
    """Recupere les metadonnees via l'API oEmbed (pas de cle API requise)."""
    url = f"https://www.youtube.com/oembed?url=https://youtube.com/watch?v={video_id}&format=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════
# JAVASCRIPT GENERATORS (pour injection Playwright)
# ═══════════════════════════════════════════════

def generate_bypass_js() -> str:
    """JS pour bypasser les popups YouTube (consent, login, age-gate).

    Utilisation Playwright MCP :
        browser_evaluate expression:"<ce code JS>"
    """
    return r"""
(function ytBypass() {
    const result = { popups_dismissed: [] };

    // 1. Consent dialog (RGPD)
    const consentBtn = document.querySelector(
        'button[aria-label*="Accept"], button[aria-label*="Accepter"], ' +
        'tp-yt-paper-dialog #button, ytd-consent-bump-v2-lightbox button'
    );
    if (consentBtn) {
        consentBtn.click();
        result.popups_dismissed.push("consent");
    }

    // 2. Login popup ("Sign in" overlay)
    const dismissBtns = document.querySelectorAll(
        'yt-button-renderer.style-blue-text button, ' +
        '[id="dismiss-button"] button, ' +
        'tp-yt-paper-dialog button[aria-label="No thanks"], ' +
        'tp-yt-paper-dialog button[aria-label*="later"], ' +
        '.yt-upsell-dialog-renderer button'
    );
    for (const btn of dismissBtns) {
        const text = (btn.textContent || "").toLowerCase();
        if (/no thanks|not now|plus tard|non merci|dismiss|skip/i.test(text)) {
            btn.click();
            result.popups_dismissed.push("login-prompt");
            break;
        }
    }

    // 3. Age-gate (si present)
    const ageBtn = document.querySelector(
        'tp-yt-paper-button#confirm-button, ' +
        'button[aria-label*="confirm"], ' +
        '#reason button'
    );
    if (ageBtn && /confirm|proceed|continue/i.test(ageBtn.textContent)) {
        ageBtn.click();
        result.popups_dismissed.push("age-gate");
    }

    // 4. Mini-player fermer
    const miniClose = document.querySelector('button.ytp-miniplayer-close-button');
    if (miniClose) { miniClose.click(); result.popups_dismissed.push("miniplayer"); }

    // 5. Survey popup
    const surveyClose = document.querySelectorAll('button[aria-label="Close"], button[aria-label="Fermer"]');
    for (const btn of surveyClose) {
        if (btn.closest('.ytd-popup-container, ytd-enforcement-message-view-model')) {
            btn.click();
            result.popups_dismissed.push("survey/popup");
            break;
        }
    }

    return result;
})();
""".strip()


def generate_search_js(query: str) -> str:
    """JS pour effectuer une recherche YouTube depuis la page."""
    escaped = query.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
    return f"""
(function ytSearch() {{
    const searchInput = document.querySelector('input#search, input[name="search_query"]');
    if (!searchInput) return {{ success: false, error: "Search input not found" }};

    searchInput.focus();
    searchInput.value = "{escaped}";
    searchInput.dispatchEvent(new Event('input', {{ bubbles: true }}));

    // Soumettre le formulaire
    const form = searchInput.closest('form');
    if (form) {{
        form.submit();
        return {{ success: true, query: "{escaped}" }};
    }}

    // Fallback : touche Enter
    searchInput.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', keyCode: 13, bubbles: true }}));
    return {{ success: true, query: "{escaped}", method: "keydown" }};
}})();
""".strip()


def generate_player_control_js(action: str = "play") -> str:
    """JS pour controler le lecteur video YouTube.

    Actions: play, pause, mute, unmute, fullscreen, skip30, back10, speed2x
    """
    actions = {
        "play": "video.play(); return {action:'play'};",
        "pause": "video.pause(); return {action:'pause'};",
        "mute": "video.muted = true; return {action:'mute'};",
        "unmute": "video.muted = false; return {action:'unmute'};",
        "fullscreen": "video.requestFullscreen(); return {action:'fullscreen'};",
        "skip30": "video.currentTime += 30; return {action:'skip30', time: video.currentTime};",
        "back10": "video.currentTime -= 10; return {action:'back10', time: video.currentTime};",
        "speed2x": "video.playbackRate = 2.0; return {action:'speed2x'};",
        "speed1x": "video.playbackRate = 1.0; return {action:'speed1x'};",
        "status": """return {
            playing: !video.paused,
            currentTime: video.currentTime,
            duration: video.duration,
            volume: video.volume,
            muted: video.muted,
            speed: video.playbackRate,
            title: document.title
        };""",
    }

    code = actions.get(action, f"return {{error: 'Unknown action: {action}'}};")
    return f"""
(function ytControl() {{
    const video = document.querySelector('video');
    if (!video) return {{ error: "No video element found" }};
    {code}
}})();
""".strip()


def generate_extract_results_js() -> str:
    """JS pour extraire les resultats de recherche YouTube."""
    return r"""
(function ytExtractResults() {
    const results = [];
    const items = document.querySelectorAll('ytd-video-renderer, ytd-rich-item-renderer');

    for (const item of items) {
        if (results.length >= 10) break;

        const titleEl = item.querySelector('#video-title');
        const channelEl = item.querySelector('#channel-name a, .ytd-channel-name a');
        const viewsEl = item.querySelector('#metadata-line span:first-child');
        const durationEl = item.querySelector('badge-shape .badge-shape-wiz__text, span.ytd-thumbnail-overlay-time-status-renderer');
        const linkEl = item.querySelector('a#video-title, a#thumbnail');

        if (titleEl) {
            const href = linkEl ? linkEl.getAttribute('href') : '';
            results.push({
                title: titleEl.textContent.trim(),
                channel: channelEl ? channelEl.textContent.trim() : '',
                views: viewsEl ? viewsEl.textContent.trim() : '',
                duration: durationEl ? durationEl.textContent.trim() : '',
                url: href ? 'https://www.youtube.com' + href : '',
                videoId: href ? (href.match(/v=([A-Za-z0-9_-]{11})/) || [])[1] || '' : '',
            });
        }
    }

    return { count: results.length, results };
})();
""".strip()


# ═══════════════════════════════════════════════
# PLAYWRIGHT MCP PROCEDURE GENERATOR
# ═══════════════════════════════════════════════

def generate_procedure(action: str, **kwargs) -> list[dict[str, str]]:
    """Genere une sequence d'appels MCP Playwright pour une action YouTube.

    Args:
        action: "search", "play_video", "extract_results", "get_metadata"
        **kwargs: Parametres specifiques a l'action

    Returns:
        Liste de dicts {"tool": "...", "args": "..."} a executer sequentiellement
    """
    if action == "search":
        query = kwargs.get("query", "")
        url = build_search_url(query)
        return [
            {"tool": "browser_navigate", "args": f'url:"{url}"'},
            {"tool": "browser_evaluate", "args": f'expression:"{generate_bypass_js()}"'},
            {"tool": "browser_snapshot", "args": ""},
            {"tool": "browser_evaluate", "args": f'expression:"{generate_extract_results_js()}"'},
        ]

    elif action == "play_video":
        video_id = kwargs.get("video_id", "")
        url = build_direct_url(video_id)
        return [
            {"tool": "browser_navigate", "args": f'url:"{url}"'},
            {"tool": "browser_evaluate", "args": f'expression:"{generate_bypass_js()}"'},
            {"tool": "browser_snapshot", "args": ""},
            {"tool": "browser_evaluate", "args": f'expression:"{generate_player_control_js("play")}"'},
        ]

    elif action == "get_metadata":
        video_id = kwargs.get("video_id", "")
        oembed = get_oembed_metadata(video_id)
        return [{"result": oembed}]

    return [{"error": f"Unknown action: {action}"}]


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python youtube-control.py search <query>")
        print("  python youtube-control.py url <query>           # Juste l'URL de recherche")
        print("  python youtube-control.py metadata <url_or_id>  # Metadonnees oEmbed")
        print("  python youtube-control.py trending [category]")
        print("  python youtube-control.py inject-bypass         # JS pour bypass popups")
        print("  python youtube-control.py inject-search <query> # JS pour recherche")
        print("  python youtube-control.py inject-control <action>  # JS pour player")
        print("  python youtube-control.py inject-results        # JS extraction resultats")
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "search" or cmd == "url":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not query:
            print("Erreur: query requise", file=sys.stderr)
            sys.exit(1)
        url = build_search_url(query)
        if cmd == "url":
            print(url)
        else:
            print(f"URL: {url}")
            print(f"\nProcedure Playwright MCP :")
            for step in generate_procedure("search", query=query):
                print(f"  {step['tool']} {step.get('args', '')[:80]}")

    elif cmd == "metadata":
        target = sys.argv[2] if len(sys.argv) > 2 else ""
        vid = extract_video_id(target)
        if not vid:
            print(f"Erreur: impossible d'extraire l'ID video de: {target}", file=sys.stderr)
            sys.exit(1)
        meta = get_oembed_metadata(vid)
        print(json.dumps(meta, indent=2, ensure_ascii=False))

    elif cmd == "trending":
        cat = sys.argv[2] if len(sys.argv) > 2 else "now"
        print(build_trending_url(cat))

    elif cmd == "inject-bypass":
        print(generate_bypass_js())

    elif cmd == "inject-search":
        query = " ".join(sys.argv[2:])
        print(generate_search_js(query))

    elif cmd == "inject-control":
        action = sys.argv[2] if len(sys.argv) > 2 else "status"
        print(generate_player_control_js(action))

    elif cmd == "inject-results":
        print(generate_extract_results_js())

    else:
        print(f"Commande inconnue: {cmd}", file=sys.stderr)
        sys.exit(1)
