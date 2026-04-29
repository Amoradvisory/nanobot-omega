#!/usr/bin/env python
"""Local Google Workspace MCP server for Nanobot.

This server intentionally wraps the local Python Google API layer instead of the
external npm MCP package. It keeps auth local, returns parseable JSON-like
objects, and gives Nanobot a durable fallback when third-party MCP tool names
change or fail to load.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

OMEGA_ROOT = Path(__file__).resolve().parents[1]
if str(OMEGA_ROOT) not in sys.path:
    sys.path.insert(0, str(OMEGA_ROOT))

from google_auth import auth_status
from mcp.server.fastmcp import FastMCP
from tools import google_tools as gt

mcp = FastMCP("nanobot-google-workspace")


@mcp.tool()
def google_auth_status() -> dict[str, Any]:
    """Return local OAuth status for the Google Workspace account."""
    return auth_status()


@mcp.tool()
def google_natural(prompt: str) -> dict[str, Any]:
    """Execute a simple natural-language Google Workspace request."""
    return gt.handle_google_prompt(prompt)


@mcp.tool()
def gmail_search(query: str = "", max_results: int = 10) -> list[dict[str, Any]]:
    """Search Gmail messages using Gmail search syntax."""
    return gt.list_emails(max_results=max_results, query=query)


@mcp.tool()
def gmail_read(email_id: str) -> dict[str, Any]:
    """Read a Gmail message by id."""
    return gt.read_email(email_id)


@mcp.tool()
def gmail_send(to: str, subject: str, body: str) -> dict[str, Any]:
    """Send a plain-text Gmail message."""
    return gt.send_email(to, subject, body)


@mcp.tool()
def gmail_labels() -> list[dict[str, Any]]:
    """List Gmail labels."""
    return gt.list_gmail_labels()


@mcp.tool()
def gmail_create_label(name: str) -> dict[str, Any]:
    """Create a Gmail label."""
    return gt.create_gmail_label(name)


@mcp.tool()
def gmail_delete_label(name_or_id: str) -> dict[str, Any]:
    """Delete a user Gmail label."""
    return gt.delete_gmail_label(name_or_id)


@mcp.tool()
def gmail_modify_labels(
    email_id: str,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    create_missing_labels: bool = False,
) -> dict[str, Any]:
    """Add or remove labels on a Gmail message."""
    return gt.modify_email_labels(
        email_id,
        add=add,
        remove=remove,
        create_missing_labels=create_missing_labels,
    )


@mcp.tool()
def gmail_mark_read(email_id: str, read: bool = True) -> dict[str, Any]:
    """Mark a Gmail message as read or unread."""
    return gt.mark_email_read(email_id, read=read)


@mcp.tool()
def gmail_archive(email_id: str) -> dict[str, Any]:
    """Archive a Gmail message by removing INBOX."""
    return gt.archive_email(email_id)


@mcp.tool()
def gmail_move_to_label(
    email_id: str,
    label: str,
    archive: bool = True,
    create_missing_label: bool = True,
) -> dict[str, Any]:
    """Classify a Gmail message under a label."""
    return gt.move_email_to_label(
        email_id,
        label,
        archive=archive,
        create_missing_label=create_missing_label,
    )


@mcp.tool()
def gmail_trash(email_id: str) -> dict[str, Any]:
    """Move a Gmail message to trash."""
    return gt.trash_email(email_id)


@mcp.tool()
def gmail_untrash(email_id: str) -> dict[str, Any]:
    """Restore a Gmail message from trash."""
    return gt.untrash_email(email_id)


@mcp.tool()
def gmail_delete(email_id: str, permanent: bool = False) -> dict[str, Any]:
    """Trash by default, or permanently delete a Gmail message if requested."""
    return gt.delete_email(email_id, permanent=permanent)


@mcp.tool()
def calendar_list(days: int = 7, start_date: str | None = None) -> list[dict[str, Any]]:
    """List Google Calendar events."""
    return gt.list_events(days=days, start_date=start_date)


@mcp.tool()
def calendar_create(title: str, date: str, time: str, duration: int = 60) -> dict[str, Any]:
    """Create a Google Calendar event."""
    return gt.create_event(title, date, time, duration)


@mcp.tool()
def calendar_delete(event_id: str) -> dict[str, Any]:
    """Delete a Google Calendar event by id."""
    return gt.delete_event(event_id)


@mcp.tool()
def drive_list(folder: str | None = None, max_results: int = 20) -> list[dict[str, Any]]:
    """List recent Google Drive files or files in a folder."""
    return gt.list_files(folder=folder, max=max_results)


@mcp.tool()
def drive_search(query: str, max_results: int = 20, mime_type: str | None = None) -> list[dict[str, Any]]:
    """Search Google Drive files by name and optional MIME type."""
    return gt.search_files(query, max_results=max_results, mime_type=mime_type)


@mcp.tool()
def drive_read(file_id: str) -> dict[str, Any]:
    """Read/download or export a Google Drive file as text when possible."""
    return gt.read_file(file_id)


@mcp.tool()
def drive_upload(local_path: str, folder: str | None = None) -> dict[str, Any]:
    """Upload a local file to Google Drive."""
    return gt.upload_file(local_path, folder=folder)


@mcp.tool()
def drive_create_folder(name: str, parent: str | None = None) -> dict[str, Any]:
    """Create a Google Drive folder."""
    return gt.create_folder(name, parent=parent)


@mcp.tool()
def drive_update_metadata(
    file_id: str,
    name: str | None = None,
    description: str | None = None,
    starred: bool | None = None,
) -> dict[str, Any]:
    """Update simple Google Drive file metadata."""
    return gt.update_file_metadata(file_id, name=name, description=description, starred=starred)


@mcp.tool()
def drive_move(file_id: str, folder_id: str) -> dict[str, Any]:
    """Move a Google Drive file to a target folder."""
    return gt.move_file(file_id, folder_id)


@mcp.tool()
def drive_delete(file_id: str, permanent: bool = False) -> dict[str, Any]:
    """Trash a Google Drive file by default, or permanently delete if requested."""
    return gt.delete_file(file_id, permanent=permanent)


@mcp.tool()
def docs_list(query: str = "", max_results: int = 20) -> list[dict[str, Any]]:
    """List or search Google Docs."""
    return gt.list_docs(max_results=max_results, query=query)


@mcp.tool()
def docs_create(title: str) -> dict[str, Any]:
    """Create a Google Doc."""
    return gt.create_doc(title)


@mcp.tool()
def docs_read(document_id: str) -> dict[str, Any]:
    """Read a Google Doc."""
    return gt.read_doc(document_id)


@mcp.tool()
def docs_append(document_id: str, text: str) -> dict[str, Any]:
    """Append text to a Google Doc."""
    return gt.append_doc(document_id, text)


@mcp.tool()
def docs_delete(document_id: str, permanent: bool = False) -> dict[str, Any]:
    """Trash or permanently delete a Google Doc through Drive."""
    return gt.delete_doc(document_id, permanent=permanent)


@mcp.tool()
def sheets_list(query: str = "", max_results: int = 20) -> list[dict[str, Any]]:
    """List or search Google Sheets."""
    return gt.list_sheets(max_results=max_results, query=query)


@mcp.tool()
def sheets_create(title: str) -> dict[str, Any]:
    """Create a Google Sheet."""
    return gt.create_sheet(title)


@mcp.tool()
def sheets_read(spreadsheet_id: str, range_name: str = "A1:Z50") -> dict[str, Any]:
    """Read a Google Sheets range."""
    return gt.read_sheet(spreadsheet_id, range_name=range_name)


@mcp.tool()
def sheets_append_row(spreadsheet_id: str, values: list[str], range_name: str = "A1") -> dict[str, Any]:
    """Append one row to a Google Sheet."""
    return gt.append_sheet_row(spreadsheet_id, values, range_name=range_name)


@mcp.tool()
def sheets_update_values(
    spreadsheet_id: str,
    values: list[list[Any]],
    range_name: str = "A1",
) -> dict[str, Any]:
    """Replace a Google Sheets range with values."""
    return gt.update_sheet_values(spreadsheet_id, values, range_name=range_name)


@mcp.tool()
def sheets_clear(spreadsheet_id: str, range_name: str = "A1:Z1000") -> dict[str, Any]:
    """Clear a Google Sheets range."""
    return gt.clear_sheet_values(spreadsheet_id, range_name=range_name)


@mcp.tool()
def sheets_delete(spreadsheet_id: str, permanent: bool = False) -> dict[str, Any]:
    """Trash or permanently delete a Google Sheet through Drive."""
    return gt.delete_sheet(spreadsheet_id, permanent=permanent)


@mcp.tool()
def tasks_list() -> list[dict[str, Any]]:
    """List Google Tasks."""
    return gt.list_tasks()


@mcp.tool()
def tasks_add(title: str, due_date: str | None = None) -> dict[str, Any]:
    """Add a Google Task."""
    return gt.add_task(title, due_date=due_date)


@mcp.tool()
def tasks_complete(task_id: str) -> dict[str, Any]:
    """Complete a Google Task."""
    return gt.complete_task(task_id)


@mcp.tool()
def contacts_list(max_results: int = 20) -> list[dict[str, Any]]:
    """List Google Contacts."""
    return gt.list_contacts(max_results=max_results)


@mcp.tool()
def contacts_search(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search Google Contacts."""
    return gt.search_contacts(query, max_results=max_results)


@mcp.tool()
def contacts_create(name: str, email: str | None = None, phone: str | None = None) -> dict[str, Any]:
    """Create a Google Contact."""
    return gt.create_contact(name, email=email, phone=phone)


if __name__ == "__main__":
    mcp.run()
