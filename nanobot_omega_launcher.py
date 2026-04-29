"""Launcher for Nanobot Omega using the native Gemini orchestrator provider."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


OMEGA_ROOT = Path(r"C:\AI\nanobot-omega")
CONFIG_PATH = OMEGA_ROOT / "config_omega.json"
GUI_ROOT = Path(r"C:\AI\nanobot-gui")
NANOBOT_SITE = Path(
    r"C:\Users\user\AppData\Roaming\uv\tools\nanobot-ai\Lib\site-packages"
)

if str(NANOBOT_SITE) not in sys.path:
    sys.path.insert(0, str(NANOBOT_SITE))
if str(OMEGA_ROOT) not in sys.path:
    sys.path.insert(0, str(OMEGA_ROOT))
if str(GUI_ROOT) not in sys.path:
    sys.path.insert(0, str(GUI_ROOT))

try:
    from loguru import logger

    logger.remove()
except Exception:
    pass


def run_cli() -> None:
    from nanobot.cli.commands import app

    sys.argv = ["nanobot", "agent", "--config", str(CONFIG_PATH)]
    app()


def run_gateway() -> None:
    from nanobot.cli.commands import app

    sys.argv = ["nanobot", "gateway", "--config", str(CONFIG_PATH)]
    app()


def run_gui() -> None:
    from nanobot_gui import NanobotGui

    app = NanobotGui()
    app.mainloop()


def run_test(prompt: str) -> None:
    from nanobot.nanobot import Nanobot

    async def _test() -> str:
        bot = Nanobot.from_config(CONFIG_PATH)
        result = await bot.run(prompt, session_key="omega:test")
        return result.content

    content = asyncio.run(_test())
    print(f"\n{'=' * 60}")
    print("OMEGA RESPONSE:")
    print(f"{'=' * 60}")
    print(content)
    print(f"{'=' * 60}\n")


def show_status() -> None:
    from gemini_cli_orchestrator import get_orchestrator
    from omega_status import build_status, to_text

    print(to_text(build_status()))
    print()
    status = get_orchestrator().get_status()
    print(json.dumps(status, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nanobot Omega - Gemini-powered AI agent"
    )
    parser.add_argument("--gateway", action="store_true", help="Run in gateway mode")
    parser.add_argument("--gui", action="store_true", help="Launch GUI")
    parser.add_argument("--status", action="store_true", help="Show orchestrator status")
    parser.add_argument("--test", type=str, default=None, help="Quick test with a prompt")
    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.test:
        run_test(args.test)
    elif args.gateway:
        run_gateway()
    elif args.gui:
        run_gui()
    else:
        run_cli()


if __name__ == "__main__":
    main()
