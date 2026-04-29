#!/usr/bin/env python
"""Deploie les skills nanobot-omega dans les 10 instances Gemini CLI (A-J)."""
import argparse
import json
import shutil
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILLS_SRC = Path("C:/AI/nanobot-omega/skills")
GEMINI_BASE = Path("C:/Users/user/GeminiCLI")
INSTANCES = list("ABCDEFGHIJ")


def expected_skills() -> list[tuple[str, Path]]:
    return [
        (skill_file.stem.replace("SKILL_", "").replace("_", "-"), skill_file)
        for skill_file in sorted(SKILLS_SRC.glob("SKILL_*.md"))
    ]

def deploy():
    skills = [path for _, path in expected_skills()]
    print(f"  Skills a deployer: {len(skills)}")

    for letter in INSTANCES:
        dest_base = GEMINI_BASE / letter / ".gemini" / "skills"

        for skill_file in skills:
            # Convertir SKILL_alpha_web.md → alpha-web/SKILL.md
            name = skill_file.stem.replace("SKILL_", "").replace("_", "-")
            dest_dir = dest_base / name
            dest_dir.mkdir(parents=True, exist_ok=True)

            dest_file = dest_dir / "SKILL.md"
            shutil.copy2(skill_file, dest_file)

        print(f"  [{letter}] {len(skills)} skills deployes")

    print(f"\n  Total: {len(skills)} skills x {len(INSTANCES)} instances = {len(skills)*len(INSTANCES)} fichiers")


def check() -> int:
    skills = expected_skills()
    report = {
        "ok": True,
        "source": str(SKILLS_SRC),
        "instances": {},
        "summary": {"present": 0, "missing": 0, "divergent": 0},
    }

    for letter in INSTANCES:
        dest_base = GEMINI_BASE / letter / ".gemini" / "skills"
        instance = {"present": [], "missing": [], "divergent": []}
        for name, src in skills:
            dest = dest_base / name / "SKILL.md"
            if not dest.exists():
                instance["missing"].append(name)
                report["summary"]["missing"] += 1
                report["ok"] = False
                continue
            if src.read_text(encoding="utf-8", errors="replace") != dest.read_text(encoding="utf-8", errors="replace"):
                instance["divergent"].append(name)
                report["summary"]["divergent"] += 1
                report["ok"] = False
                continue
            instance["present"].append(name)
            report["summary"]["present"] += 1
        report["instances"][letter] = instance

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Verifier les skills sans modifier les instances")
    args = parser.parse_args()
    if args.check:
        raise SystemExit(check())
    deploy()
