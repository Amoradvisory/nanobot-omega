"""Watch framework — helpers réutilisables pour veilles déterministes.

Extrait les briques communes utilisées par run_veille_and_notify (2ememain) pour
permettre de creer rapidement d'autres veilles : immobilier, jobs, prix, stocks.

Briques fournies :
- WatchConfig (dataclass : nom, urls, schedule, geo, scoring rules, ...)
- haversine_km() : distance euclidienne sphere
- TranslationCache : cache JSON persistant Google Translate gratuit
- HealthJournal : journal append-only + alerte si N echecs consécutifs
- ScoreEngine : moteur de scoring déterministe à partir de PREMIUM/RISK rules
- TelegramNotifier : sendMessage / sendPhoto / sendMediaGroup avec fallback en cascade
- DedupStore : déduplication par ID extrait du lien (pattern regex configurable)
- compute_distance_km(location, postcode_coords, user_coords) : helper

Usage type pour une nouvelle veille :

    from watch_framework import (
        WatchConfig, HealthJournal, TranslationCache,
        TelegramNotifier, DedupStore, haversine_km, compute_distance_km,
    )

    config = WatchConfig(name="immo-mouscron", ...)
    health = HealthJournal(Path(".../immo_health.json"))
    dedup = DedupStore(Path(".../immo_history.json"), id_pattern=r"/(im\d+)")
    notifier = TelegramNotifier(token, chat_id)

    # ... scrape -> filter -> score -> notify -> health.update()
"""
from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib import request as urlrequest
from urllib.parse import urlencode

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ===========================================================================
# Geo / distance
# ===========================================================================

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance grand-cercle (km) entre 2 points (lat, lon) en degres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_distance_km(
    location_text: str,
    postcode_coords: dict[str, tuple[float, float]],
    city_to_postcode: dict[str, str],
    user_coords: tuple[float, float],
) -> tuple[float | None, str]:
    """Estime la distance depuis user_coords a partir d'un texte de localisation.

    Retourne (km, source_label).
    Source : 'postcode XXXX', 'city NAME', 'unknown'.
    """
    if not location_text:
        return None, "unknown"
    text = location_text.lower()
    pc_match = re.search(r"\b(\d{4,5})\b", text)
    if pc_match:
        pc = pc_match.group(1)
        coords = postcode_coords.get(pc)
        if coords:
            d = haversine_km(user_coords[0], user_coords[1], coords[0], coords[1])
            return round(d, 1), f"postcode {pc}"
    for city, pc in city_to_postcode.items():
        if city in text:
            coords = postcode_coords.get(pc)
            if coords:
                d = haversine_km(user_coords[0], user_coords[1], coords[0], coords[1])
                return round(d, 1), f"city {city}"
    return None, "unknown"


# ===========================================================================
# Translation cache
# ===========================================================================

class TranslationCache:
    """Cache JSON persistant pour Google Translate gratuit (translate.googleapis.com)."""

    def __init__(self, path: Path, target_lang: str = "fr"):
        self.path = path
        self.target_lang = target_lang
        self._cache: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            self._cache = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._cache = {}

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._cache, indent=2, ensure_ascii=False), encoding="utf-8",
            )
        except Exception:
            pass

    def translate(self, text: str) -> str:
        source = (text or "").strip()
        if not source:
            return source
        if source in self._cache:
            return self._cache[source]
        params = urlencode({
            "client": "gtx", "sl": "auto", "tl": self.target_lang, "dt": "t", "q": source,
        })
        req = urlrequest.Request(
            f"https://translate.googleapis.com/translate_a/single?{params}",
            headers={"User-Agent": "Mozilla/5.0"}, method="GET",
        )
        try:
            with urlrequest.urlopen(req, timeout=8) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            translated = "".join(part[0] for part in payload[0] if part and part[0]).strip()
            self._cache[source] = translated or source
            return self._cache[source]
        except Exception:
            self._cache[source] = source
            return source


# ===========================================================================
# Health journal
# ===========================================================================

class HealthJournal:
    """Journal append-only des runs de la veille avec rolling window."""

    def __init__(self, path: Path, window: int = 20):
        self.path = path
        self.window = window

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"runs": []}

    def update(self, *, success: bool, items_count: int = 0,
               scraper_ok: bool | None = None, error: str | None = None,
               extra: dict[str, Any] | None = None) -> dict[str, Any]:
        data = self._load()
        runs = data.setdefault("runs", [])
        entry: dict[str, Any] = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "success": success,
            "items_count": items_count,
            "error": error,
        }
        if scraper_ok is not None:
            entry["scraper_ok"] = scraper_ok
        if extra:
            entry.update(extra)
        runs.append(entry)
        runs[:] = runs[-self.window:]
        last3 = sum(1 for r in runs[-3:] if not r.get("success"))
        data["last_3_failures"] = last3
        if success:
            data["last_success"] = entry["ts"]
        else:
            data["last_failure"] = entry["ts"]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return data

    def should_alert(self, dedup_hours: int = 6) -> tuple[bool, str | None]:
        """Renvoie (should_send, last_error) si 3 echecs consecutifs et pas alerte recente."""
        data = self._load()
        if data.get("last_3_failures", 0) < 3:
            return False, None
        last_alert = data.get("last_alert")
        if last_alert:
            try:
                last_dt = datetime.fromisoformat(last_alert)
                if (datetime.now() - last_dt).total_seconds() < dedup_hours * 3600:
                    return False, None
            except Exception:
                pass
        runs = data.get("runs", [])
        last_err = next((r.get("error") for r in reversed(runs) if r.get("error")), None)
        return True, last_err

    def mark_alert_sent(self) -> None:
        data = self._load()
        data["last_alert"] = datetime.now().isoformat(timespec="seconds")
        try:
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


# ===========================================================================
# Score engine
# ===========================================================================

@dataclass
class ScoreRule:
    keywords: tuple[str, ...]
    delta: int
    comment: str
    resale_low: int | None = None
    resale_high: int | None = None


@dataclass
class ScoreResult:
    score: int
    verdict: str
    verdict_emoji: str
    comment: str
    all_reasons: list[str]
    resale_low: int | None
    resale_high: int | None
    matched_premium: bool


class ScoreEngine:
    """Moteur déterministe : applique premium_rules (1 match max) + risk_rules (cumulatifs)."""

    DEFAULT_VERDICTS = [
        (8, "TOP OPPORTUNITE", "🔥", "A tenter tout de suite, contacter immediatement."),
        (5, "INTERESSANT", "✅", "A prendre si trajet raisonnable."),
        (3, "MOYEN", "⚖️", "A verifier avant de bouger."),
        (0, "FAIBLE", "🧊", "Ne vaut probablement pas le deplacement."),
    ]

    def __init__(self, premium_rules: list[ScoreRule], risk_rules: list[ScoreRule],
                 category_bonus: dict[str, int] | None = None,
                 verdict_table: list[tuple[int, str, str, str]] | None = None,
                 base_score: int = 1):
        self.premium_rules = premium_rules
        self.risk_rules = risk_rules
        self.category_bonus = category_bonus or {}
        self.verdict_table = verdict_table or self.DEFAULT_VERDICTS
        self.base_score = base_score

    def evaluate(self, *, title: str, description: str = "", category: str = "",
                 distance_km: float | None = None,
                 distance_penalty_threshold: float = 30.0,
                 distance_penalty_per_10km: int = 1,
                 distance_penalty_max: int = 3) -> ScoreResult:
        haystack = f"{title} {description} {category}".lower()
        score = self.base_score + self.category_bonus.get(category, 0)
        reasons: list[str] = []
        resale_low: int | None = None
        resale_high: int | None = None
        matched_premium = False
        for rule in self.premium_rules:
            if any(kw in haystack for kw in rule.keywords):
                score += rule.delta
                reasons.append(rule.comment)
                resale_low, resale_high = rule.resale_low, rule.resale_high
                matched_premium = True
                break
        for rule in self.risk_rules:
            if any(kw in haystack for kw in rule.keywords):
                score += rule.delta
                reasons.append(rule.comment)
        score = max(0, min(10, score))
        if distance_km is not None and distance_km > distance_penalty_threshold:
            penalty = min(
                distance_penalty_max,
                int((distance_km - distance_penalty_threshold) // 10) * distance_penalty_per_10km,
            )
            if penalty > 0:
                score = max(0, score - penalty)
                reasons.append(f"distance {distance_km} km : -{penalty} pts essence")
        verdict, emoji, action = "FAIBLE", "🧊", "Ne vaut probablement pas le deplacement."
        for threshold, name, em, act in self.verdict_table:
            if score >= threshold:
                verdict, emoji, action = name, em, act
                break
        if not reasons:
            reasons.append("Valeur incertaine.")
        return ScoreResult(
            score=score, verdict=verdict, verdict_emoji=emoji,
            comment=f"{action} {reasons[0]}", all_reasons=reasons,
            resale_low=resale_low, resale_high=resale_high,
            matched_premium=matched_premium,
        )


# ===========================================================================
# Dedup store
# ===========================================================================

class DedupStore:
    """Store JSON list of seen IDs, with regex-based ID extraction from URLs."""

    def __init__(self, path: Path, id_pattern: str = r"/(m\d+)"):
        self.path = path
        self.regex = re.compile(id_pattern)
        self._seen: list[str] = []
        self._load()

    def _load(self) -> None:
        try:
            self._seen = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self._seen, list):
                self._seen = []
        except Exception:
            self._seen = []

    def extract_id(self, url: str) -> str:
        m = self.regex.search(url or "")
        return m.group(1) if m else (url or "")

    def is_seen(self, url: str) -> bool:
        return self.extract_id(url) in self._seen

    def add(self, url: str) -> None:
        ad_id = self.extract_id(url)
        if ad_id and ad_id not in self._seen:
            self._seen.append(ad_id)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._seen, indent=2, ensure_ascii=False), encoding="utf-8",
            )
        except Exception:
            pass

    @property
    def count(self) -> int:
        return len(self._seen)


# ===========================================================================
# Telegram notifier (with cascade fallback)
# ===========================================================================

class TelegramNotifier:
    """sendMessage / sendPhoto / sendMediaGroup with cascade fallback."""

    def __init__(self, token: str, chat_id: str, dry_run: bool = False,
                 logger: Callable[[str], None] | None = None):
        self.token = token
        self.chat_id = chat_id
        self.dry_run = dry_run
        self.log = logger or (lambda m: None)

    def _post(self, endpoint: str, payload: dict[str, Any], timeout: int = 20) -> bool:
        if self.dry_run:
            self.log(f"[DRY] {endpoint} skipped, payload {len(json.dumps(payload))} chars")
            return True
        url = f"https://api.telegram.org/bot{self.token}/{endpoint}"
        body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(url, data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlrequest.urlopen(req, timeout=timeout) as resp:
                return resp.status == 200
        except Exception as exc:
            self.log(f"Telegram {endpoint} error: {exc}")
            return False

    def send_message(self, text: str) -> bool:
        return self._post("sendMessage", {
            "chat_id": self.chat_id, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": False,
        }, timeout=15)

    def send_photo(self, photo_url: str, caption: str) -> bool:
        return self._post("sendPhoto", {
            "chat_id": self.chat_id, "photo": photo_url,
            "caption": caption, "parse_mode": "HTML",
        }, timeout=20)

    def send_album(self, photo_urls: list[str], caption: str) -> bool:
        urls = photo_urls[:10]
        media = []
        for i, p in enumerate(urls):
            item: dict[str, Any] = {"type": "photo", "media": p}
            if i == 0:
                item["caption"] = caption
                item["parse_mode"] = "HTML"
            media.append(item)
        return self._post("sendMediaGroup", {"chat_id": self.chat_id, "media": media}, timeout=30)

    def send_with_cascade(self, photo_urls: list[str], caption: str) -> bool:
        """Album si plusieurs photos → photo simple → texte. Falls through on failure."""
        urls = [u for u in (photo_urls or []) if u]
        if len(urls) >= 2 and self.send_album(urls, caption):
            return True
        if urls and self.send_photo(urls[0], caption):
            return True
        return self.send_message(caption)


# ===========================================================================
# Watch config
# ===========================================================================

@dataclass
class WatchConfig:
    """Configuration generique d'une veille."""
    name: str
    urls: list[str]
    schedule_minutes: int = 30
    home_postcode: str = ""
    home_coords: tuple[float, float] = (0.0, 0.0)
    radius_km: int = 50
    source_lang: str = "auto"
    target_lang: str = "fr"
    notification_chat_id: str = ""
    active: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


# ===========================================================================
# Smoke test
# ===========================================================================

def _selftest() -> int:
    print("=== watch_framework selftest ===")
    # haversine basique
    d = haversine_km(50.7372, 3.2141, 50.8276, 3.2647)
    assert 5 < d < 15, f"haversine Mouscron-Kortrijk should be ~10 km, got {d}"
    print(f"  haversine Mouscron-Kortrijk = {d:.1f} km [OK]")
    # ScoreEngine
    engine = ScoreEngine(
        premium_rules=[ScoreRule(("iphone",), 5, "Apple", 100, 600)],
        risk_rules=[ScoreRule(("kapot",), -5, "Casse")],
        category_bonus={"Tech": 2},
    )
    res = engine.evaluate(title="iPhone 12 a donner", category="Tech", distance_km=10)
    assert res.score >= 7, f"iPhone close should score >=7, got {res.score}"
    print(f"  scoreEngine iPhone -> verdict={res.verdict} score={res.score} [OK]")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(_selftest())
