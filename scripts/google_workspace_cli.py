#!/usr/bin/env python
"""Mini CLI Google pour Nanobot: Gmail, Calendar, Drive, Tasks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

OMEGA_ROOT = Path(__file__).resolve().parents[1]
if str(OMEGA_ROOT) not in sys.path:
    sys.path.insert(0, str(OMEGA_ROOT))

from google_auth import auth_status
from tools import google_tools as gt


def _print(data: Any, *, as_json: bool = False, formatter=None) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    elif formatter:
        print(formatter(data))
    elif isinstance(data, (dict, list)):
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(data)


def _read_body_arg(value: str | None) -> str:
    if value:
        return value
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return input("Message: ").strip()


def _split_row(value: str) -> list[str]:
    return [part.strip() for part in value.split(",")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Google CLI leger pour Nanobot.")
    parser.add_argument("--json", action="store_true", help="Sortie JSON brute.")
    sub = parser.add_subparsers(dest="service")

    auth = sub.add_parser("auth", help="Etat OAuth")
    auth.add_argument("action", nargs="?", default="status", choices=["status", "refresh"])

    mail = sub.add_parser("mail", help="Gmail")
    mail.add_argument("--max", type=int, default=10)
    mail.add_argument("--query", default="")
    mail_sub = mail.add_subparsers(dest="mail_cmd")
    mail_search = mail_sub.add_parser("search", help="Chercher des emails")
    mail_search.add_argument("query", nargs=argparse.REMAINDER)
    mail_read = mail_sub.add_parser("read", help="Lire un email")
    mail_read.add_argument("id")
    mail_send = mail_sub.add_parser("send", help="Envoyer un email")
    mail_send.add_argument("to")
    mail_send.add_argument("--subject", "-s", default="")
    mail_send.add_argument("--body", "-b", default="")
    mail_sub.add_parser("labels", help="Lister les labels Gmail")
    mail_label_create = mail_sub.add_parser("create-label", help="Creer un label Gmail")
    mail_label_create.add_argument("name")
    mail_label_delete = mail_sub.add_parser("delete-label", help="Supprimer un label Gmail")
    mail_label_delete.add_argument("name_or_id")
    mail_label = mail_sub.add_parser("label", help="Ajouter/retirer des labels sur un email")
    mail_label.add_argument("id")
    mail_label.add_argument("--add", nargs="*", default=[])
    mail_label.add_argument("--remove", nargs="*", default=[])
    mail_label.add_argument("--create-missing", action="store_true")
    mail_read_state = mail_sub.add_parser("mark", help="Marquer lu/non lu")
    mail_read_state.add_argument("id")
    mail_read_state.add_argument("--read", action="store_true")
    mail_read_state.add_argument("--unread", action="store_true")
    mail_archive = mail_sub.add_parser("archive", help="Archiver un email")
    mail_archive.add_argument("id")
    mail_move = mail_sub.add_parser("move", help="Classer un email sous un label")
    mail_move.add_argument("id")
    mail_move.add_argument("--label", required=True)
    mail_move.add_argument("--keep-inbox", action="store_true")
    mail_trash = mail_sub.add_parser("trash", help="Mettre un email a la corbeille")
    mail_trash.add_argument("id")
    mail_untrash = mail_sub.add_parser("untrash", help="Restaurer un email depuis la corbeille")
    mail_untrash.add_argument("id")
    mail_delete = mail_sub.add_parser("delete", help="Supprimer un email")
    mail_delete.add_argument("id")
    mail_delete.add_argument("--permanent", action="store_true")

    cal = sub.add_parser("cal", help="Google Calendar")
    cal_sub = cal.add_subparsers(dest="cal_cmd")
    cal_sub.add_parser("today", help="Agenda du jour")
    cal_sub.add_parser("tomorrow", help="Agenda de demain")
    cal_sub.add_parser("week", help="Agenda 7 jours")
    cal_create = cal_sub.add_parser("create", help="Creer un evenement")
    cal_create.add_argument("title")
    cal_create.add_argument("--date", required=True, help="YYYY-MM-DD, demain, jeudi...")
    cal_create.add_argument("--time", required=True, help="14h, 14:30...")
    cal_create.add_argument("--duration", type=int, default=60, help="Minutes")
    cal_delete = cal_sub.add_parser("delete", help="Supprimer un evenement")
    cal_delete.add_argument("id")

    drive = sub.add_parser("drive", help="Google Drive")
    drive_sub = drive.add_subparsers(dest="drive_cmd")
    drive_ls = drive_sub.add_parser("ls", help="Lister Drive")
    drive_ls.add_argument("--folder", default=None)
    drive_ls.add_argument("--max", type=int, default=20)
    drive_search = drive_sub.add_parser("search", help="Chercher dans Drive")
    drive_search.add_argument("query")
    drive_search.add_argument("--max", type=int, default=20)
    drive_folder = drive_sub.add_parser("mkdir", help="Creer un dossier Drive")
    drive_folder.add_argument("name")
    drive_folder.add_argument("--parent", default=None)
    drive_read = drive_sub.add_parser("read", help="Lire/exporter un fichier")
    drive_read.add_argument("id")
    drive_upload = drive_sub.add_parser("upload", help="Uploader un fichier")
    drive_upload.add_argument("path")
    drive_upload.add_argument("--folder", default=None)
    drive_meta = drive_sub.add_parser("metadata", help="Modifier les metadonnees Drive")
    drive_meta.add_argument("id")
    drive_meta.add_argument("--name")
    drive_meta.add_argument("--description")
    drive_meta.add_argument("--starred", choices=["true", "false"])
    drive_move = drive_sub.add_parser("move", help="Deplacer un fichier Drive")
    drive_move.add_argument("id")
    drive_move.add_argument("--folder", required=True)
    drive_delete = drive_sub.add_parser("delete", help="Mettre a la corbeille un fichier Drive")
    drive_delete.add_argument("id")
    drive_delete.add_argument("--permanent", action="store_true")

    tasks = sub.add_parser("tasks", help="Google Tasks")
    tasks_sub = tasks.add_subparsers(dest="tasks_cmd")
    tasks_add = tasks_sub.add_parser("add", help="Ajouter une tache")
    tasks_add.add_argument("title")
    tasks_add.add_argument("--due", default=None)
    tasks_done = tasks_sub.add_parser("complete", help="Terminer une tache")
    tasks_done.add_argument("id")

    contacts = sub.add_parser("contacts", help="Google Contacts")
    contacts.add_argument("--max", type=int, default=20)
    contacts_sub = contacts.add_subparsers(dest="contacts_cmd")
    contacts_search = contacts_sub.add_parser("search", help="Chercher un contact")
    contacts_search.add_argument("query")
    contacts_add = contacts_sub.add_parser("add", help="Creer un contact")
    contacts_add.add_argument("name")
    contacts_add.add_argument("--email", default=None)
    contacts_add.add_argument("--phone", default=None)

    docs = sub.add_parser("docs", help="Google Docs")
    docs.add_argument("--max", type=int, default=20)
    docs.add_argument("--query", default="")
    docs_sub = docs.add_subparsers(dest="docs_cmd")
    docs_create = docs_sub.add_parser("create", help="Creer un Doc")
    docs_create.add_argument("title")
    docs_read = docs_sub.add_parser("read", help="Lire un Doc")
    docs_read.add_argument("id")
    docs_append = docs_sub.add_parser("append", help="Ajouter du texte a un Doc")
    docs_append.add_argument("id")
    docs_append.add_argument("text")
    docs_delete = docs_sub.add_parser("delete", help="Mettre a la corbeille un Doc")
    docs_delete.add_argument("id")
    docs_delete.add_argument("--permanent", action="store_true")

    sheets = sub.add_parser("sheets", help="Google Sheets")
    sheets.add_argument("--max", type=int, default=20)
    sheets.add_argument("--query", default="")
    sheets_sub = sheets.add_subparsers(dest="sheets_cmd")
    sheets_create = sheets_sub.add_parser("create", help="Creer un Sheet")
    sheets_create.add_argument("title")
    sheets_read = sheets_sub.add_parser("read", help="Lire une plage")
    sheets_read.add_argument("id")
    sheets_read.add_argument("--range", default="A1:Z50")
    sheets_append = sheets_sub.add_parser("append-row", help="Ajouter une ligne CSV")
    sheets_append.add_argument("id")
    sheets_append.add_argument("values", help="Valeurs separees par virgules")
    sheets_append.add_argument("--range", default="A1")
    sheets_update = sheets_sub.add_parser("update", help="Remplacer une plage avec JSON rows")
    sheets_update.add_argument("id")
    sheets_update.add_argument("values_json", help="JSON: [[\"A\",\"B\"],[\"1\",\"2\"]]")
    sheets_update.add_argument("--range", default="A1")
    sheets_clear = sheets_sub.add_parser("clear", help="Vider une plage")
    sheets_clear.add_argument("id")
    sheets_clear.add_argument("--range", default="A1:Z1000")
    sheets_delete = sheets_sub.add_parser("delete", help="Mettre a la corbeille un Sheet")
    sheets_delete.add_argument("id")
    sheets_delete.add_argument("--permanent", action="store_true")

    keep = sub.add_parser("keep", help="Google Keep")
    keep.add_argument("--max", type=int, default=20)
    keep.add_argument("--query", default="")
    keep_sub = keep.add_subparsers(dest="keep_cmd")
    keep_create = keep_sub.add_parser("create", help="Creer une note Keep")
    keep_create.add_argument("title")
    keep_create.add_argument("--text", default="")
    keep_read = keep_sub.add_parser("read", help="Lire une note Keep")
    keep_read.add_argument("id")
    keep_delete = keep_sub.add_parser("delete", help="Supprimer une note Keep")
    keep_delete.add_argument("id")

    args = parser.parse_args()

    try:
        if args.service == "auth":
            if args.action == "refresh":
                try:
                    from google_auth import load_credentials
                    creds = load_credentials(interactive=False)
                    _print({"ok": True, "valid": bool(creds.valid), "expiry": str(getattr(creds, "expiry", None)), "has_refresh_token": bool(creds.refresh_token)}, as_json=args.json)
                except Exception as exc:
                    _print({"ok": False, "error": str(exc)}, as_json=args.json)
            else:
                _print(auth_status(), as_json=args.json)

        elif args.service == "mail":
            if args.mail_cmd == "search":
                query = " ".join(args.query).strip()
                _print(gt.search_emails(query, max_results=args.max), as_json=args.json, formatter=gt.format_emails)
            elif args.mail_cmd == "read":
                data = gt.read_email(args.id)
                if args.json:
                    _print(data, as_json=True)
                else:
                    print(f"{data.get('subject')} | {data.get('from')} | {data.get('date')}")
                    print("")
                    print(data.get("body", ""))
            elif args.mail_cmd == "send":
                subject = args.subject or input("Sujet: ").strip()
                body = _read_body_arg(args.body)
                _print(gt.send_email(args.to, subject, body), as_json=args.json)
            elif args.mail_cmd == "labels":
                _print(gt.list_gmail_labels(), as_json=args.json)
            elif args.mail_cmd == "create-label":
                _print(gt.create_gmail_label(args.name), as_json=args.json)
            elif args.mail_cmd == "delete-label":
                _print(gt.delete_gmail_label(args.name_or_id), as_json=args.json)
            elif args.mail_cmd == "label":
                _print(
                    gt.modify_email_labels(
                        args.id,
                        add=args.add,
                        remove=args.remove,
                        create_missing_labels=args.create_missing,
                    ),
                    as_json=args.json,
                )
            elif args.mail_cmd == "mark":
                if args.read == args.unread:
                    raise ValueError("Choisis --read ou --unread.")
                _print(gt.mark_email_read(args.id, read=bool(args.read)), as_json=args.json)
            elif args.mail_cmd == "archive":
                _print(gt.archive_email(args.id), as_json=args.json)
            elif args.mail_cmd == "move":
                _print(
                    gt.move_email_to_label(
                        args.id,
                        args.label,
                        archive=not args.keep_inbox,
                        create_missing_label=True,
                    ),
                    as_json=args.json,
                )
            elif args.mail_cmd == "trash":
                _print(gt.trash_email(args.id), as_json=args.json)
            elif args.mail_cmd == "untrash":
                _print(gt.untrash_email(args.id), as_json=args.json)
            elif args.mail_cmd == "delete":
                _print(gt.delete_email(args.id, permanent=args.permanent), as_json=args.json)
            else:
                _print(
                    gt.list_emails(max_results=args.max, query=args.query),
                    as_json=args.json,
                    formatter=gt.format_emails,
                )

        elif args.service == "cal":
            if args.cal_cmd == "today":
                _print(gt.list_events(days=1, start_date="aujourdhui"), as_json=args.json, formatter=gt.format_events)
            elif args.cal_cmd == "tomorrow":
                _print(gt.list_events(days=1, start_date="demain"), as_json=args.json, formatter=gt.format_events)
            elif args.cal_cmd == "create":
                _print(gt.create_event(args.title, args.date, args.time, args.duration), as_json=args.json)
            elif args.cal_cmd == "delete":
                _print(gt.delete_event(args.id), as_json=args.json)
            else:
                _print(gt.list_events(days=7), as_json=args.json, formatter=gt.format_events)

        elif args.service == "drive":
            if args.drive_cmd == "search":
                _print(gt.search_files(args.query, max_results=args.max), as_json=args.json, formatter=gt.format_files)
            elif args.drive_cmd == "mkdir":
                _print(gt.create_folder(args.name, parent=args.parent), as_json=args.json)
            elif args.drive_cmd == "read":
                data = gt.read_file(args.id)
                if args.json:
                    _print(data, as_json=True)
                else:
                    print(f"{data.get('name')} | {data.get('mimeType')}")
                    print("")
                    print(data.get("text", ""))
            elif args.drive_cmd == "upload":
                _print(gt.upload_file(args.path, folder=args.folder), as_json=args.json)
            elif args.drive_cmd == "metadata":
                starred = None if args.starred is None else args.starred == "true"
                _print(
                    gt.update_file_metadata(
                        args.id,
                        name=args.name,
                        description=args.description,
                        starred=starred,
                    ),
                    as_json=args.json,
                )
            elif args.drive_cmd == "move":
                _print(gt.move_file(args.id, args.folder), as_json=args.json)
            elif args.drive_cmd == "delete":
                _print(gt.delete_file(args.id, permanent=args.permanent), as_json=args.json)
            else:
                _print(
                    gt.list_files(folder=getattr(args, "folder", None), max=getattr(args, "max", 20)),
                    as_json=args.json,
                    formatter=gt.format_files,
                )

        elif args.service == "tasks":
            if args.tasks_cmd == "add":
                _print(gt.add_task(args.title, due_date=args.due), as_json=args.json)
            elif args.tasks_cmd == "complete":
                _print(gt.complete_task(args.id), as_json=args.json)
            else:
                _print(gt.list_tasks(), as_json=args.json, formatter=gt.format_tasks)

        elif args.service == "contacts":
            if args.contacts_cmd == "search":
                _print(
                    gt.search_contacts(args.query, max_results=args.max),
                    as_json=args.json,
                    formatter=gt.format_contacts,
                )
            elif args.contacts_cmd == "add":
                _print(gt.create_contact(args.name, email=args.email, phone=args.phone), as_json=args.json)
            else:
                _print(gt.list_contacts(max_results=args.max), as_json=args.json, formatter=gt.format_contacts)

        elif args.service == "docs":
            if args.docs_cmd == "create":
                _print(gt.create_doc(args.title), as_json=args.json)
            elif args.docs_cmd == "read":
                data = gt.read_doc(args.id)
                if args.json:
                    _print(data, as_json=True)
                else:
                    print(f"{data.get('title')} | id={data.get('id')}")
                    print("")
                    print(data.get("text", ""))
            elif args.docs_cmd == "append":
                _print(gt.append_doc(args.id, args.text), as_json=args.json)
            elif args.docs_cmd == "delete":
                _print(gt.delete_doc(args.id, permanent=args.permanent), as_json=args.json)
            else:
                _print(
                    gt.list_docs(max_results=args.max, query=args.query),
                    as_json=args.json,
                    formatter=gt.format_docs,
                )

        elif args.service == "sheets":
            if args.sheets_cmd == "create":
                _print(gt.create_sheet(args.title), as_json=args.json)
            elif args.sheets_cmd == "read":
                data = gt.read_sheet(args.id, range_name=args.range)
                if args.json:
                    _print(data, as_json=True)
                else:
                    print(gt.format_sheet_values(data.get("values", [])))
            elif args.sheets_cmd == "append-row":
                _print(gt.append_sheet_row(args.id, _split_row(args.values), range_name=args.range), as_json=args.json)
            elif args.sheets_cmd == "update":
                values = json.loads(args.values_json)
                _print(gt.update_sheet_values(args.id, values, range_name=args.range), as_json=args.json)
            elif args.sheets_cmd == "clear":
                _print(gt.clear_sheet_values(args.id, range_name=args.range), as_json=args.json)
            elif args.sheets_cmd == "delete":
                _print(gt.delete_sheet(args.id, permanent=args.permanent), as_json=args.json)
            else:
                _print(
                    gt.list_sheets(max_results=args.max, query=args.query),
                    as_json=args.json,
                    formatter=gt.format_sheets,
                )

        elif args.service == "keep":
            if args.keep_cmd == "create":
                _print(gt.create_keep_note(args.title, text=args.text), as_json=args.json)
            elif args.keep_cmd == "read":
                data = gt.read_keep_note(args.id)
                if args.json:
                    _print(data, as_json=True)
                else:
                    print(f"{data.get('title')} | id={data.get('id')}")
                    print("")
                    print(data.get("text", ""))
            elif args.keep_cmd == "delete":
                _print(gt.delete_keep_note(args.id), as_json=args.json)
            else:
                _print(
                    gt.list_keep_notes(max_results=args.max, query=args.query),
                    as_json=args.json,
                    formatter=gt.format_keep_notes,
                )
        else:
            parser.print_help()
            return 1
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"[ERREUR] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
