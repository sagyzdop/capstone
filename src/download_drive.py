"""Download every folder whose name ends with a suffix (default '_30') found
anywhere under a Google Drive folder, keeping the Drive path layout.

Setup:
    pip install google-auth-oauthlib google-api-python-client
    Put an OAuth "Desktop app" client file at credentials.json (Google Cloud
    console, Drive API enabled). The first run opens a browser to log in and
    saves token.json next to it.

Usage:
    python src/download_drive.py
    python src/download_drive.py --root <folder id or URL> --suffix _30 --out data/drive
"""

import argparse
import os
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
ROOT_ID = "14oxtWhFOoRRHIKBYFMSU945cTeUrT2Zr"
FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"

# Google Docs/Sheets/Slides have no binary content and must be exported.
EXPORTS = {
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
}


def get_service(credentials, token):
    creds = None
    if os.path.exists(token):
        creds = Credentials.from_authorized_user_file(token, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def list_children(service, folder_id):
    """All non-trashed children of a folder, following pagination."""
    items, page = [], None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, size, shortcutDetails)",
            pageSize=1000,
            pageToken=page,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        items += resp.get("files", [])
        page = resp.get("nextPageToken")
        if not page:
            return items


def resolve(item):
    """Follow a shortcut to its target so shortcut folders are walked too."""
    if item["mimeType"] == SHORTCUT:
        d = item.get("shortcutDetails", {})
        return {**item, "id": d.get("targetId"), "mimeType": d.get("targetMimeType", "")}
    return item


def safe(name):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip() or "_"


def fetch(request, path):
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        downloader = MediaIoBaseDownload(f, request, chunksize=32 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk(num_retries=5)
    os.replace(tmp, path)


def download_file(service, item, path):
    mime = item["mimeType"]
    if mime.startswith("application/vnd.google-apps."):
        if mime not in EXPORTS:
            print(f"  skip (no export): {path}")
            return
        target, ext = EXPORTS[mime]
        path += "" if path.endswith(ext) else ext
        if os.path.exists(path):
            return
        print(f"  export {path}")
        fetch(service.files().export_media(fileId=item["id"], mimeType=target), path)
        return
    # skip files already downloaded in full, so reruns resume
    if os.path.exists(path) and os.path.getsize(path) == int(item.get("size", -1)):
        return
    print(f"  get    {path}")
    fetch(service.files().get_media(fileId=item["id"], supportsAllDrives=True), path)


def download_folder(service, folder_id, local_dir):
    os.makedirs(local_dir, exist_ok=True)
    for item in map(resolve, list_children(service, folder_id)):
        path = os.path.join(local_dir, safe(item["name"]))
        if item["mimeType"] == FOLDER:
            download_folder(service, item["id"], path)
        else:
            download_file(service, item, path)


def find_matches(service, folder_id, rel, suffix, seen):
    """Yield (id, relative path) of folders ending with suffix. A matching
    folder is downloaded whole, so its subfolders are not searched again."""
    if folder_id in seen:
        return
    seen.add(folder_id)
    for item in map(resolve, list_children(service, folder_id)):
        if item["mimeType"] != FOLDER:
            continue
        sub = os.path.join(rel, safe(item["name"]))
        if item["name"].endswith(suffix):
            yield item["id"], sub
        else:
            yield from find_matches(service, item["id"], sub, suffix, seen)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=ROOT_ID, help="Drive folder id or URL to search under")
    ap.add_argument("--suffix", default="_30")
    ap.add_argument("--out", default="data/drive")
    ap.add_argument("--credentials", default="credentials.json")
    ap.add_argument("--token", default="token.json")
    ap.add_argument("--dry-run", action="store_true", help="only list matching folders")
    args = ap.parse_args()

    root = args.root.rstrip("/").split("/")[-1].split("?")[0]
    service = get_service(args.credentials, args.token)

    print(f"searching {root} for folders ending with '{args.suffix}'...")
    matches = list(find_matches(service, root, "", args.suffix, set()))
    for _, rel in matches:
        print(f"  {rel}")
    print(f"found {len(matches)} folders")
    if args.dry_run:
        return

    for folder_id, rel in matches:
        print(f"\n--- {rel} ---")
        download_folder(service, folder_id, os.path.join(args.out, rel))
    print("\ndone")


if __name__ == "__main__":
    main()
