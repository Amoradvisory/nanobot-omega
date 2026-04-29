from __future__ import annotations

import importlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OMEGA = Path("C:/AI/nanobot-omega")
SITE = Path("C:/Users/user/AppData/Roaming/uv/tools/nanobot-ai/Lib/site-packages")
DOCS = [
    OMEGA / "workspace" / "NANOBOT_ARSENAL.md",
    OMEGA / "workspace" / "NANOBOT_STARTUP_CONTEXT.md",
    OMEGA / "AGENT_V2.md",
    OMEGA / "MISSION_YOLO.md",
]
OUT = OMEGA / "health" / "tools_audit.json"

KNOWN_BUILTINS: dict[str, tuple[str, str]] = {
    "browser_automation": ("nanobot.agent.tools.browser_automation", "BrowserAutomationTool"),
    "desktop_automation": ("nanobot.agent.tools.desktop_automation", "DesktopAutomationTool"),
    "tool_diagnostics": ("nanobot.agent.tools.diagnostics", "ToolDiagnosticsTool"),
    "ocr": ("nanobot.agent.tools.ocr", "OCRTool"),
    "vision_analyze_image": ("nanobot.agent.tools.vision", "VisionAnalyzeImageTool"),
    "exec": ("nanobot.agent.tools.shell", "ExecTool"),
    "read_file": ("nanobot.agent.tools.filesystem", "ReadFileTool"),
    "write_file": ("nanobot.agent.tools.filesystem", "WriteFileTool"),
    "edit_file": ("nanobot.agent.tools.filesystem", "EditFileTool"),
    "list_dir": ("nanobot.agent.tools.filesystem", "ListDirTool"),
    "grep": ("nanobot.agent.tools.filesystem", "GrepTool"),
    "glob": ("nanobot.agent.tools.filesystem", "GlobTool"),
    "web_fetch": ("nanobot.agent.tools.web", "WebFetchTool"),
    "web_search": ("nanobot.agent.tools.web", "WebSearchTool"),
    "message": ("nanobot.agent.tools.message", "MessageTool"),
    "spawn": ("nanobot.agent.tools.spawn", "SpawnTool"),
    "cron": ("nanobot.agent.tools.cron", "CronTool"),
}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def declared_tools() -> dict[str, list[str]]:
    names: dict[str, list[str]] = {}
    pattern = re.compile(
        r"`((?:mcp_[A-Za-z0-9_-]+)|browser_automation|desktop_automation|tool_diagnostics|vision_analyze_image|ocr|exec|read_file|write_file|edit_file|list_dir|grep|glob|web_fetch|web_search|message|spawn|cron)`"
    )
    for doc in DOCS:
        text = read_text(doc)
        for match in pattern.finditer(text):
            names.setdefault(match.group(1), []).append(str(doc))
    for name in KNOWN_BUILTINS:
        names.setdefault(name, [])
    return names


def latest_runtime_tools_from_sessions() -> set[str]:
    sessions = sorted((OMEGA / "workspace" / "sessions").glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in sessions[:5]:
        text = read_text(path)
        matches = re.findall(r'"registered_tools"\s*:\s*\[(.*?)\]', text, flags=re.DOTALL)
        if not matches:
            continue
        try:
            return set(re.findall(r'"([^"]+)"', matches[-1]))
        except Exception:
            continue
    return set()


def importable(name: str) -> bool:
    if name.startswith("mcp_"):
        return True
    spec = KNOWN_BUILTINS.get(name)
    if not spec:
        return False
    module_name, class_name = spec
    try:
        module = importlib.import_module(module_name)
        return hasattr(module, class_name)
    except Exception:
        return False


def mcp_server_for(name: str) -> str | None:
    if not name.startswith("mcp_"):
        return None
    rest = name[4:]
    for server in ("filesystem", "google_workspace", "memory", "notion", "sequential_thinking"):
        if rest.startswith(server + "_"):
            return server
    return rest.split("_", 1)[0] if "_" in rest else rest


def last_called_at(name: str) -> str | None:
    newest = None
    for path in (OMEGA / "workspace" / "sessions").glob("*.jsonl"):
        for line in read_text(path).splitlines():
            if f'"name": "{name}"' not in line and f'"name":"{name}"' not in line:
                continue
            try:
                data = json.loads(line)
                ts = data.get("timestamp")
                if ts and (newest is None or ts > newest):
                    newest = ts
            except Exception:
                continue
    return newest


def main() -> int:
    import sys
    if str(SITE) not in sys.path:
        sys.path.insert(0, str(SITE))
    runtime = latest_runtime_tools_from_sessions()
    declared = declared_tools()
    rows: list[dict[str, Any]] = []
    for name in sorted(declared):
        is_importable = importable(name)
        in_runtime = name in runtime or (name in KNOWN_BUILTINS and is_importable)
        rows.append({
            "name": name,
            "declared_in": sorted(set(declared[name])),
            "importable": is_importable,
            "in_runtime_tools": in_runtime,
            "mcp_server": mcp_server_for(name),
            "callable_test": "skipped" if name.startswith("mcp_") or name in {"browser_automation", "desktop_automation", "exec"} else ("ok" if is_importable else "fail"),
            "last_called_at": last_called_at(name),
        })
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_source": "latest tool_diagnostics session plus builtin registry import checks",
        "tools": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
