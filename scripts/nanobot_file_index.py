from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


OMEGA_ROOT = Path(r"C:\AI\nanobot-omega")
DB_PATH = OMEGA_ROOT / "workspace" / "memory" / "nanobot_file_index.db"
STATUS_PATH = OMEGA_ROOT / "workspace" / "memory" / "nanobot_file_index_status.json"

DEFAULT_ROOTS = [
    Path(r"C:\AI"),
    Path(r"C:\Users\user\Desktop"),
    Path(r"C:\Users\user\Documents"),
    Path(r"C:\Users\user\Downloads"),
    Path(r"C:\Users\user\.codex"),
    Path(r"C:\Users\user\AppData\Roaming\uv\tools\nanobot-ai"),
]

TEXT_EXTS = {
    ".txt", ".md", ".py", ".ps1", ".bat", ".cmd", ".vbs", ".json", ".toml",
    ".yaml", ".yml", ".csv", ".tsv", ".html", ".htm", ".css", ".js", ".ts",
    ".tsx", ".jsx", ".xml", ".log", ".ini", ".cfg",
}
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".cache", ".npm", "_npx", "npm-cache", "cache", "caches",
    "$recycle.bin", "system volume information",
}
SKIP_PARTS = {
    r"\appdata\local\temp",
    r"\appdata\local\google\chrome\user data",
    r"\appdata\local\microsoft\edge\user data",
    r"\gemini-light-homes",
}
MAX_TEXT_BYTES = 262_144
SAMPLE_CHARS = 5000


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def norm(path: Path) -> str:
    return str(path).replace("\\", "/")


def should_skip_dir(path: Path) -> bool:
    lower_name = path.name.lower()
    lower_path = str(path).lower()
    if lower_name in SKIP_DIRS:
        return True
    return any(part in lower_path for part in SKIP_PARTS)


def read_sample(path: Path, size: int, ext: str) -> str:
    if ext not in TEXT_EXTS or size > MAX_TEXT_BYTES:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:SAMPLE_CHARS]
    except Exception:
        return ""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("pragma journal_mode=wal")
    conn.execute(
        """
        create table if not exists files (
            path text primary key,
            name text,
            parent text,
            ext text,
            size integer,
            mtime real,
            indexed_at real,
            content_sample text
        )
        """
    )
    conn.execute("create index if not exists idx_files_name on files(name)")
    conn.execute("create index if not exists idx_files_ext on files(ext)")
    conn.execute("create index if not exists idx_files_mtime on files(mtime)")
    return conn


def write_status(payload: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def iter_files(roots: list[Path]):
    seen_roots: set[str] = set()
    for root in roots:
        try:
            root = root.resolve()
        except Exception:
            continue
        root_key = str(root).lower()
        if root_key in seen_roots or not root.exists():
            continue
        seen_roots.add(root_key)
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            dirs[:] = [d for d in dirs if not should_skip_dir(current_path / d)]
            if should_skip_dir(current_path):
                continue
            for name in files:
                yield current_path / name


def index_files(max_seconds: int, max_files: int, roots: list[Path]) -> dict:
    started = time.time()
    conn = connect()
    count_seen = 0
    count_upsert = 0
    count_error = 0
    last_path = ""
    write_status({
        "state": "running",
        "started_at": now_text(),
        "roots": [norm(root) for root in roots],
        "file_count": 0,
    })
    try:
        for path in iter_files(roots):
            if time.time() - started > max_seconds or count_seen >= max_files:
                break
            count_seen += 1
            try:
                stat = path.stat()
                ext = path.suffix.lower()
                sample = read_sample(path, stat.st_size, ext)
                p = norm(path)
                last_path = p
                conn.execute(
                    """
                    insert into files(path,name,parent,ext,size,mtime,indexed_at,content_sample)
                    values(?,?,?,?,?,?,?,?)
                    on conflict(path) do update set
                      name=excluded.name,
                      parent=excluded.parent,
                      ext=excluded.ext,
                      size=excluded.size,
                      mtime=excluded.mtime,
                      indexed_at=excluded.indexed_at,
                      content_sample=excluded.content_sample
                    """,
                    (p, path.name, norm(path.parent), ext, stat.st_size, stat.st_mtime, time.time(), sample),
                )
                count_upsert += 1
                if count_upsert % 500 == 0:
                    conn.commit()
            except Exception:
                count_error += 1
        conn.commit()
        total = conn.execute("select count(*) from files").fetchone()[0]
    finally:
        conn.close()
    finished = time.time()
    status = {
        "state": "partial" if (finished - started >= max_seconds or count_seen >= max_files) else "complete",
        "started_at": datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": now_text(),
        "duration_s": round(finished - started, 1),
        "seen_this_run": count_seen,
        "upserted_this_run": count_upsert,
        "errors_this_run": count_error,
        "file_count": total,
        "last_path": last_path,
        "roots": [norm(root) for root in roots],
        "db": norm(DB_PATH),
    }
    write_status(status)
    return status


def search(query: str, limit: int) -> list[dict]:
    conn = connect()
    terms = [part.strip().lower() for part in query.split() if part.strip()]
    if not terms:
        return []
    where_parts = []
    params: list[str] = []
    for term in terms[:5]:
        like = f"%{term}%"
        where_parts.append("(lower(path) like ? or lower(name) like ? or lower(content_sample) like ?)")
        params.extend([like, like, like])
    primary = terms[0]
    sql = (
        "select path,name,parent,ext,size,mtime,content_sample from files where "
        + " and ".join(where_parts)
        + """
          order by
            case
              when lower(name)=? then 0
              when lower(name) like ? then 1
              when lower(path) like ? then 2
              else 3
            end,
            mtime desc
          limit ?
        """
    )
    params.extend([primary, f"%{primary}%", f"%{primary}%"])
    params.append(str(limit))
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    results = []
    for path, name, parent, ext, size, mtime, sample in rows:
        snippet = " ".join((sample or "").split())[:260]
        results.append({
            "path": path,
            "name": name,
            "parent": parent,
            "ext": ext,
            "size": size,
            "mtime": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S") if mtime else "",
            "snippet": snippet,
        })
    return results


def status() -> dict:
    payload = {}
    if STATUS_PATH.exists():
        try:
            payload = json.loads(STATUS_PATH.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            payload = {}
    if DB_PATH.exists():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                payload["file_count"] = conn.execute("select count(*) from files").fetchone()[0]
            payload["db_exists"] = True
        except Exception as exc:
            payload["db_error"] = str(exc)
    else:
        payload["db_exists"] = False
        payload.setdefault("file_count", 0)
    return payload


def format_search(results: list[dict]) -> str:
    if not results:
        return "Aucun fichier trouve dans l'index local. Lance `indexe fichiers` si l'index est ancien."
    lines = [f"{len(results)} resultat(s) dans l'index local:"]
    for idx, row in enumerate(results, 1):
        size_mb = (row.get("size") or 0) / (1024 * 1024)
        lines.append(f"{idx}. {row['path']} ({size_mb:.2f} Mo, modifie {row.get('mtime')})")
        if row.get("snippet"):
            lines.append(f"   extrait: {row['snippet']}")
    return "\n".join(lines)


def parse_roots(raw_roots: list[str] | None) -> list[Path]:
    if not raw_roots:
        return DEFAULT_ROOTS
    return [Path(root) for root in raw_roots]


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_index = sub.add_parser("index")
    p_index.add_argument("--max-seconds", type=int, default=240)
    p_index.add_argument("--max-files", type=int, default=50000)
    p_index.add_argument("--root", action="append", default=None)

    p_search = sub.add_parser("search")
    p_search.add_argument("query", nargs="+")
    p_search.add_argument("--limit", type=int, default=12)
    p_search.add_argument("--json", action="store_true")

    sub.add_parser("status")

    args = parser.parse_args()
    if args.cmd == "index":
        result = index_files(args.max_seconds, args.max_files, parse_roots(args.root))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "search":
        results = search(" ".join(args.query), args.limit)
        print(json.dumps(results, indent=2, ensure_ascii=False) if args.json else format_search(results))
        return 0
    if args.cmd == "status":
        print(json.dumps(status(), indent=2, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
