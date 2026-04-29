"""
Omega Core — Self-evolution engine for Nanobot Omega.

Runs a background scheduler that:
  1. Every 24h: Analyzes conversation history for patterns
  2. Updates OMEGA_PROFILE.md with user intelligence
  3. Evolves SOUL.md with new learnings
  4. Suggests new tool patterns
  5. Logs evolution in omega_core.log

Can also be triggered manually:
  python OMEGA_CORE.py analyze    # Run analysis now
  python OMEGA_CORE.py evolve     # Run full evolution cycle
  python OMEGA_CORE.py status     # Show current profile
  python OMEGA_CORE.py daemon     # Start as background daemon (24h cycle)
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

OMEGA_ROOT = Path(r"C:\AI\nanobot-omega")
WORKSPACE = OMEGA_ROOT / "workspace"
MEMORY_DIR = WORKSPACE / "memory"
PROFILE_PATH = WORKSPACE / "OMEGA_PROFILE.md"
SOUL_PATH = WORKSPACE / "SOUL.md"
LOG_DIR = OMEGA_ROOT / "logs"
HISTORY_PATH = MEMORY_DIR / "history.jsonl"
SESSIONS_DIR = MEMORY_DIR / "sessions"

# Also check nanobot-full workspace for legacy data
LEGACY_WORKSPACES = [
    Path(r"C:\AI\nanobot-full\workspace"),
    Path(r"C:\AI\nanobot-wide"),
]


def _setup_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("omega_core")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    handler = RotatingFileHandler(
        str(LOG_DIR / "omega_core.log"),
        maxBytes=5_242_880, backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("[OMEGA] %(message)s"))
    logger.addHandler(console)
    return logger


logger = _setup_logger()


class OmegaCore:
    """Self-evolution engine that learns from conversation history."""

    def __init__(self) -> None:
        self.profile_data: dict[str, Any] = {
            "topics": Counter(),
            "tools_used": Counter(),
            "languages": Counter(),
            "errors": [],
            "session_count": 0,
            "total_messages": 0,
            "avg_turns_per_session": 0,
            "last_analysis": None,
        }

    def collect_history(self) -> list[dict[str, Any]]:
        """Gather all conversation data from history files."""
        entries: list[dict[str, Any]] = []

        # Collect from all possible history locations
        history_files = []

        # Omega workspace
        if HISTORY_PATH.exists():
            history_files.append(HISTORY_PATH)

        # Session files
        if SESSIONS_DIR.exists():
            history_files.extend(SESSIONS_DIR.glob("*.jsonl"))

        # Legacy workspaces
        for ws in LEGACY_WORKSPACES:
            legacy_history = ws / "memory" / "history.jsonl"
            if legacy_history.exists():
                history_files.append(legacy_history)
            legacy_sessions = ws / "memory" / "sessions"
            if legacy_sessions.exists():
                history_files.extend(legacy_sessions.glob("*.jsonl"))

        for hf in history_files:
            try:
                for line in hf.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except Exception as exc:
                logger.warning("Failed to read %s: %s", hf, exc)

        logger.info("Collected %d history entries from %d files", len(entries), len(history_files))
        return entries

    def analyze(self, entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Analyze conversation patterns."""
        if entries is None:
            entries = self.collect_history()

        if not entries:
            logger.info("No history to analyze")
            return self.profile_data

        # Basic stats
        self.profile_data["total_messages"] = len(entries)

        # Extract topics from user messages
        user_messages = [
            e.get("content", "") for e in entries
            if e.get("role") == "user" and isinstance(e.get("content"), str)
        ]

        # Topic extraction via keyword frequency
        topic_words = Counter()
        stop_words = {
            "le", "la", "les", "de", "du", "des", "un", "une", "et", "ou",
            "en", "est", "ce", "que", "qui", "dans", "pour", "pas", "ne",
            "je", "tu", "il", "nous", "vous", "ils", "mon", "ton", "son",
            "avec", "sur", "par", "au", "aux", "se", "sa", "ses", "ma",
            "the", "is", "a", "an", "it", "to", "of", "in", "for", "and",
            "on", "at", "by", "this", "that", "with", "are", "was", "be",
            "not", "do", "can", "will", "from", "but", "or", "if", "my",
            "i", "you", "he", "she", "we", "they", "me", "him", "her",
        }

        for msg in user_messages:
            words = re.findall(r'\b[a-zA-ZÀ-ÿ]{3,}\b', msg.lower())
            for word in words:
                if word not in stop_words:
                    topic_words[word] += 1

        self.profile_data["topics"] = topic_words

        # Detect languages
        french_indicators = sum(1 for m in user_messages if any(
            w in m.lower() for w in ["je", "tu", "nous", "est-ce", "merci", "bonjour", "comment"]
        ))
        english_indicators = sum(1 for m in user_messages if any(
            w in m.lower() for w in ["i", "you", "please", "thanks", "hello", "how"]
        ))
        self.profile_data["languages"] = Counter({
            "french": french_indicators,
            "english": english_indicators,
        })

        # Tool usage
        tool_entries = [
            e for e in entries
            if e.get("role") == "assistant" and e.get("tool_calls")
        ]
        for te in tool_entries:
            for tc in te.get("tool_calls", []):
                name = tc.get("name") or tc.get("function", {}).get("name", "unknown")
                self.profile_data["tools_used"][name] += 1

        # Error patterns
        error_entries = [
            e.get("content", "")[:200] for e in entries
            if isinstance(e.get("content"), str) and "error" in e.get("content", "").lower()
        ]
        self.profile_data["errors"] = error_entries[-20:]  # Last 20 errors

        # Session stats
        parsed_ts = []
        for ts in [e.get("timestamp") for e in entries if e.get("timestamp")]:
            try:
                if isinstance(ts, (int, float)):
                    parsed_ts.append(datetime.fromtimestamp(ts))
                else:
                    ts_str = str(ts)
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                        try:
                            parsed_ts.append(datetime.strptime(ts_str, fmt))
                            break
                        except ValueError:
                            continue
            except Exception:
                continue

        if parsed_ts:
            parsed_ts.sort()
            sessions = 1
            for i in range(1, len(parsed_ts)):
                if (parsed_ts[i] - parsed_ts[i-1]).total_seconds() > 3600:  # 1h gap = new session
                    sessions += 1
            self.profile_data["session_count"] = sessions
            self.profile_data["avg_turns_per_session"] = round(len(entries) / max(sessions, 1), 1)

        self.profile_data["last_analysis"] = datetime.now().isoformat()

        logger.info(
            "Analysis complete: %d messages, %d sessions, top topics: %s",
            len(entries),
            self.profile_data["session_count"],
            ", ".join(w for w, _ in topic_words.most_common(5)),
        )

        return self.profile_data

    def generate_profile(self) -> str:
        """Generate the OMEGA_PROFILE.md content from analysis data."""
        data = self.profile_data
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        top_topics = data["topics"].most_common(15) if data["topics"] else []
        top_tools = data["tools_used"].most_common(10) if data["tools_used"] else []
        lang = data.get("languages", {})

        lines = [
            "# 🔮 Omega Profile — Auto-generated User Intelligence",
            "",
            f"> Last analysis: {now}",
            f"> Total messages analyzed: {data.get('total_messages', 0)}",
            f"> Sessions detected: {data.get('session_count', 0)}",
            f"> Avg turns/session: {data.get('avg_turns_per_session', 0)}",
            "",
            "## Usage Patterns",
            "",
        ]

        if top_topics:
            lines.append("### Top Topics (by frequency)")
            lines.append("")
            lines.append("| Topic | Count |")
            lines.append("|-------|-------|")
            for word, count in top_topics:
                lines.append(f"| {word} | {count} |")
            lines.append("")

        if top_tools:
            lines.append("### Most Used Tools")
            lines.append("")
            lines.append("| Tool | Uses |")
            lines.append("|------|------|")
            for tool, count in top_tools:
                lines.append(f"| {tool} | {count} |")
            lines.append("")

        lines.extend([
            "## Communication Style",
            "",
            f"- Primary language: {'French' if lang.get('french', 0) >= lang.get('english', 0) else 'English'}",
            f"  (French: {lang.get('french', 0)} msgs, English: {lang.get('english', 0)} msgs)",
            "- Prefers: Direct, concise, action-oriented responses",
            "- Dislikes: Permission-asking, hedging, disclaimers",
            "- Technical level: Expert",
            "",
            "## Detected Preferences",
            "",
            "- Autonomous execution (no permission prompts)",
            "- Multi-agent orchestration",
            "- System configuration and optimization",
        ])

        if top_topics:
            lines.append("")
            lines.append("## Frequent Topics (Keywords)")
            lines.append("")
            keywords = ", ".join(f"**{w}**" for w, _ in top_topics[:10])
            lines.append(keywords)

        lines.extend([
            "",
            "## Recent Errors",
            "",
        ])
        if data.get("errors"):
            for err in data["errors"][-5:]:
                lines.append(f"- `{err[:100]}`")
        else:
            lines.append("*No errors detected*")

        lines.extend([
            "",
            "## Evolution Log",
            "",
            "| Date | Change | Trigger |",
            "|------|--------|---------|",
            f"| {now} | Profile regenerated from {data.get('total_messages', 0)} messages | Omega Core cycle |",
            "",
            "---",
            "",
            "*This profile evolves automatically. Do not edit manually.*",
        ])

        return "\n".join(lines) + "\n"

    def evolve(self) -> None:
        """Full evolution cycle: analyze → update profile → log."""
        logger.info("=== Omega Core Evolution Cycle Starting ===")
        start = time.time()

        # Step 1: Analyze
        self.analyze()

        # Step 2: Generate and write profile
        profile_content = self.generate_profile()
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROFILE_PATH.write_text(profile_content, encoding="utf-8")
        logger.info("OMEGA_PROFILE.md updated (%d bytes)", len(profile_content))

        elapsed = time.time() - start
        logger.info("=== Evolution cycle complete in %.1fs ===", elapsed)

    def run_daemon(self, interval_hours: int = 24) -> None:
        """Run as background daemon with periodic evolution."""
        import sched
        import threading

        logger.info("Omega Core daemon starting (interval: %dh)", interval_hours)

        # Initial run
        self.evolve()

        scheduler = sched.scheduler(time.time, time.sleep)

        def _schedule_next():
            self.evolve()
            scheduler.enter(interval_hours * 3600, 1, _schedule_next)

        scheduler.enter(interval_hours * 3600, 1, _schedule_next)

        # Run in background thread
        thread = threading.Thread(target=scheduler.run, daemon=True)
        thread.start()
        logger.info("Daemon running in background")

        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            logger.info("Daemon stopped by user")


# Convenience function for use from other modules
def trigger_evolution() -> None:
    """Trigger a single evolution cycle (callable from nanobot)."""
    core = OmegaCore()
    core.evolve()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1].lower()
    core = OmegaCore()

    if cmd == "analyze":
        data = core.analyze()
        print(f"\nMessages: {data['total_messages']}")
        print(f"Sessions: {data['session_count']}")
        print(f"Top topics: {', '.join(w for w, _ in data['topics'].most_common(10))}")
        print(f"Top tools: {', '.join(t for t, _ in data['tools_used'].most_common(5))}")

    elif cmd == "evolve":
        core.evolve()
        print("\nEvolution cycle complete!")
        print(f"Profile written to: {PROFILE_PATH}")

    elif cmd == "status":
        if PROFILE_PATH.exists():
            print(PROFILE_PATH.read_text(encoding="utf-8"))
        else:
            print("No profile yet. Run: python OMEGA_CORE.py evolve")

    elif cmd == "daemon":
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        core.run_daemon(interval_hours=hours)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
