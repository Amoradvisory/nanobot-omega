#!/usr/bin/env python
"""
google_tools.py - Outils Gmail, Calendar, Drive et Tasks pour Nanobot.

Toutes les fonctions retournent des dictionnaires/listes Python simples pour
etre utilisables en CLI, dans agent.py, ou dans des tests sans interface lourde.
"""
from __future__ import annotations

import base64
import html
import mimetypes
import os
import re
import time as time_module
import unicodedata
from datetime import date as date_cls
from datetime import datetime, time, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from google_auth import GoogleAuthError, build_google_service

GOOGLE_TIMEZONE = "Europe/Paris"


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.lower().strip()


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _has_word(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def _clean_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _json_error(exc: Exception) -> str:
    msg = str(exc)
    return msg[:1000] if msg else exc.__class__.__name__


def _looks_like_browser_or_account_login(prompt: str) -> bool:
    """Avoid routing browser/login/account-switching requests to Google APIs."""
    account_words = (
        "mauvais compte",
        "bon compte",
        "bonne adresse mail",
        "adresse mail",
        "compte ouvert",
        "compte connecte",
        "deconnecte",
        "deconnecter",
        "deconnexion",
        "reconnecte",
        "reconnecter",
        "connexion",
        "login",
        "logout",
        "sign in",
        "sign out",
    )
    surface_words = (
        "navigateur",
        "browser",
        "chrome",
        "github",
        "git hub",
        "page",
        "onglet",
        "site",
        "ouvert",
    )
    data_actions = (
        "liste mes mails",
        "liste mes emails",
        "lis mes mails",
        "lis mes emails",
        "cherche dans gmail",
        "recherche dans gmail",
        "envoie un mail",
        "envoie un email",
        "gmail labels",
        "labels gmail",
    )
    if _contains_any(prompt, data_actions):
        return False
    return _contains_any(prompt, account_words) or (
        _contains_any(prompt, surface_words) and _contains_any(prompt, ("compte", "adresse mail", "connecte"))
    )


def _looks_like_capability_report(prompt: str) -> bool:
    """Avoid treating pasted upgrade/status notes as commands to read Gmail."""
    direct_ops = (
        "liste mes mails",
        "liste mes emails",
        "lis mes mails",
        "lis mes emails",
        "cherche dans gmail",
        "recherche dans gmail",
        "envoie un mail",
        "envoie un email",
        "supprime l email",
        "archive l email",
        "marque l email",
        "classe l email",
    )
    if _contains_any(prompt, direct_ops):
        return False
    report_words = (
        "reponse de codex",
        "demande d augmentation",
        "capacite",
        "capacites",
        "pouvoir",
        "pouvoirs",
        "scope",
        "oauth",
        "autorisation",
        "gmail modify",
        "mcp tool",
        "mcp tools",
        "documentation durable",
        "verifie",
        "verified",
        "c est fait",
        "google workspace capabilities",
        "radical capabilities",
    )
    return _contains_any(prompt, report_words)


def _contains_google_action(prompt: str) -> bool:
    action_words = (
        "liste",
        "lister",
        "affiche",
        "montre",
        "lis",
        "lire",
        "cherche",
        "recherche",
        "search",
        "trouve",
        "cree",
        "creer",
        "ajoute",
        "mets",
        "planifie",
        "envoie",
        "envoyer",
        "send",
        "supprime",
        "delete",
        "corbeille",
        "trash",
        "archive",
        "classe",
        "classer",
        "label",
        "labels",
        "libelle",
        "libelles",
        "marque",
        "lu",
        "non lu",
        "upload",
        "deplace",
        "deplacer",
        "termine",
        "complete",
        "contacts",
        "calendrier",
        "agenda",
    )
    read_contexts = (
        "derniers mails",
        "derniers emails",
        "mails recents",
        "emails recents",
        "boite mail",
        "boite de reception",
        "inbox",
        "mes mails",
        "mes emails",
        "mes courriels",
        "dans mon gmail",
        "dans ma boite mail",
        "dans ma boite de reception",
        "ce que j ai dans gmail",
        "ce que j ai dans mon gmail",
        "qu est ce que j ai dans gmail",
        "qu est ce que j ai dans mon gmail",
    )
    return _contains_any(prompt, action_words) or _contains_any(prompt, read_contexts)


def is_google_prompt(prompt: str) -> bool:
    """Detecte les demandes Google Workspace, sans confondre avec une recherche web."""
    p = _normalize(prompt)
    if _looks_like_capability_report(p):
        return False
    if _looks_like_browser_or_account_login(p):
        return False
    service_words = (
        "gmail",
        "courriel",
        "agenda",
        "calendrier",
        "calendar",
        "drive",
        "google drive",
        "tache",
        "taches",
        "task",
        "tasks",
        "todo",
        "contact",
        "contacts",
        "google docs",
        "document google",
        "google sheets",
        "tableur",
        "google keep",
    )
    generic_service_words = (
        "mail",
        "email",
        "drive",
        "docs",
        "sheets",
        "sheet",
        "task",
        "tasks",
        "tache",
        "taches",
        "todo",
        "contact",
        "contacts",
        "keep",
    )
    if _contains_any(p, service_words) and _contains_google_action(p):
        return True
    if _contains_any(p, generic_service_words) and _contains_google_action(p):
        return True
    return "note" in p and ("google" in p or "keep" in p)


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------


def _headers(headers: list[dict[str, str]]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in headers or []}


def _decode_body(data: str | None) -> str:
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode((data + padding).encode("ascii"))
    return raw.decode("utf-8", errors="replace")


def _strip_html(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", value)
    value = re.sub(r"(?s)<br\s*/?>", "\n", value)
    value = re.sub(r"(?s)</p>", "\n", value)
    value = re.sub(r"(?s)<.*?>", "", value)
    return html.unescape(value).strip()


def _extract_body(payload: dict[str, Any]) -> str:
    """Extrait text/plain en priorite, puis text/html en secours."""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if data and mime == "text/plain":
            plain_parts.append(_decode_body(data))
        elif data and mime == "text/html":
            html_parts.append(_strip_html(_decode_body(data)))
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload or {})
    return "\n\n".join(p for p in plain_parts if p).strip() or "\n\n".join(
        p for p in html_parts if p
    ).strip()


def list_emails(max_results: int = 10, query: str = "") -> list[dict[str, Any]]:
    """Liste les emails Gmail recents, avec support de la syntaxe de recherche Gmail."""
    service = build_google_service("gmail", "v1")
    req: dict[str, Any] = {"userId": "me", "maxResults": max_results}
    if query:
        req["q"] = query
    results = service.users().messages().list(**req).execute()
    messages = results.get("messages", [])
    emails: list[dict[str, Any]] = []

    for item in messages:
        msg = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=item["id"],
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            )
            .execute()
        )
        hdr = _headers(msg.get("payload", {}).get("headers", []))
        emails.append(
            {
                "id": msg.get("id"),
                "threadId": msg.get("threadId"),
                "from": hdr.get("from", ""),
                "to": hdr.get("to", ""),
                "subject": hdr.get("subject", "(sans sujet)"),
                "date": hdr.get("date", ""),
                "snippet": msg.get("snippet", ""),
            }
        )
    return emails


def read_email(email_id: str) -> dict[str, Any]:
    """Lit un email complet par ID Gmail."""
    service = build_google_service("gmail", "v1")
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=email_id, format="full")
        .execute()
    )
    payload = msg.get("payload", {})
    hdr = _headers(payload.get("headers", []))
    return {
        "id": msg.get("id"),
        "threadId": msg.get("threadId"),
        "from": hdr.get("from", ""),
        "to": hdr.get("to", ""),
        "subject": hdr.get("subject", "(sans sujet)"),
        "date": hdr.get("date", ""),
        "snippet": msg.get("snippet", ""),
        "labelIds": msg.get("labelIds", []),
        "body": _extract_body(payload),
    }


def send_email(to: str, subject: str, body: str) -> dict[str, Any]:
    """Envoie un email texte via Gmail."""
    service = build_google_service("gmail", "v1")
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject or "(sans sujet)"
    msg.set_content(body or "")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"id": sent.get("id"), "threadId": sent.get("threadId"), "to": to}


def search_emails(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Cherche dans Gmail avec la syntaxe Gmail: from:, newer_than:, has:, etc."""
    return list_emails(max_results=max_results, query=query)


def list_gmail_labels() -> list[dict[str, Any]]:
    """Liste les labels Gmail disponibles."""
    service = build_google_service("gmail", "v1")
    result = service.users().labels().list(userId="me").execute()
    return result.get("labels", [])


def create_gmail_label(name: str) -> dict[str, Any]:
    """Cree un label Gmail utilisateur."""
    service = build_google_service("gmail", "v1")
    return (
        service.users()
        .labels()
        .create(
            userId="me",
            body={
                "name": name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        .execute()
    )


def delete_gmail_label(label_name_or_id: str) -> dict[str, Any]:
    """Supprime un label Gmail utilisateur."""
    label_id = _gmail_label_id(label_name_or_id, create=False)
    system_labels = {
        "INBOX",
        "UNREAD",
        "STARRED",
        "TRASH",
        "SPAM",
        "IMPORTANT",
        "SENT",
        "DRAFT",
        "CATEGORY_PERSONAL",
        "CATEGORY_SOCIAL",
        "CATEGORY_PROMOTIONS",
        "CATEGORY_UPDATES",
        "CATEGORY_FORUMS",
    }
    if label_id in system_labels:
        raise ValueError(f"Refus de supprimer un label systeme Gmail: {label_id}")
    build_google_service("gmail", "v1").users().labels().delete(userId="me", id=label_id).execute()
    return {"id": label_id, "deleted": True}


def _gmail_label_id(label_name_or_id: str, *, create: bool = False) -> str:
    wanted = (label_name_or_id or "").strip()
    if not wanted:
        raise ValueError("Label Gmail vide.")
    system_aliases = {
        "inbox": "INBOX",
        "unread": "UNREAD",
        "read": "UNREAD",
        "starred": "STARRED",
        "trash": "TRASH",
        "spam": "SPAM",
        "important": "IMPORTANT",
    }
    if wanted.upper() in system_aliases.values():
        return wanted.upper()
    normalized = _normalize(wanted)
    if normalized in system_aliases:
        return system_aliases[normalized]
    for label in list_gmail_labels():
        if label.get("id") == wanted or _normalize(label.get("name", "")) == normalized:
            return str(label["id"])
    if create:
        return str(create_gmail_label(wanted)["id"])
    raise ValueError(f"Label Gmail introuvable: {label_name_or_id}")


def modify_email_labels(
    email_id: str,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    *,
    create_missing_labels: bool = False,
) -> dict[str, Any]:
    """Ajoute/retire des labels Gmail sur un message."""
    add_ids = [_gmail_label_id(label, create=create_missing_labels) for label in (add or [])]
    remove_ids = [_gmail_label_id(label, create=False) for label in (remove or [])]
    result = (
        build_google_service("gmail", "v1")
        .users()
        .messages()
        .modify(
            userId="me",
            id=email_id,
            body={"addLabelIds": add_ids, "removeLabelIds": remove_ids},
        )
        .execute()
    )
    return {
        "id": result.get("id"),
        "threadId": result.get("threadId"),
        "labelIds": result.get("labelIds", []),
        "added": add_ids,
        "removed": remove_ids,
    }


def mark_email_read(email_id: str, read: bool = True) -> dict[str, Any]:
    """Marque un email comme lu ou non lu."""
    return modify_email_labels(email_id, remove=["UNREAD"] if read else [], add=[] if read else ["UNREAD"])


def archive_email(email_id: str) -> dict[str, Any]:
    """Archive un email en retirant le label INBOX."""
    return modify_email_labels(email_id, remove=["INBOX"])


def trash_email(email_id: str) -> dict[str, Any]:
    """Deplace un email dans la corbeille Gmail."""
    result = build_google_service("gmail", "v1").users().messages().trash(userId="me", id=email_id).execute()
    return {"id": result.get("id"), "threadId": result.get("threadId"), "labelIds": result.get("labelIds", []), "trashed": True}


def untrash_email(email_id: str) -> dict[str, Any]:
    """Restaure un email depuis la corbeille Gmail."""
    result = build_google_service("gmail", "v1").users().messages().untrash(userId="me", id=email_id).execute()
    return {"id": result.get("id"), "threadId": result.get("threadId"), "labelIds": result.get("labelIds", []), "untrashed": True}


def delete_email(email_id: str, *, permanent: bool = False) -> dict[str, Any]:
    """Supprime un email. Par defaut: corbeille. Permanent: delete Gmail."""
    if not permanent:
        return trash_email(email_id)
    build_google_service("gmail", "v1").users().messages().delete(userId="me", id=email_id).execute()
    return {"id": email_id, "deleted": True, "permanent": True}


def move_email_to_label(
    email_id: str,
    label: str,
    *,
    archive: bool = True,
    create_missing_label: bool = True,
) -> dict[str, Any]:
    """Classe un email sous un label, avec retrait optionnel de INBOX."""
    remove = ["INBOX"] if archive else []
    return modify_email_labels(
        email_id,
        add=[label],
        remove=remove,
        create_missing_labels=create_missing_label,
    )


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


WEEKDAYS = {
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
}


def _next_weekday(name: str, *, today: date_cls | None = None) -> date_cls:
    base = today or date_cls.today()
    target = WEEKDAYS[name]
    days = (target - base.weekday()) % 7
    if days == 0:
        days = 7
    return base + timedelta(days=days)


def _parse_date(value: str | date_cls | datetime | None) -> date_cls:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_cls):
        return value
    if not value:
        return date_cls.today()
    raw = str(value).strip()
    norm = _normalize(raw)
    if norm in ("aujourd'hui", "aujourdhui", "today"):
        return date_cls.today()
    if norm in ("demain", "tomorrow"):
        return date_cls.today() + timedelta(days=1)
    if norm in ("apres demain", "apres-demain"):
        return date_cls.today() + timedelta(days=2)
    if norm in WEEKDAYS:
        return _next_weekday(norm)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Date non comprise: {value}")


def _parse_time(value: str | time | None) -> time:
    if isinstance(value, time):
        return value
    if not value:
        return time(9, 0)
    raw = str(value).strip().lower().replace(" ", "")
    match = re.search(r"(\d{1,2})(?:h|:)?(\d{2})?", raw)
    if not match:
        raise ValueError(f"Heure non comprise: {value}")
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    return time(hour, minute)


def _local_dt(day: date_cls, clock: time) -> datetime:
    return datetime.combine(day, clock).astimezone()


def list_events(days: int = 7, start_date: str | date_cls | None = None) -> list[dict[str, Any]]:
    """Liste les evenements des N prochains jours."""
    service = build_google_service("calendar", "v3")
    start_day = _parse_date(start_date) if start_date else None
    start = _local_dt(start_day, time(0, 0)) if start_day else datetime.now().astimezone()
    end = start + timedelta(days=days)

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            maxResults=50,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = events_result.get("items", [])
    return [
        {
            "id": item.get("id"),
            "title": item.get("summary", "(sans titre)"),
            "start": item.get("start", {}).get("dateTime")
            or item.get("start", {}).get("date"),
            "end": item.get("end", {}).get("dateTime") or item.get("end", {}).get("date"),
            "location": item.get("location", ""),
            "htmlLink": item.get("htmlLink", ""),
        }
        for item in items
    ]


def create_event(
    title: str,
    date: str | date_cls,
    time: str | time,
    duration: int = 60,
) -> dict[str, Any]:
    """Cree un evenement dans l'agenda principal."""
    service = build_google_service("calendar", "v3")
    start_day = _parse_date(date)
    start_clock = _parse_time(time)
    start = datetime.combine(start_day, start_clock)
    end = start + timedelta(minutes=int(duration or 60))
    event = {
        "summary": title or "Evenement Nanobot",
        "start": {"dateTime": start.isoformat(), "timeZone": GOOGLE_TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": GOOGLE_TIMEZONE},
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    return {
        "id": created.get("id"),
        "title": created.get("summary"),
        "start": created.get("start", {}).get("dateTime"),
        "end": created.get("end", {}).get("dateTime"),
        "htmlLink": created.get("htmlLink"),
    }


def delete_event(event_id: str) -> dict[str, Any]:
    """Supprime un evenement Calendar par ID."""
    service = build_google_service("calendar", "v3")
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return {"id": event_id, "deleted": True}


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------


def list_files(folder: str | None = None, max: int = 20) -> list[dict[str, Any]]:
    """Liste les fichiers Google Drive recents."""
    service = build_google_service("drive", "v3")
    query = "trashed = false"
    if folder:
        query += f" and '{folder}' in parents"
    result = (
        service.files()
        .list(
            q=query,
            pageSize=max,
            orderBy="modifiedTime desc",
            fields="files(id,name,mimeType,modifiedTime,size,webViewLink)",
        )
        .execute()
    )
    return result.get("files", [])


def search_files(query: str, max_results: int = 20, mime_type: str | None = None) -> list[dict[str, Any]]:
    """Cherche des fichiers Drive par nom ou type MIME."""
    service = build_google_service("drive", "v3")
    safe_query = (query or "").replace("'", "\\'")
    clauses = ["trashed = false"]
    if safe_query:
        clauses.append(f"name contains '{safe_query}'")
    if mime_type:
        clauses.append(f"mimeType = '{mime_type}'")
    result = (
        service.files()
        .list(
            q=" and ".join(clauses),
            pageSize=max_results,
            orderBy="modifiedTime desc",
            fields="files(id,name,mimeType,modifiedTime,size,parents,webViewLink)",
        )
        .execute()
    )
    return result.get("files", [])


def create_folder(name: str, parent: str | None = None) -> dict[str, Any]:
    """Cree un dossier Google Drive."""
    metadata: dict[str, Any] = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent:
        metadata["parents"] = [parent]
    return (
        build_google_service("drive", "v3")
        .files()
        .create(body=metadata, fields="id,name,mimeType,parents,webViewLink")
        .execute()
    )


def update_file_metadata(
    file_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    starred: bool | None = None,
) -> dict[str, Any]:
    """Met a jour les metadonnees Drive simples."""
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    if starred is not None:
        body["starred"] = bool(starred)
    if not body:
        raise ValueError("Aucune metadonnee Drive a modifier.")
    return (
        build_google_service("drive", "v3")
        .files()
        .update(fileId=file_id, body=body, fields="id,name,mimeType,description,starred,modifiedTime,webViewLink")
        .execute()
    )


def move_file(file_id: str, folder_id: str) -> dict[str, Any]:
    """Deplace un fichier Drive vers un dossier cible."""
    service = build_google_service("drive", "v3")
    file = service.files().get(fileId=file_id, fields="parents").execute()
    previous_parents = ",".join(file.get("parents", []))
    return (
        service.files()
        .update(
            fileId=file_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields="id,name,mimeType,parents,modifiedTime,webViewLink",
        )
        .execute()
    )


def delete_file(file_id: str, *, permanent: bool = False) -> dict[str, Any]:
    """Supprime un fichier Drive. Par defaut, envoie a la corbeille."""
    service = build_google_service("drive", "v3")
    if permanent:
        service.files().delete(fileId=file_id).execute()
        return {"id": file_id, "deleted": True, "permanent": True}
    result = service.files().update(fileId=file_id, body={"trashed": True}, fields="id,name,trashed").execute()
    return {**result, "deleted": True, "permanent": False}


def read_file(file_id: str) -> dict[str, Any]:
    """Lit un fichier texte ou exporte un Google Doc/Sheet en texte."""
    service = build_google_service("drive", "v3")
    meta = (
        service.files()
        .get(fileId=file_id, fields="id,name,mimeType,modifiedTime,webViewLink")
        .execute()
    )
    mime = meta.get("mimeType", "")

    export_mime = None
    if mime == "application/vnd.google-apps.document":
        export_mime = "text/plain"
    elif mime == "application/vnd.google-apps.spreadsheet":
        export_mime = "text/csv"

    if export_mime:
        content = service.files().export(fileId=file_id, mimeType=export_mime).execute()
    else:
        content = service.files().get_media(fileId=file_id).execute()

    text = content if isinstance(content, str) else bytes(content).decode("utf-8", errors="replace")
    return {**meta, "text": text}


def upload_file(local_path: str, folder: str | None = None) -> dict[str, Any]:
    """Upload un fichier local vers Google Drive."""
    try:
        from googleapiclient.http import MediaFileUpload
    except Exception as exc:  # pragma: no cover - dependances optionnelles
        raise GoogleAuthError(
            "google-api-python-client est requis pour uploader un fichier."
        ) from exc

    path = Path(local_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {path}")

    service = build_google_service("drive", "v3")
    mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    metadata: dict[str, Any] = {"name": path.name}
    if folder:
        metadata["parents"] = [folder]
    media = MediaFileUpload(str(path), mimetype=mime_type, resumable=False)
    return (
        service.files()
        .create(body=metadata, media_body=media, fields="id,name,mimeType,webViewLink")
        .execute()
    )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def _task_service() -> Any:
    return build_google_service("tasks", "v1")


def _default_tasklist_id(service: Any) -> str | None:
    lists = service.tasklists().list(maxResults=10).execute().get("items", [])
    if lists:
        return lists[0]["id"]
    created = service.tasklists().insert(body={"title": "Nanobot"}).execute()
    return created.get("id")


def list_tasks() -> list[dict[str, Any]]:
    """Liste les taches non supprimees de la liste par defaut."""
    service = _task_service()
    tasklist_id = _default_tasklist_id(service)
    if not tasklist_id:
        return []
    result = (
        service.tasks()
        .list(tasklist=tasklist_id, showCompleted=True, showDeleted=False, maxResults=50)
        .execute()
    )
    return [
        {
            "id": item.get("id"),
            "title": item.get("title", ""),
            "status": item.get("status", ""),
            "due": item.get("due", ""),
            "notes": item.get("notes", ""),
            "tasklist": tasklist_id,
        }
        for item in result.get("items", [])
    ]


def _due_value(due_date: str | None) -> str | None:
    if not due_date:
        return None
    day = _parse_date(due_date)
    return datetime.combine(day, time(0, 0), tzinfo=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def add_task(title: str, due_date: str | None = None) -> dict[str, Any]:
    """Ajoute une tache Google Tasks."""
    service = _task_service()
    tasklist_id = _default_tasklist_id(service)
    if not tasklist_id:
        raise RuntimeError("Aucune liste Google Tasks disponible.")
    body: dict[str, Any] = {"title": title}
    due = _due_value(due_date)
    if due:
        body["due"] = due
    created = service.tasks().insert(tasklist=tasklist_id, body=body).execute()
    return {
        "id": created.get("id"),
        "title": created.get("title"),
        "due": created.get("due"),
        "status": created.get("status"),
        "tasklist": tasklist_id,
    }


def _find_tasklist_for_task(service: Any, task_id: str) -> str | None:
    for tasklist in service.tasklists().list(maxResults=20).execute().get("items", []):
        tasklist_id = tasklist.get("id")
        try:
            service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
            return tasklist_id
        except Exception:
            continue
    return None


def complete_task(task_id: str) -> dict[str, Any]:
    """Marque une tache comme terminee."""
    service = _task_service()
    tasklist_id = _find_tasklist_for_task(service, task_id) or _default_tasklist_id(service)
    completed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    task = (
        service.tasks()
        .patch(
            tasklist=tasklist_id,
            task=task_id,
            body={"status": "completed", "completed": completed},
        )
        .execute()
    )
    return {
        "id": task.get("id"),
        "title": task.get("title"),
        "status": task.get("status"),
        "completed": task.get("completed"),
        "tasklist": tasklist_id,
    }


# ---------------------------------------------------------------------------
# Contacts / People API
# ---------------------------------------------------------------------------


CONTACT_FIELDS = "names,emailAddresses,phoneNumbers,organizations"


def _first_value(items: list[dict[str, Any]] | None, *keys: str) -> str:
    if not items:
        return ""
    first = items[0] or {}
    for key in keys:
        value = first.get(key)
        if value:
            return str(value)
    return ""


def _person_summary(person: dict[str, Any]) -> dict[str, Any]:
    emails = [e.get("value", "") for e in person.get("emailAddresses", []) if e.get("value")]
    phones = [p.get("value", "") for p in person.get("phoneNumbers", []) if p.get("value")]
    orgs = [
        _clean_ws(" ".join(str(o.get(k, "")) for k in ("name", "title") if o.get(k)))
        for o in person.get("organizations", [])
    ]
    return {
        "resourceName": person.get("resourceName"),
        "name": _first_value(person.get("names"), "displayName", "unstructuredName"),
        "emails": emails,
        "phones": phones,
        "organizations": [o for o in orgs if o],
    }


def list_contacts(max_results: int = 20) -> list[dict[str, Any]]:
    """Liste les contacts Google du compte connecte."""
    service = build_google_service("people", "v1")
    result = (
        service.people()
        .connections()
        .list(
            resourceName="people/me",
            pageSize=max_results,
            personFields=CONTACT_FIELDS,
            sortOrder="FIRST_NAME_ASCENDING",
        )
        .execute()
    )
    return [_person_summary(item) for item in result.get("connections", [])]


def search_contacts(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Cherche dans les contacts Google."""
    service = build_google_service("people", "v1")
    # Google recommande un appel de warmup avant searchContacts.
    service.people().searchContacts(query="", pageSize=1, readMask=CONTACT_FIELDS).execute()
    result = (
        service.people()
        .searchContacts(query=query, pageSize=max_results, readMask=CONTACT_FIELDS)
        .execute()
    )
    return [_person_summary(item.get("person", {})) for item in result.get("results", [])]


def create_contact(
    name: str,
    email: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    """Cree un contact Google simple."""
    body: dict[str, Any] = {"names": [{"givenName": name, "displayName": name}]}
    if email:
        body["emailAddresses"] = [{"value": email}]
    if phone:
        body["phoneNumbers"] = [{"value": phone}]
    created = build_google_service("people", "v1").people().createContact(body=body).execute()
    return _person_summary(created)


# ---------------------------------------------------------------------------
# Google Docs
# ---------------------------------------------------------------------------


GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"


def _drive_files_by_mime(
    mime_type: str,
    *,
    query: str = "",
    max_results: int = 20,
) -> list[dict[str, Any]]:
    service = build_google_service("drive", "v3")
    q = f"trashed = false and mimeType = '{mime_type}'"
    if query:
        safe_query = query.replace("'", "\\'")
        q += f" and name contains '{safe_query}'"
    result = (
        service.files()
        .list(
            q=q,
            pageSize=max_results,
            orderBy="modifiedTime desc",
            fields="files(id,name,mimeType,modifiedTime,webViewLink)",
        )
        .execute()
    )
    return result.get("files", [])


def list_docs(max_results: int = 20, query: str = "") -> list[dict[str, Any]]:
    """Liste ou cherche les Google Docs recents via Drive."""
    return _drive_files_by_mime(GOOGLE_DOC_MIME, query=query, max_results=max_results)


def create_doc(title: str) -> dict[str, Any]:
    """Cree un Google Doc vide."""
    doc = build_google_service("docs", "v1").documents().create(body={"title": title}).execute()
    return {
        "id": doc.get("documentId"),
        "title": doc.get("title"),
    }


def _doc_text(elements: list[dict[str, Any]] | None) -> str:
    chunks: list[str] = []
    for element in elements or []:
        paragraph = element.get("paragraph")
        if paragraph:
            for pe in paragraph.get("elements", []) or []:
                content = pe.get("textRun", {}).get("content")
                if content:
                    chunks.append(content)
        table = element.get("table")
        if table:
            for row in table.get("tableRows", []) or []:
                cells = row.get("tableCells", []) or []
                for cell in cells:
                    chunks.append(_doc_text(cell.get("content", [])))
                chunks.append("\n")
    return "".join(chunks).strip()


def read_doc(document_id: str) -> dict[str, Any]:
    """Lit le texte principal d'un Google Doc."""
    doc = build_google_service("docs", "v1").documents().get(documentId=document_id).execute()
    return {
        "id": doc.get("documentId"),
        "title": doc.get("title"),
        "text": _doc_text(doc.get("body", {}).get("content", [])),
    }


def append_doc(document_id: str, text: str) -> dict[str, Any]:
    """Ajoute du texte a la fin d'un Google Doc."""
    service = build_google_service("docs", "v1")
    doc = service.documents().get(documentId=document_id).execute()
    content = doc.get("body", {}).get("content", []) or []
    end_index = max(1, int(content[-1].get("endIndex", 1)) - 1) if content else 1
    service.documents().batchUpdate(
        documentId=document_id,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": end_index},
                        "text": text if text.endswith("\n") else text + "\n",
                    }
                }
            ]
        },
    ).execute()
    return {"id": document_id, "appended": True, "chars": len(text)}


def delete_doc(document_id: str, *, permanent: bool = False) -> dict[str, Any]:
    """Supprime un Google Doc via Drive."""
    return delete_file(document_id, permanent=permanent)


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------


def list_sheets(max_results: int = 20, query: str = "") -> list[dict[str, Any]]:
    """Liste ou cherche les Google Sheets recents via Drive."""
    return _drive_files_by_mime(GOOGLE_SHEET_MIME, query=query, max_results=max_results)


def create_sheet(title: str) -> dict[str, Any]:
    """Cree un Google Sheet vide."""
    sheet = (
        build_google_service("sheets", "v4")
        .spreadsheets()
        .create(body={"properties": {"title": title}})
        .execute()
    )
    return {
        "id": sheet.get("spreadsheetId"),
        "title": sheet.get("properties", {}).get("title"),
        "url": sheet.get("spreadsheetUrl"),
    }


def read_sheet(spreadsheet_id: str, range_name: str = "A1:Z50") -> dict[str, Any]:
    """Lit une plage de cellules Google Sheets."""
    result = (
        build_google_service("sheets", "v4")
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_name)
        .execute()
    )
    return {
        "id": spreadsheet_id,
        "range": result.get("range", range_name),
        "values": result.get("values", []),
    }


def append_sheet_row(
    spreadsheet_id: str,
    values: list[str],
    range_name: str = "A1",
) -> dict[str, Any]:
    """Ajoute une ligne dans un Google Sheet."""
    result = (
        build_google_service("sheets", "v4")
        .spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [values]},
        )
        .execute()
    )
    return {
        "id": spreadsheet_id,
        "updatedRange": result.get("updates", {}).get("updatedRange"),
        "updatedCells": result.get("updates", {}).get("updatedCells"),
    }


def update_sheet_values(
    spreadsheet_id: str,
    values: list[list[Any]],
    range_name: str = "A1",
) -> dict[str, Any]:
    """Remplace une plage Google Sheets par des valeurs."""
    result = (
        build_google_service("sheets", "v4")
        .spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        )
        .execute()
    )
    return {
        "id": spreadsheet_id,
        "updatedRange": result.get("updatedRange"),
        "updatedRows": result.get("updatedRows"),
        "updatedColumns": result.get("updatedColumns"),
        "updatedCells": result.get("updatedCells"),
    }


def clear_sheet_values(spreadsheet_id: str, range_name: str = "A1:Z1000") -> dict[str, Any]:
    """Vide une plage Google Sheets."""
    result = (
        build_google_service("sheets", "v4")
        .spreadsheets()
        .values()
        .clear(spreadsheetId=spreadsheet_id, range=range_name, body={})
        .execute()
    )
    return {"id": spreadsheet_id, "clearedRange": result.get("clearedRange")}


def delete_sheet(spreadsheet_id: str, *, permanent: bool = False) -> dict[str, Any]:
    """Supprime un Google Sheet via Drive."""
    return delete_file(spreadsheet_id, permanent=permanent)


# ---------------------------------------------------------------------------
# Google Keep
# ---------------------------------------------------------------------------


KEEP_DISCOVERY_URL = "https://keep.googleapis.com/$discovery/rest?version=v1"


def _keep_service() -> Any:
    if os.environ.get("NANOBOT_ENABLE_KEEP_API", "").lower() not in ("1", "true", "yes"):
        raise GoogleAuthError(
            "Google Keep est code dans Nanobot, mais Google bloque le scope Keep "
            "sur ce compte/app OAuth. Les API Gmail, Calendar, Drive, Tasks, "
            "Contacts, Docs et Sheets restent utilisables. Pour retester Keep plus "
            "tard avec un compte Google Workspace compatible, mets "
            "NANOBOT_ENABLE_KEEP_API=1 puis relance setup_google_auth.py."
        )
    return build_google_service(
        "keep",
        "v1",
        discovery_service_url=KEEP_DISCOVERY_URL,
    )


def _keep_note_name(note_id_or_name: str) -> str:
    return note_id_or_name if note_id_or_name.startswith("notes/") else f"notes/{note_id_or_name}"


def _keep_note_text(note: dict[str, Any]) -> str:
    body = note.get("body", {})
    text = body.get("text", {}).get("text")
    if text:
        return text
    list_items = body.get("list", {}).get("listItems", []) or []
    lines = []
    for item in list_items:
        checked = "x" if item.get("checked") else " "
        value = item.get("text", {}).get("text", "")
        if value:
            lines.append(f"[{checked}] {value}")
    return "\n".join(lines)


def _keep_summary(note: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": note.get("name"),
        "id": str(note.get("name", "")).removeprefix("notes/"),
        "title": note.get("title", ""),
        "text": _keep_note_text(note),
        "createTime": note.get("createTime", ""),
        "updateTime": note.get("updateTime", ""),
        "trashed": bool(note.get("trashed")),
    }


def list_keep_notes(max_results: int = 20, query: str = "") -> list[dict[str, Any]]:
    """Liste les notes Google Keep accessibles a l'API."""
    result = _keep_service().notes().list(pageSize=max_results).execute()
    notes = [_keep_summary(note) for note in result.get("notes", [])]
    if query:
        needle = _normalize(query)
        notes = [
            note
            for note in notes
            if needle in _normalize(note.get("title", ""))
            or needle in _normalize(note.get("text", ""))
        ]
    return notes


def read_keep_note(note_id_or_name: str) -> dict[str, Any]:
    """Lit une note Google Keep par nom ou ID."""
    note = _keep_service().notes().get(name=_keep_note_name(note_id_or_name)).execute()
    return _keep_summary(note)


def create_keep_note(title: str, text: str = "") -> dict[str, Any]:
    """Cree une note texte Google Keep."""
    body = {
        "title": title or "Note Nanobot",
        "body": {"text": {"text": text or ""}},
    }
    note = _keep_service().notes().create(body=body).execute()
    return _keep_summary(note)


def delete_keep_note(note_id_or_name: str) -> dict[str, Any]:
    """Supprime une note Google Keep par nom ou ID."""
    name = _keep_note_name(note_id_or_name)
    _keep_service().notes().delete(name=name).execute()
    return {"name": name, "deleted": True}


def format_emails(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Aucun email trouve."
    return "\n".join(
        f"- {item.get('subject')} | {item.get('from')} | {item.get('date')} | id={item.get('id')}"
        for item in items
    )


def format_events(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Aucun evenement trouve."
    return "\n".join(
        f"- {item.get('start')} -> {item.get('title')} | id={item.get('id')}"
        for item in items
    )


def format_files(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Aucun fichier Drive trouve."
    return "\n".join(
        f"- {item.get('name')} | {item.get('mimeType')} | id={item.get('id')}"
        for item in items
    )


def format_tasks(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Aucune tache trouvee."
    return "\n".join(
        f"- [{item.get('status')}] {item.get('title')} | due={item.get('due') or '-'} | id={item.get('id')}"
        for item in items
    )


def format_contacts(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Aucun contact trouve."
    lines = []
    for item in items:
        email = ", ".join(item.get("emails", [])) or "-"
        phone = ", ".join(item.get("phones", [])) or "-"
        lines.append(f"- {item.get('name') or '(sans nom)'} | {email} | {phone} | id={item.get('resourceName')}")
    return "\n".join(lines)


def format_docs(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Aucun Google Doc trouve."
    return "\n".join(
        f"- {item.get('name') or item.get('title')} | id={item.get('id')}"
        for item in items
    )


def format_sheets(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Aucun Google Sheet trouve."
    return "\n".join(
        f"- {item.get('name') or item.get('title')} | id={item.get('id')}"
        for item in items
    )


def format_sheet_values(values: list[list[Any]]) -> str:
    if not values:
        return "La plage Google Sheets est vide."
    return "\n".join(" | ".join(str(cell) for cell in row) for row in values)


def format_keep_notes(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Aucune note Keep trouvee."
    lines = []
    for item in items:
        preview = _clean_ws(item.get("text", ""))[:80]
        suffix = f" | {preview}" if preview else ""
        lines.append(f"- {item.get('title') or '(sans titre)'}{suffix} | id={item.get('id')}")
    return "\n".join(lines)


def _email_address(prompt: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", prompt)
    return match.group(0) if match else None


def _body_after_marker(prompt: str) -> str:
    match = re.search(
        r"(?:pour dire|disant|message|contenu)\s+(.+)$",
        prompt,
        flags=re.IGNORECASE,
    )
    return _clean_ws(match.group(1)) if match else ""


def _time_in_prompt(prompt: str) -> str | None:
    match = re.search(r"\b(\d{1,2}\s*(?:h|:)\s*\d{0,2})\b", prompt, flags=re.IGNORECASE)
    return match.group(1).replace(" ", "") if match else None


def _date_in_prompt(prompt: str) -> str | None:
    p = _normalize(prompt)
    for word in ("demain", "apres demain", "apres-demain", "aujourd'hui", "aujourdhui"):
        if word in p:
            return word
    for word in WEEKDAYS:
        if word in p:
            return word
    match = re.search(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})\b", prompt)
    return match.group(1) if match else None


def _duration_in_prompt(prompt: str) -> int:
    match = re.search(r"\b(\d+)\s*(min|mn|h|heure|heures)\b", _normalize(prompt))
    if not match:
        return 60
    value = int(match.group(1))
    unit = match.group(2)
    return value * 60 if unit.startswith("h") else value


def _event_title(prompt: str) -> str:
    p = _normalize(prompt)
    if "reunion" in p:
        return "Reunion"
    if "rdv" in p or "rendez-vous" in p:
        return "Rendez-vous"
    if "appel" in p:
        return "Appel"
    return "Evenement Nanobot"


def _task_title(prompt: str) -> str:
    text = re.sub(
        r"(?i)\b(ajoute|cree|creer|mets|mettre|une|un|tache|todo|task)\b",
        " ",
        prompt,
    )
    text = re.sub(r"(?i)\b(pour|a faire|dans tasks?)\b", " ", text)
    return _clean_ws(text) or "Tache Nanobot"


def _phone_in_prompt(prompt: str) -> str | None:
    match = re.search(r"(?:\+?\d[\d .-]{7,}\d)", prompt)
    return _clean_ws(match.group(0)) if match else None


def _after_any_marker(prompt: str, markers: tuple[str, ...]) -> str:
    marker_re = "|".join(re.escape(marker) for marker in markers)
    match = re.search(rf"(?:{marker_re})\s+(.+)$", prompt, flags=re.IGNORECASE)
    return _clean_ws(match.group(1)) if match else ""


def _title_after_prompt(prompt: str, default: str) -> str:
    text = _after_any_marker(
        prompt,
        (
            "appele",
            "appelee",
            "titre",
            "nomme",
            "nommee",
            "avec le titre",
            "qui s'appelle",
        ),
    )
    return text or default


def _extract_id(prompt: str) -> str | None:
    match = re.search(r"\b([A-Za-z0-9_-]{8,}|notes/[A-Za-z0-9_-]+)\b", prompt)
    return match.group(1) if match else None


def _contact_name_from_prompt(prompt: str) -> str:
    text = re.sub(
        r"(?i)\b(ajoute|cree|creer|contact|contacts|avec|email|mail|telephone|tel|numero)\b",
        " ",
        prompt,
    )
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", " ", text)
    phone = _phone_in_prompt(prompt)
    if phone:
        text = text.replace(phone, " ")
    return _clean_ws(text) or "Contact Nanobot"


def _keep_title_and_body(prompt: str) -> tuple[str, str]:
    body = _body_after_marker(prompt)
    title = _title_after_prompt(prompt, "Note Nanobot")
    if not body:
        body = _after_any_marker(prompt, ("note", "keep"))
        body = re.sub(r"(?i)\b(google|keep|cree|creer|ajoute|une|note)\b", " ", body)
        body = _clean_ws(body)
    return title, body


def handle_google_prompt(prompt: str) -> dict[str, Any]:
    """Execute une demande naturelle simple liee a Google Workspace."""
    started = time_module.time()
    p = _normalize(prompt)
    try:
        if _contains_any(p, ("contact", "contacts")):
            if _contains_any(p, ("ajoute", "cree", "creer")):
                data = create_contact(
                    _contact_name_from_prompt(prompt),
                    email=_email_address(prompt),
                    phone=_phone_in_prompt(prompt),
                )
                text = f"Contact cree: {data.get('name')} id={data.get('resourceName')}"
                tool = "contacts.create_contact"
            elif _contains_any(p, ("cherche", "search", "recherche")):
                query = _after_any_marker(prompt, ("cherche", "recherche", "contact", "contacts"))
                data = search_contacts(query or prompt)
                text = format_contacts(data)
                tool = "contacts.search_contacts"
            else:
                data = list_contacts()
                text = format_contacts(data)
                tool = "contacts.list_contacts"

        elif _contains_any(p, ("gmail", "mail", "email", "courriel")):
            if _contains_any(p, ("envoie", "envoyer", "send")):
                to = _email_address(prompt)
                body = _body_after_marker(prompt)
                if not to or not body:
                    return {
                        "ok": False,
                        "agent": "google",
                        "error": "Pour envoyer, precise une adresse email et le message.",
                        "text": "Exemple: Envoie un mail a nom@example.com pour dire Bonjour.",
                    }
                data = send_email(to, "Message de Nanobot", body)
                text = f"Email envoye a {to}. id={data.get('id')}"
                tool = "gmail.send_email"
            elif _contains_any(p, ("labels", "libelles", "libellés")):
                data = list_gmail_labels()
                text = "\n".join(f"- {item.get('name')} | id={item.get('id')}" for item in data) or "Aucun label Gmail."
                tool = "gmail.list_labels"
            elif _contains_any(p, ("supprime", "delete", "corbeille", "trash", "archive", "classe", "label", "marque")):
                msg_id = _extract_id(prompt)
                if not msg_id:
                    return {
                        "ok": False,
                        "agent": "google",
                        "error": "ID Gmail manquant.",
                        "text": "Donne l'id Gmail du message a classer, archiver, marquer ou supprimer.",
                    }
                if _contains_any(p, ("supprime", "delete", "corbeille", "trash")):
                    data = delete_email(msg_id, permanent="permanent" in p)
                    text = f"Email supprime/deplace: id={msg_id}"
                    tool = "gmail.delete_email"
                elif "archive" in p:
                    data = archive_email(msg_id)
                    text = f"Email archive: id={msg_id}"
                    tool = "gmail.archive_email"
                elif "non lu" in p or "unread" in p:
                    data = mark_email_read(msg_id, read=False)
                    text = f"Email marque non lu: id={msg_id}"
                    tool = "gmail.mark_unread"
                elif "lu" in p or "read" in p:
                    data = mark_email_read(msg_id, read=True)
                    text = f"Email marque lu: id={msg_id}"
                    tool = "gmail.mark_read"
                else:
                    label = _after_any_marker(prompt, ("label", "libelle", "libellé", "classe dans", "classer dans"))
                    data = move_email_to_label(msg_id, label or "Nanobot", archive=True, create_missing_label=True)
                    text = f"Email classe sous {label or 'Nanobot'}: id={msg_id}"
                    tool = "gmail.move_to_label"
            elif _contains_any(p, ("cherche", "search", "recherche")):
                data = search_emails(prompt)
                text = format_emails(data)
                tool = "gmail.search_emails"
            else:
                data = list_emails()
                text = format_emails(data)
                tool = "gmail.list_emails"

        elif _contains_any(p, ("agenda", "calendrier", "calendar", "evenement", "reunion", "rdv")):
            wants_create = _contains_any(p, ("mets", "ajoute", "cree", "creer", "planifie"))
            if wants_create:
                day = _date_in_prompt(prompt)
                clock = _time_in_prompt(prompt)
                if not day or not clock:
                    return {
                        "ok": False,
                        "agent": "google",
                        "error": "Pour creer un evenement, precise une date et une heure.",
                        "text": "Exemple: Mets une reunion jeudi a 14h.",
                    }
                data = create_event(_event_title(prompt), day, clock, _duration_in_prompt(prompt))
                text = f"Evenement cree: {data.get('title')} le {data.get('start')} id={data.get('id')}"
                tool = "calendar.create_event"
            else:
                if "demain" in p:
                    data = list_events(days=1, start_date="demain")
                elif "aujourd" in p or "today" in p:
                    data = list_events(days=1, start_date="aujourdhui")
                else:
                    data = list_events(days=7)
                text = format_events(data)
                tool = "calendar.list_events"

        elif "drive" in p:
            data = list_files()
            text = format_files(data)
            tool = "drive.list_files"

        elif _contains_any(p, ("google docs", "docs", "document google")):
            if _contains_any(p, ("cree", "creer", "ajoute", "nouveau")):
                data = create_doc(_title_after_prompt(prompt, "Document Nanobot"))
                text = f"Google Doc cree: {data.get('title')} id={data.get('id')}"
                tool = "docs.create_doc"
            elif _has_word(p, ("lis", "lire", "read")):
                doc_id = _extract_id(prompt)
                if not doc_id:
                    return {
                        "ok": False,
                        "agent": "google",
                        "error": "ID Google Doc manquant.",
                        "text": "Donne l'id du Google Doc a lire.",
                    }
                data = read_doc(doc_id)
                text = data.get("text") or "Google Doc vide."
                tool = "docs.read_doc"
            else:
                data = list_docs()
                text = format_docs(data)
                tool = "docs.list_docs"

        elif _contains_any(p, ("google sheets", "sheets", "sheet", "tableur")):
            if _contains_any(p, ("cree", "creer", "ajoute", "nouveau")):
                data = create_sheet(_title_after_prompt(prompt, "Tableur Nanobot"))
                text = f"Google Sheet cree: {data.get('title')} id={data.get('id')}"
                tool = "sheets.create_sheet"
            elif _has_word(p, ("lis", "lire", "read")):
                sheet_id = _extract_id(prompt)
                if not sheet_id:
                    return {
                        "ok": False,
                        "agent": "google",
                        "error": "ID Google Sheet manquant.",
                        "text": "Donne l'id du Google Sheet a lire.",
                    }
                data = read_sheet(sheet_id)
                text = format_sheet_values(data.get("values", []))
                tool = "sheets.read_sheet"
            else:
                data = list_sheets()
                text = format_sheets(data)
                tool = "sheets.list_sheets"

        elif "keep" in p or ("note" in p and "google" in p):
            if _contains_any(p, ("cree", "creer", "ajoute", "nouvelle")):
                title, body = _keep_title_and_body(prompt)
                data = create_keep_note(title, body)
                text = f"Note Keep creee: {data.get('title')} id={data.get('id')}"
                tool = "keep.create_keep_note"
            elif _has_word(p, ("lis", "lire", "read")):
                note_id = _extract_id(prompt)
                if not note_id:
                    return {
                        "ok": False,
                        "agent": "google",
                        "error": "ID Keep manquant.",
                        "text": "Donne l'id de la note Keep a lire.",
                    }
                data = read_keep_note(note_id)
                text = data.get("text") or "Note Keep vide."
                tool = "keep.read_keep_note"
            elif _contains_any(p, ("supprime", "delete", "efface")):
                note_id = _extract_id(prompt)
                if not note_id:
                    return {
                        "ok": False,
                        "agent": "google",
                        "error": "ID Keep manquant.",
                        "text": "Donne l'id de la note Keep a supprimer.",
                    }
                data = delete_keep_note(note_id)
                text = f"Note Keep supprimee: {data.get('name')}"
                tool = "keep.delete_keep_note"
            else:
                data = list_keep_notes()
                text = format_keep_notes(data)
                tool = "keep.list_keep_notes"

        elif _contains_any(p, ("tache", "taches", "task", "tasks", "todo")):
            if _contains_any(p, ("ajoute", "cree", "creer", "mets")):
                data = add_task(_task_title(prompt), due_date=_date_in_prompt(prompt))
                text = f"Tache ajoutee: {data.get('title')} id={data.get('id')}"
                tool = "tasks.add_task"
            elif _contains_any(p, ("termine", "complete", "finis")):
                match = re.search(r"\b([A-Za-z0-9_-]{8,})\b", prompt)
                if not match:
                    return {
                        "ok": False,
                        "agent": "google",
                        "error": "ID de tache manquant.",
                        "text": "Donne l'id de la tache a terminer.",
                    }
                data = complete_task(match.group(1))
                text = f"Tache terminee: {data.get('title')} id={data.get('id')}"
                tool = "tasks.complete_task"
            else:
                data = list_tasks()
                text = format_tasks(data)
                tool = "tasks.list_tasks"
        else:
            return {
                "ok": False,
                "agent": "google",
                "error": "Demande Google non reconnue.",
                "text": "Je peux lire Gmail, Calendar, Drive, Tasks, Contacts, Docs, Sheets et Keep.",
            }

        return {
            "ok": True,
            "agent": "google",
            "tool": tool,
            "text": text,
            "data": data,
            "duration_ms": int((time_module.time() - started) * 1000),
        }
    except GoogleAuthError as exc:
        return {
            "ok": False,
            "agent": "google",
            "error": str(exc),
            "text": str(exc),
            "duration_ms": int((time_module.time() - started) * 1000),
        }
    except Exception as exc:
        return {
            "ok": False,
            "agent": "google",
            "error": _json_error(exc),
            "text": f"Erreur Google: {_json_error(exc)}",
            "duration_ms": int((time_module.time() - started) * 1000),
        }
