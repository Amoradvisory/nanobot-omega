"""Deterministic 2ememain watch: scrape free items and notify Telegram.

This deliberately avoids an LLM in the hot path: lower latency, no Gemini quota,
and no hallucinated ads. The expert comment is a deterministic resale/usefulness
heuristic, not a market lookup.

Lot 3 (2026-04-29): rich Telegram notifications with photo album, distance,
adaptive Dutch message, confidence level, recommended action.
"""
from __future__ import annotations

import json
import math
import re
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
HEALTH_FILE = Path("C:/AI/nanobot-omega/logs/veille_health.json")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

DRY_RUN = "--dry-run" in sys.argv

# Same Telegram chat used by Nanobot.
TELEGRAM_CHAT_ID = "8520981076"

# User home base — Mouscron / 7700.
USER_LAT = 50.7372
USER_LON = 3.2141


# Belgian + Northern France postcodes commonly seen on 2ememain.
# Approximate centers, used for Haversine distance from Mouscron.
POSTCODE_COORDS = {
    "7700": (50.7372, 3.2141),  # Mouscron
    "7711": (50.7372, 3.2141),  # Dottignies
    "7712": (50.7180, 3.1980),  # Herseaux
    "7730": (50.6630, 3.2570),  # Estaimpuis
    "7740": (50.6190, 3.3960),  # Pecq
    "7780": (50.7570, 3.0610),  # Comines (BE)
    "7500": (50.6075, 3.3878),  # Tournai
    "7600": (50.5253, 3.4626),  # Peruwelz
    "7800": (50.6105, 3.7620),  # Ath
    "7860": (50.7090, 3.7770),  # Lessines
    "7900": (50.6440, 3.6200),  # Leuze-en-Hainaut
    "7330": (50.4280, 3.8260),  # Saint-Ghislain
    "7340": (50.4150, 3.8500),  # Colfontaine
    "7350": (50.4500, 3.7670),  # Hensies
    "7000": (50.4674, 3.9526),  # Mons
    "7100": (50.4794, 4.1864),  # La Louviere
    "8500": (50.8276, 3.2647),  # Kortrijk
    "8510": (50.8090, 3.3160),  # Marke / Bellegem
    "8520": (50.8210, 3.2890),  # Kuurne
    "8530": (50.8590, 3.2640),  # Harelbeke
    "8540": (50.7860, 3.3690),  # Deerlijk
    "8550": (50.8470, 3.3970),  # Zwevegem
    "8560": (50.7990, 3.4310),  # Wevelgem
    "8580": (50.7570, 3.4150),  # Avelgem
    "8600": (51.0240, 2.9120),  # Diksmuide
    "8700": (50.9490, 3.1230),  # Tielt
    "8800": (50.9500, 3.1227),  # Roeselare
    "8900": (50.8514, 2.8856),  # Ypres / Ieper
    "9000": (51.0540, 3.7180),  # Gent
    "9300": (50.9355, 4.0407),  # Aalst
    "9400": (50.9370, 4.0410),  # Ninove
    "9500": (50.7700, 3.9000),  # Geraardsbergen
    "9600": (50.7900, 3.5520),  # Renaix
    "9700": (50.8470, 3.6010),  # Oudenaarde
    "9800": (50.9650, 3.5440),  # Deinze
    # Northern France around Lille-Mouscron
    "59000": (50.6292, 3.0573),  # Lille
    "59100": (50.6896, 3.1816),  # Roubaix
    "59200": (50.7253, 3.1610),  # Tourcoing
    "59150": (50.6962, 3.1690),  # Wattrelos
    "59250": (50.6620, 3.0540),  # Halluin
    "59700": (50.6471, 3.0731),  # Marcq-en-Baroeul
    "59800": (50.6300, 3.0700),  # Lille
    "59650": (50.6393, 3.1473),  # Villeneuve d'Ascq
}

CITY_TO_POSTCODE = {
    "mouscron": "7700", "moeskroen": "7700",
    "tournai": "7500", "doornik": "7500",
    "comines": "7780", "komen": "7780",
    "kortrijk": "8500", "courtrai": "8500",
    "roeselare": "8800", "roulers": "8800",
    "wevelgem": "8560",
    "harelbeke": "8530",
    "zwevegem": "8550",
    "ieper": "8900", "ypres": "8900",
    "gent": "9000", "gand": "9000",
    "renaix": "9600", "ronse": "9600",
    "lille": "59000", "rijsel": "59000",
    "roubaix": "59100",
    "tourcoing": "59200", "toerkonje": "59200",
    "mons": "7000", "bergen": "7000",
}


# (keywords, score_delta, comment_template, resale_low, resale_high)
# resale = fourchette de revente realiste en EUR pour la Belgique.
PREMIUM_RULES_RICH = [
    (("iphone", "macbook", "ipad", "imac"), 5,
     "Apple : forte demande, revente rapide si etat correct.",
     100, 600),
    (("ps5", "playstation 5", "nintendo switch", "xbox series"), 5,
     "Console recente : tres forte liquidite, contacter immediatement.",
     80, 250),
    (("velo electrique", "e-bike", "ebike"), 5,
     "Velo electrique : vraie opportunite si batterie/chargeur presents.",
     200, 800),
    (("lave-vaisselle", "vaatwasser"), 4,
     "Lave-vaisselle : revente facile si fonctionnel, 2-3 ans max ideal.",
     50, 180),
    (("frigo", "koelkast", "frigidaire"), 4,
     "Frigo : utile mais transport encombrant, revente moyenne.",
     30, 150),
    (("congelateur", "vriezer", "diepvries"), 4,
     "Congelateur : revente facile en hiver, transport delicat.",
     40, 130),
    (("machine a laver", "wasmachine", "lave-linge"), 4,
     "Lave-linge : revente moyenne si fonctionnel et propre.",
     40, 150),
    (("seche-linge", "droogkast", "tumble"), 4,
     "Seche-linge : revente moyenne, forte demande hiver.",
     40, 140),
    (("tv oled", "tv qled", "oled", "qled"), 4,
     "TV haut de gamme : interessant si dalle intacte.",
     150, 500),
    (("4k", "smart tv"), 3,
     "TV 4K/Smart : revente moyenne, attention aux ecrans casses.",
     50, 200),
    (("perceuse", "visseuse", "bosch", "makita", "dewalt", "outillage", "gereedschap"), 4,
     "Outillage : se revend bien et part vite, surtout marques pros.",
     20, 120),
    (("canape", "zetel", "fauteuil"), 2,
     "Canape : valeur surtout d'usage, revente faible. Verifier transport.",
     0, 80),
    (("table", "tafel"), 2,
     "Table : utile, revente symbolique sauf bois massif/design.",
     0, 60),
    (("chaise", "stoel"), 1,
     "Chaise : valeur faible, surtout d'usage perso ou en lot.",
     0, 30),
    (("armoire", "kast", "commode", "garderobe"), 2,
     "Armoire : encombrant, revente faible, utilite si tu en as besoin.",
     0, 60),
    (("bureau", "desk"), 2,
     "Bureau : revente moyenne si compact + bon etat.",
     0, 80),
    (("tondeuse", "grasmaaier"), 3,
     "Tondeuse : revente correcte au printemps si fonctionnelle.",
     30, 120),
    (("barbecue", "bbq"), 3,
     "Barbecue : revente saisonniere (printemps), valeur si en bon etat.",
     20, 100),
    (("plante", "plant"), 1,
     "Plante : symbolique, gratuit = bonus pour ton interieur/jardin.",
     0, 25),
    (("jardin", "tuin"), 1,
     "Jardin/terrasse : interessant si proche et en bon etat.",
     0, 50),
]

RISK_RULES_RICH = [
    (("hs", "defect", "defectueux", "defectueuse", "kapot", "pour pieces"), -5,
     "Risque panne/pieces : a eviter sauf valeur claire."),
    (("a reparer", "reparation", "herstellen", "casse", "broken"), -4,
     "A reparer : temps incertain, opportunite faible."),
    (("sale", "vuil", "tache", "vlek", "dechire", "gescheurd", "troue", "moisi"), -3,
     "Etat cosmetique faible : difficile a revendre proprement."),
    (("urgent", "aujourd'hui", "containerpark", "dechetterie", "container"), 1,
     "Urgent : possible bon coup si tu peux reagir vite."),
]

CATEGORY_SCORE = {
    "Electromenager": 2,
    "Informatique": 2,
    "TV / hi-fi": 2,
    "Sport / fitness": 1,
    "Maison / meubles": 1,
    "Jardin / terrasse": 1,
}

# Adaptive Dutch contact templates by category.
NL_TEMPLATES = {
    "Electromenager": "Hallo, is dit nog beschikbaar? Werkt het volledig? Ik kan vandaag of morgen ophalen, ik kom uit Moeskroen. Bedankt!",
    "Informatique": "Hallo, is dit nog beschikbaar? In welke staat? Werkt het normaal? Ik kan snel ophalen vanuit Moeskroen. Bedankt!",
    "TV / hi-fi": "Hallo, is dit nog beschikbaar? Is het scherm intact? Werkt alles? Ik kan vlot komen ophalen. Bedankt!",
    "Sport / fitness": "Hallo, is dit nog beschikbaar? In welke staat is het? Ik kan vandaag of morgen ophalen. Bedankt!",
    "Maison / meubles": "Hallo, is dit nog beschikbaar? Wat zijn de afmetingen ongeveer? Ik kan ophalen vanuit Moeskroen met aanhangwagen. Bedankt!",
    "Jardin / terrasse": "Hallo, is dit nog beschikbaar? Werkt het / in welke staat? Ik kan ophalen vanuit Moeskroen. Bedankt!",
    "Vetements": "Hallo, is dit nog beschikbaar? In welke maat? Bedankt!",
}
NL_TEMPLATE_DEFAULT = (
    "Hallo, is dit nog beschikbaar? Ik kan vandaag of morgen ophalen, "
    "ik kom uit Moeskroen. Alvast bedankt!"
)


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
    """Translate short ad text to French through Google's public translate endpoint."""
    source = (text or "").strip()
    if not source:
        return source
    if source in cache:
        return cache[source]
    params = urlencode({
        "client": "gtx", "sl": "auto", "tl": "fr", "dt": "t", "q": source,
    })
    req = urlrequest.Request(
        f"https://translate.googleapis.com/translate_a/single?{params}",
        headers={"User-Agent": "Mozilla/5.0"}, method="GET",
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


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def estimate_distance_km(ad: dict) -> tuple[float | None, str]:
    """Returns (km, source). Source explains where the number came from."""
    if isinstance(ad.get("distance_km"), (int, float)):
        return float(ad["distance_km"]), "scraped"
    location = (ad.get("location") or "").strip()
    if not location:
        return None, "unknown"
    text = location.lower()
    # Look for explicit Belgian/French postcode (4 digits or 5 digits)
    pc_match = re.search(r"\b(\d{4,5})\b", text)
    if pc_match:
        pc = pc_match.group(1)
        coords = POSTCODE_COORDS.get(pc)
        if coords:
            d = haversine_km(USER_LAT, USER_LON, coords[0], coords[1])
            return round(d, 1), f"postcode {pc}"
    for city, pc in CITY_TO_POSTCODE.items():
        if city in text:
            coords = POSTCODE_COORDS.get(pc)
            if coords:
                d = haversine_km(USER_LAT, USER_LON, coords[0], coords[1])
                return round(d, 1), f"city {city}"
    return None, "unknown"


def fuel_cost_estimate(distance_km: float | None) -> str:
    if distance_km is None:
        return "essence inconnue"
    # ~0.10 EUR / km aller-retour pour une voiture moyenne (essence + usure).
    cost = round(distance_km * 2 * 0.10, 1)
    return f"~{cost:.1f} eur essence A/R"


def confidence_level(ad: dict) -> tuple[str, list[str]]:
    score = 0
    reasons = []
    if ad.get("image_main"):
        score += 1
        reasons.append("photo OK")
    else:
        reasons.append("pas de photo")
    desc = (ad.get("description") or "").strip()
    if len(desc) >= 40:
        score += 1
        reasons.append(f"description {len(desc)} chars")
    else:
        reasons.append("description courte/absente")
    if ad.get("location"):
        score += 1
        reasons.append("localisation OK")
    else:
        reasons.append("localisation manquante")
    if ad.get("category") and ad["category"] != "Autre":
        score += 1
    if score >= 3:
        return "fiable", reasons
    if score == 2:
        return "moyenne", reasons
    return "incertaine", reasons


def evaluate_opportunity(ad: dict) -> dict:
    title = ad.get("title") or ""
    description = ad.get("description") or ""
    category = ad.get("category") or ""
    haystack = f"{title} {description} {category}".lower()
    score = 1 + CATEGORY_SCORE.get(category, 0)
    reasons: list[str] = []
    resale_low: int | None = None
    resale_high: int | None = None
    matched_premium = False

    for keywords, delta, reason, low, high in PREMIUM_RULES_RICH:
        if any(keyword in haystack for keyword in keywords):
            score += delta
            reasons.append(reason)
            resale_low, resale_high = low, high
            matched_premium = True
            break

    for keywords, delta, reason in RISK_RULES_RICH:
        if any(keyword in haystack for keyword in keywords):
            score += delta
            reasons.append(reason)

    score = max(0, min(10, score))

    # Penalty for distance > 30 km (essence rentre dans la decision).
    distance_km, distance_source = estimate_distance_km(ad)
    if distance_km is not None and distance_km > 30:
        # Pour chaque tranche de 10 km au-dessus de 30, -1 (max -3).
        penalty = min(3, int((distance_km - 30) // 10))
        if penalty > 0:
            score = max(0, score - penalty)
            reasons.append(f"distance {distance_km} km : -{penalty} pts essence")

    if score >= 8:
        verdict_emoji = "🔥"
        verdict = "TOP OPPORTUNITE"
        action = "A tenter tout de suite, contacter immediatement."
    elif score >= 5:
        verdict_emoji = "✅"
        verdict = "INTERESSANT"
        action = "A prendre si trajet raisonnable."
    elif score >= 3:
        verdict_emoji = "⚖️"
        verdict = "MOYEN"
        action = "A verifier avant de bouger (etat, photo, mesures)."
    else:
        verdict_emoji = "🧊"
        verdict = "FAIBLE"
        action = "Ne vaut probablement pas le deplacement sauf besoin perso."

    if not reasons:
        reasons.append("Valeur incertaine : decision selon etat, distance et facilite d'enlevement.")

    confidence, conf_reasons = confidence_level(ad)
    nl_template = NL_TEMPLATES.get(category, NL_TEMPLATE_DEFAULT)

    return {
        "score": score,
        "verdict": verdict,
        "verdict_emoji": verdict_emoji,
        "comment": f"{action} {reasons[0]}",
        "all_reasons": reasons,
        "resale_low": resale_low,
        "resale_high": resale_high,
        "matched_premium": matched_premium,
        "distance_km": distance_km,
        "distance_source": distance_source,
        "fuel_cost": fuel_cost_estimate(distance_km),
        "confidence": confidence,
        "confidence_reasons": conf_reasons,
        "nl_message": nl_template,
    }


def build_caption(ad: dict, translation_cache: dict[str, str]) -> str:
    """Build the Telegram caption (HTML) for one ad. <=1024 chars (Telegram limit)."""
    original_title_raw = (ad.get("title") or "Sans titre")[:140]
    translated_title_raw = translate_to_fr(original_title_raw, translation_cache)[:140]
    title_h = escape(translated_title_raw or original_title_raw)
    original_h = escape(original_title_raw)
    show_original = translated_title_raw.casefold() != original_title_raw.casefold()

    pro = evaluate_opportunity({**ad, "title": f"{original_title_raw} {translated_title_raw}"})
    category = escape(ad.get("category") or "Autre")
    location = escape((ad.get("location") or "").replace("\n", " ")[:100])
    distance_label = ""
    if pro["distance_km"] is not None:
        distance_label = f"{pro['distance_km']} km de Mouscron"
    elif ad.get("distance_display"):
        distance_label = escape(ad["distance_display"])
    else:
        distance_label = "distance inconnue"

    resale_block = ""
    if pro["resale_low"] is not None and pro["resale_high"] is not None:
        resale_block = f"\n💶 Revente estimee : <b>{pro['resale_low']}-{pro['resale_high']} eur</b>"

    desc_short = (ad.get("description") or "").strip()
    desc_block = ""
    if desc_short:
        desc_h = escape(desc_short[:160])
        desc_block = f"\n📝 <i>{desc_h}</i>"

    parts = [
        f"<b>{pro['verdict_emoji']} {title_h}</b>",
    ]
    if show_original:
        parts.append(f"<i>{original_h}</i>")
    parts.extend([
        f"📂 {category}",
        f"📍 {location or 'lieu non precise'} • {escape(distance_label)} • {escape(pro['fuel_cost'])}",
    ])
    if desc_block:
        parts.append(desc_block.lstrip("\n"))
    parts.extend([
        f"⭐ <b>{escape(pro['verdict'])} {pro['score']}/10</b> (confiance {escape(pro['confidence'])})",
        f"💡 {escape(pro['comment'])}",
    ])
    if resale_block:
        parts.append(resale_block.lstrip("\n"))
    parts.extend([
        f"🇳🇱 <code>{escape(pro['nl_message'])}</code>",
        f"🔗 {escape(ad.get('link') or '')}",
    ])
    caption = "\n".join(parts)
    # Telegram caption limit = 1024 chars.
    if len(caption) > 1020:
        caption = caption[:1015] + "..."
    return caption


def send_telegram_text(token: str, chat_id: str, text: str) -> bool:
    if DRY_RUN:
        log(f"[DRY] sendMessage skip ({len(text)} chars)")
        return True
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }).encode("utf-8")
    req = urlrequest.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as exc:
        log(f"Telegram sendMessage error: {exc}")
        return False


def send_telegram_photo(token: str, chat_id: str, photo_url: str, caption: str) -> bool:
    if DRY_RUN:
        log(f"[DRY] sendPhoto skip — photo_url={photo_url[:80]} caption={len(caption)} chars")
        return True
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = json.dumps({
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urlrequest.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=20) as resp:
            return resp.status == 200
    except Exception as exc:
        log(f"Telegram sendPhoto error: {exc}; will fallback to text")
        return False


def send_telegram_album(token: str, chat_id: str, photo_urls: list[str], caption: str) -> bool:
    """sendMediaGroup : caption va sur le premier item, max 10 photos."""
    if DRY_RUN:
        log(f"[DRY] sendMediaGroup skip — {len(photo_urls)} photos, caption {len(caption)} chars")
        return True
    if len(photo_urls) > 10:
        photo_urls = photo_urls[:10]
    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    media = []
    for i, p in enumerate(photo_urls):
        item = {"type": "photo", "media": p}
        if i == 0:
            item["caption"] = caption
            item["parse_mode"] = "HTML"
        media.append(item)
    payload = json.dumps({"chat_id": chat_id, "media": media}).encode("utf-8")
    req = urlrequest.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except Exception as exc:
        log(f"Telegram sendMediaGroup error: {exc}; will fallback to single photo or text")
        return False


def send_ad_notification(token: str, chat_id: str, ad: dict, translation_cache: dict[str, str]) -> bool:
    """Try sendMediaGroup if multiple photos, else sendPhoto, else sendMessage."""
    caption = build_caption(ad, translation_cache)
    images = [u for u in (ad.get("images") or []) if u]
    main = ad.get("image_main") or (images[0] if images else "")

    if len(images) >= 2:
        if send_telegram_album(token, chat_id, images, caption):
            return True
        # fallback to single photo
    if main:
        if send_telegram_photo(token, chat_id, main, caption):
            return True
        # fallback to text
    return send_telegram_text(token, chat_id, caption)


def run_scraper() -> list[dict] | None:
    import subprocess
    log(f"Running scraper: {SCRAPER_SCRIPT}")
    start = time.time()
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRAPER_SCRIPT)],
        cwd=str(WORKSPACE), capture_output=True, text=True,
        encoding="utf-8", timeout=600,
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


def update_health(success: bool, ads_count: int, scraper_ok: bool, error: str | None = None) -> None:
    """Maintain a simple health file with rolling window of last 10 runs."""
    try:
        if HEALTH_FILE.exists():
            data = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
        else:
            data = {"runs": []}
    except Exception:
        data = {"runs": []}
    data.setdefault("runs", []).append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "success": success,
        "scraper_ok": scraper_ok,
        "ads_count": ads_count,
        "error": error,
    })
    data["runs"] = data["runs"][-20:]
    last_failures = sum(1 for r in data["runs"][-3:] if not r.get("success"))
    data["last_3_failures"] = last_failures
    if success:
        data["last_success"] = data["runs"][-1]["ts"]
    if not success:
        data["last_failure"] = data["runs"][-1]["ts"]
    try:
        HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        HEALTH_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log(f"Health file write failed: {exc}")


def maybe_send_health_alert(token: str, chat_id: str) -> None:
    """If 3 consecutive runs failed, send a Telegram alert (dedup against latest_alert)."""
    try:
        if not HEALTH_FILE.exists():
            return
        data = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    if data.get("last_3_failures", 0) < 3:
        return
    last_alert = data.get("last_alert")
    if last_alert:
        try:
            last_dt = datetime.fromisoformat(last_alert)
            if (datetime.now() - last_dt).total_seconds() < 6 * 3600:
                return  # dedup window 6h
        except Exception:
            pass
    runs = data.get("runs", [])
    last_err = next((r.get("error") for r in reversed(runs) if r.get("error")), "inconnue")
    msg = (
        "⚠️ <b>Veille 2ememain : 3 echecs consecutifs</b>\n"
        f"Derniere erreur : <code>{escape(str(last_err)[:300])}</code>\n"
        "Actions : <code>python C:/AI/nanobot-omega/scripts/nanobot_self_check.py check</code>\n"
        "Ou : <code>python C:/AI/nanobot-omega/workspace/veille_2ememain_control.py status</code>"
    )
    send_telegram_text(token, chat_id, msg)
    data["last_alert"] = datetime.now().isoformat(timespec="seconds")
    try:
        HEALTH_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    log("=== START run_veille_and_notify ===")
    try:
        token = load_telegram_token()
    except Exception as exc:
        log(f"FATAL: {exc}")
        update_health(success=False, ads_count=0, scraper_ok=False, error=str(exc))
        return 2

    ads = run_scraper()
    if ads is None:
        log("Scraper failed; notification skipped.")
        update_health(success=False, ads_count=0, scraper_ok=False, error="scraper_failed")
        try:
            maybe_send_health_alert(token, TELEGRAM_CHAT_ID)
        except Exception as exc:
            log(f"Health alert send failed: {exc}")
        return 1
    if not ads:
        log("0 nouveaute; rien a envoyer.")
        update_health(success=True, ads_count=0, scraper_ok=True)
        return 0

    log(f"{len(ads)} nouveautes a envoyer.")
    translation_cache = load_translation_cache()
    sent_ok = 0
    sent_fail = 0
    # Cap : on envoie max 10 annonces par run (eviter spam Telegram).
    for ad in ads[:10]:
        ok = send_ad_notification(token, TELEGRAM_CHAT_ID, ad, translation_cache)
        if ok:
            sent_ok += 1
        else:
            sent_fail += 1
        time.sleep(1.0)  # politesse Telegram
    if len(ads) > 10:
        send_telegram_text(token, TELEGRAM_CHAT_ID, f"... et <b>{len(ads) - 10}</b> autres annonces gratuites a verifier sur 2ememain.")
    save_translation_cache(translation_cache)
    log(f"Telegram send: OK={sent_ok}, FAIL={sent_fail}")
    update_health(success=(sent_fail == 0), ads_count=len(ads), scraper_ok=True,
                  error=(f"{sent_fail} envois echoues" if sent_fail else None))
    if sent_fail == 0:
        return 0
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("Interrupted")
        sys.exit(130)
    except Exception as exc:
        log(f"UNHANDLED: {exc}")
        update_health(success=False, ads_count=0, scraper_ok=False, error=f"unhandled: {exc}")
        sys.exit(3)
