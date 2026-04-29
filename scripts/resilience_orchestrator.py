#!/usr/bin/env python
"""Command fallback and validation engine for Nanobot."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OMEGA_ROOT = Path(r"C:\AI\nanobot-omega")
REPORTS = OMEGA_ROOT / "workspace" / "resilience_reports"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(result: dict[str, Any], rule: dict[str, Any] | None) -> tuple[bool, str]:
    rule = rule or {"type": "exit_zero"}
    kind = rule.get("type", "exit_zero")
    if kind == "exit_zero":
        return result["returncode"] == 0, "exit_zero"
    if kind == "stdout_contains":
        wanted = str(rule.get("value", ""))
        return wanted in result.get("stdout", ""), f"stdout_contains:{wanted}"
    if kind == "file_exists":
        path = Path(str(rule.get("path", "")))
        return path.exists(), f"file_exists:{path}"
    if kind == "json_ok":
        try:
            data = json.loads(result.get("stdout", "") or "{}")
            return bool(data.get("ok", True)), "json_ok"
        except Exception as exc:
            return False, f"json_parse_failed:{exc}"
    if kind == "nonempty_json_list":
        try:
            data = json.loads(result.get("stdout", "") or "[]")
            return isinstance(data, list) and len(data) > 0, "nonempty_json_list"
        except Exception as exc:
            return False, f"json_parse_failed:{exc}"
    return False, f"unknown_validator:{kind}"


def run_command(step: dict[str, Any]) -> dict[str, Any]:
    cmd = step.get("command")
    if not cmd:
        raise ValueError("step command missing")
    proc = subprocess.run(
        cmd,
        cwd=step.get("cwd") or str(OMEGA_ROOT),
        shell=isinstance(cmd, str),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=int(step.get("timeout", 120)),
        check=False,
    )
    return {
        "name": step.get("name", "step"),
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-5000:],
        "stderr": proc.stderr[-5000:],
    }


def run_plan(plan: dict[str, Any]) -> dict[str, Any]:
    executed = []
    for step in plan.get("steps", []):
        candidates = [step] + list(step.get("fallbacks", []))
        for candidate in candidates:
            result = run_command(candidate)
            ok, reason = validate(result, candidate.get("validate") or step.get("validate"))
            result["valid"] = ok
            result["validation"] = reason
            executed.append(result)
            if ok:
                return {"ok": True, "selected": result["name"], "steps": executed}
    return {"ok": False, "selected": None, "steps": executed}


def doctor_google() -> dict[str, Any]:
    cli = str(OMEGA_ROOT / "scripts" / "google_workspace_cli.py")
    plan = {
        "steps": [
            {
                "name": "google_cli_auth",
                "command": ["python", cli, "--json", "auth", "status"],
                "validate": {"type": "stdout_contains", "value": '"token_exists": true'},
                "fallbacks": [
                    {
                        "name": "google_cli_drive_probe",
                        "command": ["python", cli, "--json", "drive", "ls", "--max", "1"],
                        "validate": {"type": "json_ok"},
                    }
                ],
            }
        ]
    }
    return run_plan(plan)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resilience orchestrator Nanobot.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--plan", required=True)
    sub.add_parser("doctor-google")
    args = parser.parse_args()
    if args.command == "run":
        payload = run_plan(load_json(Path(args.plan)))
    elif args.command == "doctor-google":
        payload = doctor_google()
    else:
        return 2
    REPORTS.mkdir(parents=True, exist_ok=True)
    report = REPORTS / f"resilience_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["report_path"] = str(report)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
