#!/usr/bin/env python
"""Create and run small task-specific Nanobot agents."""
from __future__ import annotations

import argparse
import json
import re
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

ROOT = Path(r"C:\AI\nanobot-omega")
AGENTS = ROOT / "workspace" / "ad_hoc_agents"


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_")
    return cleaned or "agent"


def create_agent(name: str, purpose: str) -> dict[str, Any]:
    agent_name = safe_name(name)
    folder = AGENTS / agent_name
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / f"{agent_name}.py"
    manifest = folder / "manifest.json"
    if not script.exists():
        script.write_text(
            f'''#!/usr/bin/env python
"""Ad hoc Nanobot agent: {agent_name}.

Purpose:
{purpose}
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime


def run(input_text: str = "") -> dict:
    # Replace this body when the task becomes concrete.
    return {{
        "ok": True,
        "agent": "{agent_name}",
        "purpose": {purpose!r},
        "input": input_text,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "result": "Agent scaffold ready.",
    }}


def main() -> int:
    parser = argparse.ArgumentParser(description={purpose!r})
    parser.add_argument("--input", default="")
    args = parser.parse_args()
    print(json.dumps(run(args.input), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
            encoding="utf-8",
        )
    manifest.write_text(
        json.dumps(
            {
                "name": agent_name,
                "purpose": purpose,
                "script": str(script),
                "created": datetime.now().isoformat(timespec="seconds"),
                "status": "ready",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "name": agent_name, "folder": str(folder), "script": str(script), "manifest": str(manifest)}


def list_agents() -> dict[str, Any]:
    AGENTS.mkdir(parents=True, exist_ok=True)
    items = []
    for manifest in sorted(AGENTS.glob("*/manifest.json")):
        try:
            items.append(json.loads(manifest.read_text(encoding="utf-8")))
        except Exception:
            continue
    return {"ok": True, "count": len(items), "items": items}


def run_agent(name: str, input_text: str = "") -> dict[str, Any]:
    agent_name = safe_name(name)
    script = AGENTS / agent_name / f"{agent_name}.py"
    if not script.exists():
        raise FileNotFoundError(f"agent not found: {agent_name}")
    proc = subprocess.run(
        ["python", str(script), "--input", input_text],
        cwd=str(script.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    return {"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def main() -> int:
    parser = argparse.ArgumentParser(description="Forge agents ad hoc Nanobot.")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("name")
    create.add_argument("--purpose", required=True)
    run = sub.add_parser("run")
    run.add_argument("name")
    run.add_argument("--input", default="")
    sub.add_parser("list")
    args = parser.parse_args()
    if args.command == "create":
        payload = create_agent(args.name, args.purpose)
    elif args.command == "run":
        payload = run_agent(args.name, args.input)
    elif args.command == "list":
        payload = list_agents()
    else:
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
