"""Deterministic 2ememain watch: scrape free items and notify Telegram.

This deliberately avoids an LLM in the hot path: lower latency, no Gemini quota,
and no hallucinated ads. The expert comment is a deterministic resale/usefulness
heuristic, not a market lookup.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from html import escape
from pathlib import Path
from urllib import request as urlrequest
from urllib.parse import urlencode

WORKSPACE = Path(__file__).parent.resolve()
CONFIG_OMEGA = Path("C:/AI/nanobot-omega/config_omega.json")
SCRAPER_SCRIPT = WORKSPACE / "run_veille_2ememain.py"
LOG_FILE = Path("C:/AI/nanobot-omega/logs/veille_direct.log")
TRANSLATION_CACHE_FILE = WORKSPACE / "veille_2ememain_translation_cache.json"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

DRY_RUN = "--dry-run" in sys.argv

# Same Telegram chat used by Nanobot.
TELEGRAM_CHAT_ID = "8520981076"


PREMIUM_RULES = [
    (("iphone", "macbook", "ipad", "imac"), 5, "Electronique Apple: forte demande, revente rapide si etat correct."),
    (("ps5", "playstation 5", "nintendo switch", "xbox series"), 5, "Console recente: tres forte liquidite, a contacter immediatement."),
    (("velo electrique", "e-bike", "ebike"), 5, "Velo electrique: vraie opportunite si batterie/chargeur presents."),
    (("lave-vaisselle", "vaatwasser", "frigo", "koelkast", "congelateur", "vriezer", "machine a laver", "wasmachine", "seche-linge", "droogkast"), 4, "Electromenager utile: bonne valeur pratique/revente si fonctionnel."),
    (("tv oled", "tv qled", "oled", "qled", "4k"), 4, "TV recente: interessant si dalle intacte et transport possible."),
    (("perceuse", "visseuse", "bosch", "makita", "dewalt", "outillage"), 4, "Outillage: se revend bien et part vite."),
    (("canape", "zetel", "fauteuil", "table", "tafel", "chaise", "stoel", "armoire", "kast", "commode", "bureau", "meuble"), 2, "Meuble: utile, mais valeur depend surtout de l'etat et du transport."),
    (("plante", "plant", "jardin", "tuin", "tondeuse", "grasmaaier", "barbecue"), 2, "Jardin/terrasse: interessant si proche et en bon etat."),
]

RISK_RULES = [
    (("hs", "defect", "defectueux", "defectueuse", "kapot", "pour pieces"), -5, "Risque panne/pieces: a eviter sauf valeur claire."),
    (("a reparer", "reparation", "herstellen", "casse", "broken"), -4, "A reparer: temps et resultat incertains, opportunite faible."),
    (("sale", "vuil", "tache", "taches", "vlek", "vlekken", "dechire", "gescheurd", "troue", "moisi"), -3, "Etat cosmetique faible: difficile a revendre proprement."),
    (("urgent", "aujourd'hui", "containerpark", "dechetterie", "container"), 1, "Urgent: possible bon coup si tu peux reagir vite."),
]

CATEGORY_SCORE = {
    "Electromenager": 2,
    "Informatique": 2,
    "TV / hi-fi": 2,
    "Sport / fitness": 1,
    "Maison / meubles": 1,
    "Jardin / terrasse": 1,
}


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_telegram_token() -> str:
    cfg = json.loads(CONFIG_OMEGA.read_text(encoding="utf-8"))
    token = cfg.get("channels", {}).get("telegram", {}).get("token", "")
    if not token:
        raise RuntimeError("Telegram token introuvable dans config_omega.json")
    return token


def load_translation_cache() -> dict[str, str]:
    try:
        return json.loads(TRANSLATION_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_translation_cache(cache: dict[str, str]) -> None:
    try:
        TRANSLATION_CACHE_FILE.write_text(
            json.dumps(cache, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        log(f"Translation cache write failed: {exc}")


def translate_to_fr(text: str, cache: dict[str, str]) -> str:
    """Translate short ad text to French through Google's public translate endpoint.

    Fails open: if translation is unavailable, keep the original text and do not
    block the watch.
    """
    source = (text or "").strip()
    if not source:
        return source
    if source in cache:
        return cache[source]

    params = urlencode({
        "client": "gtx",
        "sl": "auto",
        "tl": "fr",
        "dt": "t",
        "q": source,
    })
    req = urlrequest.Request(
        f"https://translate.googleapis.com/translate_a/single?{params}",
        headers={"User-Agent": "Mozilla/5.0"},
        method="GET",
    )
    try:
        with urlrequest.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        translated = "".join(part[0] for part in payload[0] if part and part[0]).strip()
        cache[source] = translated or source
        return cache[source]
    except Exception as exc:
        log(f"Translation failed for {source[:60]!r}: {exc}")
        cache[source] = source
        return source


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    if DRY_RUN:
        log(f"[DRY] Telegram skip ({len(text)} chars):\n{text[:600]}...")
        return True
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            ok = resp.status == 200
            if not ok:
                log(f"Telegram HTTP {resp.status}: {resp.read()[:200]}")
            return ok
    except Exception as exc:
        log(f"Telegram error: {exc}")
        return False


def run_scraper() -> list[dict] | None:
    """Run the scraper as subprocess, parse RESULTS_START/RESULTS_END block."""
    import subprocess

    log(f"Running scraper: {SCRAPER_SCRIPT}")
    start = time.time()
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRAPER_SCRIPT)],
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    elapsed = time.time() - start
    log(f"Scraper finished in {elapsed:.1f}s rc={proc.returncode}")

    if proc.returncode != 0:
        log(f"Scraper STDERR: {proc.stderr[:2000]}")
        if proc.stdout.strip():
            log(f"Scraper STDOUT: {proc.stdout[:1000]}")
        return None

    out = proc.stdout
    if "---RESULTS_START---" not in out:
        log("Aucune nouvelle annonce.")
        return []

    block = out.split("---RESULTS_START---", 1)[1].split("---RESULTS_END---", 1)[0]
    try:
        return json.loads(block.strip())
    except json.JSONDecodeError as exc:
        log(f"JSON parse fail: {exc}; block head: {block[:200]}")
        return []


def evaluate_opportunity(ad: dict) -> dict:
    title = ad.get("title") or ""
    category = ad.get("category") or ""
    haystack = f"{title} {category}".lower()
    score = 1 + CATEGORY_SCORE.get(category, 0)
    reasons: list[str] = []

    for keywords, delta, reason in PREMIUM_RULES:
        if any(keyword in haystack for keyword in keywords):
            score += delta
            reasons.append(reason)
            break

    for keywords, delta, reason in RISK_RULES:
        if any(keyword in haystack for keyword in keywords):
            score += delta
            reasons.append(reason)

    score = max(0, min(10, score))
    if score >= 8:
        verdict = "TOP OPPORTUNITE"
        action = "A tenter tout de suite."
    elif score >= 5:
        verdict = "INTERESSANT"
        action = "A prendre si trajet raisonnable."
    elif score >= 3:
        verdict = "MOYEN"
        action = "A verifier avant de bouger."
    else:
        verdict = "FAIBLE"
        action = "Ne vaut probablement pas le deplacement sauf besoin personnel."

    if not reasons:
        reasons.append("Valeur incertaine: decision surtout selon etat, distance et facilite d'enlevement.")

    return {
        "score": score,
        "verdict": verdict,
        "comment": f"{action} {reasons[0]}",
    }


def format_message(ads: list[dict]) -> str:
    n = len(ads)
    header = f"<b>2ememain Mouscron - 50 km - {n} nouveau{'x' if n > 1 else ''} GRATUIT</b>"
    parts = [header]
    translation_cache = load_translation_cache()
    for ad in ads[:15]:
        original_title_raw = (ad.get("title") or "Sans titre")[:160]
        translated_title_raw = translate_to_fr(original_title_raw, translation_cache)[:160]
        title = escape(translated_title_raw or original_title_raw)
        original_title = escape(original_title_raw)
        link = escape(ad.get("link") or "")
        price_raw = escape(ad.get("price_raw") or "")
        category = escape(ad.get("category") or "Autre")
        pro = evaluate_opportunity({**ad, "title": f"{original_title_raw} {translated_title_raw}"})
        original_line = (
            f"\nOriginal: <i>{original_title}</i>"
            if translated_title_raw.casefold() != original_title_raw.casefold()
            else ""
        )
        parts.append(
            f"\n<b>{title}</b>"
            f"{original_line}"
            f"\nCategorie: {category}"
            f"\nAvis pro: <b>{escape(pro['verdict'])}</b> ({pro['score']}/10)"
            f"\n{escape(pro['comment'])}"
            f"\n{link}"
            f"\n<i>{price_raw}</i>"
        )
    if n > 15:
        parts.append(f"\n... et {n - 15} de plus.")
    save_translation_cache(translation_cache)
    return "\n".join(parts)


def main() -> int:
    log("=== START run_veille_and_notify ===")
    try:
        token = load_telegram_token()
    except Exception as exc:
        log(f"FATAL: {exc}")
        return 2

    ads = run_scraper()
    if ads is None:
        log("Scraper failed; notification skipped.")
        return 1
    if not ads:
        log("0 nouveaute; rien a envoyer.")
        return 0

    log(f"{len(ads)} nouveautes a envoyer.")
    msg = format_message(ads)
    ok = send_telegram(token, TELEGRAM_CHAT_ID, msg)
    log(f"Telegram send: {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("Interrupted")
        sys.exit(130)
    except Exception as exc:
        log(f"UNHANDLED: {exc}")
        sys.exit(3)
