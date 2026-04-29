"""Acquire, verify, and open Windows applications for Nanobot.

Primary routes:
- Installed app detection and verified open
- Winget install for Windows desktop apps
- Direct installer download from a URL
- Basic website page parsing to find a Windows download link

This script is intentionally deterministic: it should never claim success
without verifying an installed package, a launchable app, or a downloaded file.
"""
from __future__ import annotations

import argparse
import html.parser
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path


DOWNLOADS_DIR = Path(r"C:\Users\user\Downloads")
LOG_PATH = Path(r"C:\AI\nanobot-omega\logs\app_acquisition.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

INSTALLER_EXTS = {
    ".exe",
    ".msi",
    ".msix",
    ".appx",
    ".appxbundle",
    ".msixbundle",
    ".zip",
}

COMMON_APP_ROOTS = [
    Path(r"C:\Users\user\AppData\Local\Programs"),
    Path(r"C:\Program Files"),
    Path(r"C:\Program Files (x86)"),
    Path(r"C:\Users\user\AppData\Roaming\Microsoft\Windows\Start Menu\Programs"),
    Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
]

SKIP_WORDS = {
    "application",
    "app",
    "logiciel",
    "programme",
    "le",
    "la",
    "les",
    "l",
    "un",
    "une",
    "du",
    "de",
    "des",
}


def log(message: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"[’'`]", " ", text)
    text = re.sub(r"[^a-z0-9.+:/_-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_target(raw: str) -> str:
    value = (raw or "").strip().strip("\"' ")
    if re.match(r"^https?://", value, flags=re.IGNORECASE):
        return value
    tokens = [token for token in re.split(r"\s+", value) if token]
    while tokens and normalize(tokens[0]) in SKIP_WORDS:
        tokens.pop(0)
    return " ".join(tokens).strip(" .,:;!?")


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    log("RUN " + " ".join(cmd))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def strip_progress_noise(output: str) -> str:
    cleaned: list[str] = []
    for raw in (output or "").replace("\r", "\n").splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"[-\\/|]+", line):
            continue
        cleaned.append(raw)
    return "\n".join(cleaned)


def parse_table(output: str) -> list[dict[str, str]]:
    lines = strip_progress_noise(output).splitlines()
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for idx, raw in enumerate(lines):
        line = raw.rstrip()
        if not line:
            continue
        if re.match(r"^-{3,}$", line.replace(" ", "")):
            continue
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 2:
            continue
        if header is None and any(part.lower() in {"name", "nom", "id", "version", "source"} for part in parts):
            header = parts
            continue
        if header:
            padded = parts + [""] * max(0, len(header) - len(parts))
            row = {header[i]: padded[i] for i in range(min(len(header), len(padded)))}
            rows.append(row)
    return rows


def row_value(row: dict[str, str], *keys: str) -> str:
    lowered = {k.lower(): v for k, v in row.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return ""


def looks_like_url(target: str) -> bool:
    return bool(re.match(r"^https?://", target or "", flags=re.IGNORECASE))


def is_play_store_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.netloc or "").lower()
    return "play.google.com" in host


def get_start_apps(query: str) -> list[dict[str, str]]:
    safe = query.replace("'", "''")
    ps = (
        "Get-StartApps | Where-Object { $_.Name -like '*"
        + safe
        + "*' } | Select-Object Name,AppID | ConvertTo-Json -Depth 3"
    )
    result = run(["powershell", "-NoProfile", "-Command", ps], timeout=20)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    out: list[dict[str, str]] = []
    for item in data or []:
        out.append({
            "name": str(item.get("Name", "")),
            "app_id": str(item.get("AppID", "")),
        })
    return out


def walk_limited(base: Path, max_depth: int = 4):
    if not base.exists():
        return
    base_depth = len(base.parts)
    try:
        for root, dirs, files in os.walk(base):
            current = Path(root)
            depth = len(current.parts) - base_depth
            if depth >= max_depth:
                dirs[:] = []
            yield current, files
    except Exception:
        return


def find_executable(query: str) -> str | None:
    normalized_query = normalize(query).replace(" ", "")
    for base in COMMON_APP_ROOTS:
        for root, files in walk_limited(base, max_depth=4):
            for filename in files:
                lower = filename.lower()
                if not lower.endswith((".exe", ".lnk")):
                    continue
                compact = normalize(Path(filename).stem).replace(" ", "")
                if normalized_query and normalized_query in compact:
                    return str(root / filename)
    return None


def winget_search(query: str) -> list[dict[str, str]]:
    result = run(
        ["winget", "search", "--name", query, "--source", "winget", "--accept-source-agreements"],
        timeout=120,
    )
    if result.returncode != 0:
        return []
    return parse_table(result.stdout)


def winget_list(query: str) -> list[dict[str, str]]:
    result = run(
        ["winget", "list", "--name", query, "--source", "winget", "--accept-source-agreements"],
        timeout=120,
    )
    if result.returncode != 0:
        return []
    return parse_table(result.stdout)


def score_package(row: dict[str, str], query: str) -> int:
    norm_query = normalize(query)
    name = normalize(row_value(row, "Name", "Nom"))
    package_id = normalize(row_value(row, "Id", "ID"))
    source = normalize(row_value(row, "Source"))
    score = 0
    if name == norm_query:
        score += 100
    if package_id == norm_query:
        score += 95
    if norm_query in name:
        score += 50
    if norm_query in package_id:
        score += 40
    if source == "winget":
        score += 10
    return score


def choose_package(query: str) -> dict[str, str] | None:
    rows = winget_search(query)
    if not rows:
        return None
    best = max(rows, key=lambda row: score_package(row, query), default=None)
    if best and score_package(best, query) >= 40:
        return best
    return None


def find_installed_app(query: str) -> dict[str, str | list[dict[str, str]] | bool]:
    installed_rows = winget_list(query)
    exe_path = find_executable(query)
    start_apps = get_start_apps(query)
    installed = bool(installed_rows or exe_path or start_apps)
    name = ""
    package_id = ""
    version = ""
    if installed_rows:
        row = max(installed_rows, key=lambda item: score_package(item, query))
        name = row_value(row, "Name", "Nom")
        package_id = row_value(row, "Id", "ID")
        version = row_value(row, "Version")
    elif start_apps:
        name = start_apps[0]["name"]
    return {
        "installed": installed,
        "name": name or query,
        "package_id": package_id,
        "version": version,
        "exe_path": exe_path or "",
        "start_apps": start_apps,
    }


def display_name(info: dict[str, str | list[dict[str, str]] | bool], fallback: str) -> str:
    start_apps = info.get("start_apps") or []
    if isinstance(start_apps, list) and start_apps:
        first = start_apps[0]
        if isinstance(first, dict):
            name = str(first.get("name") or "").strip()
            if name:
                return name
    for key in ("name", "package_id"):
        value = str(info.get(key) or "").strip()
        if value:
            return value
    return fallback


def verify_download(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


class DownloadLinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._href = href
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        self.links.append({
            "href": self._href,
            "text": " ".join(part.strip() for part in self._text_parts if part.strip()),
        })
        self._href = None
        self._text_parts = []


def choose_download_link(page_url: str, html_text: str) -> str | None:
    parser = DownloadLinkParser()
    parser.feed(html_text)
    page_host = urllib.parse.urlparse(page_url).netloc.lower()
    best_score = -1
    best_link: str | None = None
    for item in parser.links:
        href = item.get("href") or ""
        text = item.get("text") or ""
        resolved = urllib.parse.urljoin(page_url, href)
        parsed = urllib.parse.urlparse(resolved)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        haystack = f"{resolved} {text}".lower()
        score = 0
        if any(path.endswith(ext) for ext in INSTALLER_EXTS):
            score += 120
        if "download" in haystack or "telecharger" in haystack or "setup" in haystack or "installer" in haystack:
            score += 25
        if "windows" in haystack or "win64" in haystack or "x64" in haystack:
            score += 20
        if host == page_host:
            score += 10
        if any(bad in haystack for bad in ("android", "iphone", "ipad", "ios", "mac", "linux", "deb", "rpm")):
            score -= 40
        if score > best_score:
            best_score = score
            best_link = resolved
    return best_link if best_score >= 40 else None


def derive_filename(url: str, response) -> str:
    disposition = response.headers.get("Content-Disposition", "")
    match = re.search(r'filename="?([^";]+)"?', disposition, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    parsed = urllib.parse.urlparse(url)
    name = Path(parsed.path).name
    return name or f"download_{int(time.time())}.bin"


def download_url(url: str) -> tuple[Path | None, str]:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    if is_play_store_url(url):
        return None, (
            "Le Play Store ne fournit pas d'installateur Windows direct. "
            "Il faut soit un appareil Android/emulateur, soit trouver la version Windows officielle."
        )

    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = (response.headers.get("Content-Type") or "").lower()
        final_url = response.geturl()
        if "text/html" in content_type or not Path(urllib.parse.urlparse(final_url).path).suffix.lower() in INSTALLER_EXTS:
            html_bytes = response.read()
            html_text = html_bytes.decode("utf-8", errors="replace")
            candidate = choose_download_link(final_url, html_text)
            if not candidate:
                return None, (
                    "Je n'ai pas trouve de lien d'installation Windows direct sur cette page. "
                    "Donne-moi l'URL exacte de l'installateur ou un nom d'application compatible winget."
                )
            return download_url(candidate)

        filename = derive_filename(final_url, response)
        destination = DOWNLOADS_DIR / filename
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                handle.write(chunk)
    if not verify_download(destination):
        return None, f"Le telechargement a echoue ou le fichier est vide: {destination}"
    return destination, f"Installateur telecharge: {destination}"


def install_with_winget(query: str) -> tuple[bool, str]:
    package = choose_package(query)
    display_name = query
    if package:
        package_id = row_value(package, "Id", "ID")
        display_name = row_value(package, "Name", "Nom") or query
        command = [
            "winget",
            "install",
            "--id",
            package_id,
            "--exact",
            "--source",
            "winget",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--disable-interactivity",
        ]
    else:
        command = [
            "winget",
            "install",
            "--name",
            query,
            "--exact",
            "--source",
            "winget",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--disable-interactivity",
        ]
    result = run(command, timeout=1800)
    output = strip_progress_noise(result.stdout + "\n" + result.stderr)
    if result.returncode != 0:
        fallback = run(
            [
                "winget",
                "install",
                "--name",
                query,
                "--source",
                "winget",
                "--accept-source-agreements",
                "--accept-package-agreements",
                "--disable-interactivity",
            ],
            timeout=1800,
        )
        output = strip_progress_noise(fallback.stdout + "\n" + fallback.stderr)
        if fallback.returncode != 0:
            return False, (
                f"Echec installation winget de {display_name}: {output or 'erreur inconnue'}"
            )
    info = find_installed_app(query)
    if not info["installed"]:
        return False, (
            f"Winget a termine sans erreur visible, mais je ne peux pas verifier l'installation de {display_name}."
        )
    return True, f"{display_name} est maintenant installee et verifiee."


def verify_app_running(query: str, timeout_s: int = 6) -> bool:
    safe = query.replace("'", "''")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        ps = (
            "Get-Process | Where-Object { "
            f"$_.ProcessName -like '*{safe}*' -or $_.MainWindowTitle -like '*{safe}*' "
            "} | Select-Object -First 1 | ConvertTo-Json -Compress"
        )
        result = run(["powershell", "-NoProfile", "-Command", ps], timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return True
        time.sleep(1)
    return False


def launch_app(query: str) -> tuple[bool, str]:
    info = find_installed_app(query)
    if not info["installed"]:
        return False, f"Je ne trouve pas l'application '{query}' sur ce PC."

    exe_path = str(info.get("exe_path") or "")
    try:
        start_apps = info.get("start_apps") or []
        if isinstance(start_apps, list) and start_apps:
            app_id = start_apps[0].get("app_id") or ""
            name = start_apps[0].get("name") or query
            if app_id:
                subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"], close_fds=True)
                seen = verify_app_running(query)
                if seen:
                    return True, f"Application ouverte et verifiee via menu Demarrer: {name}."
                return True, f"Lancement declenche via menu Demarrer pour {name}. Verification visuelle non concluante."

        if exe_path and Path(exe_path).exists():
            if Path(exe_path).suffix.lower() == ".lnk":
                os.startfile(exe_path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen([exe_path], close_fds=True)
            seen = verify_app_running(query)
            if seen:
                return True, f"Application ouverte et verifiee: {Path(exe_path).stem} ({exe_path})."
            return True, f"Lancement declenche pour {Path(exe_path).stem} ({exe_path}). Verification visuelle non concluante."
    except Exception as exc:
        return False, f"Echec ouverture de '{query}': {exc}"

    return False, f"Je trouve '{query}', mais je n'ai pas de chemin de lancement exploitable."


def status_text(query: str) -> str:
    info = find_installed_app(query)
    label = display_name(info, query)
    lines = [f"Statut application: {label}"]
    lines.append(f"Installee: {'oui' if info['installed'] else 'non'}")
    if info.get("package_id"):
        lines.append(f"Paquet winget: {info['package_id']}")
    if info.get("version"):
        lines.append(f"Version: {info['version']}")
    if info.get("exe_path"):
        lines.append(f"Executable: {info['exe_path']}")
    start_apps = info.get("start_apps") or []
    if start_apps:
        lines.append(f"Demarrer: {start_apps[0].get('name')} -> {start_apps[0].get('app_id')}")
    return "\n".join(lines)


def ensure(target: str, open_after: bool = False) -> tuple[bool, str]:
    target = clean_target(target)
    if not target:
        return False, "Cible application vide."

    if looks_like_url(target):
        downloaded, message = download_url(target)
        if not downloaded:
            return False, message
        if open_after and downloaded.suffix.lower() in {".exe", ".msi", ".msix", ".appx", ".appxbundle", ".msixbundle"}:
            try:
                subprocess.Popen([str(downloaded)], close_fds=True)
                return True, message + "\nInstallateur lance."
            except Exception as exc:
                return False, message + f"\nInstallateur non lance: {exc}"
        return True, message

    current = find_installed_app(target)
    if current["installed"]:
        label = display_name(current, target)
        message = f"{label} est deja installee et verifiee.\n" + status_text(target)
        if open_after:
            ok, open_msg = launch_app(target)
            return ok, message + "\n" + open_msg
        return True, message

    ok, message = install_with_winget(target)
    if not ok:
        return False, message
    if open_after:
        opened, open_msg = launch_app(target)
        return opened, message + "\n" + open_msg
    return True, message


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    status_cmd = sub.add_parser("status")
    status_cmd.add_argument("target", nargs="+")

    ensure_cmd = sub.add_parser("ensure")
    ensure_cmd.add_argument("target", nargs="+")
    ensure_cmd.add_argument("--open", action="store_true", dest="open_after")

    open_cmd = sub.add_parser("open")
    open_cmd.add_argument("target", nargs="+")

    args = parser.parse_args(argv[1:])
    target = " ".join(getattr(args, "target", [])).strip()

    if args.command == "status":
        print(status_text(target))
        return 0

    if args.command == "ensure":
        ok, message = ensure(target, open_after=bool(args.open_after))
        print(message)
        return 0 if ok else 2

    if args.command == "open":
        ok, message = launch_app(target)
        print(message)
        return 0 if ok else 2

    print("Commande inconnue.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
