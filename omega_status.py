from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path


OMEGA_ROOT = Path(r"C:\AI\nanobot-omega")
CONFIG_PATH = OMEGA_ROOT / "config_omega.json"
INSTANCES_PATH = OMEGA_ROOT / "instances.json"
STATE_PATH = OMEGA_ROOT / "shared_state.json"
HEALTH_DIR = OMEGA_ROOT / "health"
JSON_OUT = HEALTH_DIR / "omega_status.json"
TXT_OUT = HEALTH_DIR / "omega_status.txt"
STARTUP_VBS = Path(
    r"C:\Users\user\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\Nanobot Telegram Gateway.vbs"
)
SUPERVISOR_TASK_NAME = "Nanobot Omega Supervisor"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _format_local_hhmm(timestamp: float) -> str:
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%H:%M")


def _format_local_datetime(timestamp: float) -> str:
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _is_rate_limit_error(message: str) -> bool:
    lowered = (message or "").lower()
    return any(token in lowered for token in ("429", "rate limit", "quota"))


def _get_gateway_processes() -> list[dict]:
    ps = r"""
$cfg = 'C:\AI\nanobot-omega\config_omega.json'
Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -and
    $_.CommandLine -match 'nanobot\.exe' -and
    $_.CommandLine -match '\bgateway\b' -and
    $_.CommandLine -match [regex]::Escape($cfg)
  } |
  Select-Object ProcessId, Name, CommandLine |
  ConvertTo-Json -Depth 4
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    raw = (result.stdout or "").strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        return [parsed]
    return parsed


def _task_exists(name: str) -> bool:
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", name],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return result.returncode == 0


def build_status() -> dict:
    config = _read_json(CONFIG_PATH)
    instances_cfg = _read_json(INSTANCES_PATH)
    state = _read_json(STATE_PATH)
    gateway_processes = _get_gateway_processes()
    now = time.time()
    global_state = state.get("global", {})
    stored_global_until = float(
        global_state.get(
            "cooldown_until",
            state.get("global_cooldown_until", 0.0),
        )
        or 0.0
    )
    global_reason = (
        global_state.get(
            "cooldown_reason",
            state.get("global_cooldown_reason", ""),
        )
        or ""
    )
    rate_limit_threshold = int(
        instances_cfg.get("orchestrator", {}).get("global_rate_limit_threshold", 2)
        or 2
    )

    instances = state.get("instances", {})
    available = 0
    blacklisted = 0
    quota_blocked = 0
    auth_blocked = 0
    timeout_blocked = 0
    rate_limited_untils: list[float] = []
    details: list[dict] = []

    for inst in instances_cfg.get("instances", []):
        inst_id = inst.get("id")
        metrics = instances.get(inst_id, {})
        until = float(metrics.get("blacklisted_until", 0.0) or 0.0)
        last_error = metrics.get("last_error_msg", "") or ""
        is_blacklisted = until > now
        if is_blacklisted:
            blacklisted += 1
        else:
            available += 1
        lowered = last_error.lower()
        is_rate_limited = is_blacklisted and _is_rate_limit_error(last_error)
        if is_rate_limited:
            rate_limited_untils.append(until)
        if _is_rate_limit_error(last_error):
            quota_blocked += 1
        if "auth" in lowered or "sorry" in lowered or "automated queries" in lowered:
            auth_blocked += 1
        if "timeout" in lowered:
            timeout_blocked += 1
        details.append(
            {
                "id": inst_id,
                "label": inst.get("label"),
                "blacklisted": is_blacklisted,
                "blacklisted_for_s": max(0, round(until - now)),
                "blacklisted_until": until if is_blacklisted else 0.0,
                "blacklisted_until_hhmm": _format_local_hhmm(until) if is_blacklisted else "",
                "last_error_msg": last_error,
                "avg_latency_ms": round(float(metrics.get("avg_latency_ms", 0.0) or 0.0)),
                "total_calls": int(metrics.get("total_calls", 0) or 0),
                "total_errors": int(metrics.get("total_errors", 0) or 0),
                "total_success": max(
                    0,
                    int(metrics.get("total_calls", 0) or 0)
                    - int(metrics.get("total_errors", 0) or 0),
                ),
            }
        )

    details.sort(key=lambda item: (item["blacklisted"], item["avg_latency_ms"] or 0, item["id"]))
    derived_global_until = (
        max(rate_limited_untils)
        if len(rate_limited_untils) >= rate_limit_threshold
        else 0.0
    )
    global_until = max(
        stored_global_until if stored_global_until > now else 0.0,
        derived_global_until,
    )
    global_active = global_until > now
    global_remaining_s = max(0, round(global_until - now)) if global_active else 0
    if global_active and not global_reason:
        global_reason = "rate_limit_cluster"

    shared_browser = OMEGA_ROOT / "shared-browser" / "chrome-profile"
    status = {
        "timestamp": int(now),
        "model": config.get("agents", {}).get("defaults", {}).get("model", ""),
        "telegram_enabled": bool(config.get("channels", {}).get("telegram", {}).get("enabled", False)),
        "telegram_gateway_running": bool(gateway_processes),
        "telegram_gateway_process_count": len(gateway_processes),
        "supervisor_startup_shortcut": STARTUP_VBS.exists(),
        "supervisor_scheduled_task": _task_exists(SUPERVISOR_TASK_NAME),
        "shared_browser_profile": str(shared_browser),
        "shared_browser_profile_exists": shared_browser.exists(),
        "limiter_total_instances": len(instances_cfg.get("instances", [])),
        "limiter_available_instances": available,
        "limiter_blacklisted_instances": blacklisted,
        "global_cooldown_active": global_active,
        "global_cooldown_remaining_s": global_remaining_s,
        "global_cooldown_until": global_until if global_active else 0.0,
        "global_cooldown_until_hhmm": _format_local_hhmm(global_until) if global_active else "",
        "global_cooldown_until_local": _format_local_datetime(global_until) if global_active else "",
        "global_cooldown_reason": global_reason if global_active else "",
        "rotation_total_instances": len(instances_cfg.get("instances", [])),
        "rotation_available_instances": available,
        "rotation_blacklisted_instances": blacklisted,
        "quota_related_instances": quota_blocked,
        "auth_related_instances": auth_blocked,
        "timeout_related_instances": timeout_blocked,
        "instances": details,
    }
    return status


def to_text(status: dict) -> str:
    if status["global_cooldown_active"]:
        cooldown_line = (
            "Cooldown global: ACTIF jusqu'a "
            f"{status['global_cooldown_until_hhmm']} "
            f"({status['global_cooldown_until_local']}), "
            f"reste {status['global_cooldown_remaining_s']}s"
        )
    else:
        cooldown_line = "Cooldown global: inactif"
    if status["global_cooldown_active"]:
        limiter_line = (
            "Limiteur Gemini: blocage global actif "
            f"({status['limiter_available_instances']}/{status['limiter_total_instances']} instances techniquement disponibles)"
        )
    else:
        limiter_line = (
            f"Limiteur Gemini: {status['limiter_available_instances']}/{status['limiter_total_instances']} "
            "instances disponibles"
        )

    return "\n".join(
        [
            "ETAT OMEGA",
            f"Modele: {status['model']}",
            f"Gateway Telegram: {'OK' if status['telegram_gateway_running'] else 'ARRET'} ({status['telegram_gateway_process_count']} processus)",
            limiter_line,
            cooldown_line,
            f"Instances blacklistees: {status['limiter_blacklisted_instances']}",
            f"Quota: {status['quota_related_instances']} instance(s) en historique quota/429",
            f"Auth: {status['auth_related_instances']} instance(s) en historique auth",
            f"Timeout: {status['timeout_related_instances']} instance(s) en historique timeout",
            f"Navigateur partage: {status['shared_browser_profile']}",
            f"Startup: {'OK' if status['supervisor_startup_shortcut'] else 'MANQUANT'}",
            f"Tache planifiee: {'OK' if status['supervisor_scheduled_task'] else 'MANQUANTE'}",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    status = build_status()
    text = to_text(status)

    if args.write:
        HEALTH_DIR.mkdir(parents=True, exist_ok=True)
        JSON_OUT.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
        TXT_OUT.write_text(text, encoding="utf-8")

    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
