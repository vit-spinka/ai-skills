#!/usr/bin/env python3
"""
Downloads Wiener Staatsoper streams by name or URL.
Fetches rich metadata from the performa.intio.tv API (no auth needed).

Usage:
    python wso_download.py --list                   [year]
    python wso_download.py "Luisa Miller"           [output-dir]
    python wso_download.py "Rosenkavalier" 2020     [output-dir]
    python wso_download.py https://play.wiener-staatsoper.at/event/<uuid>  [output-dir]
"""

import sys
import re
import json
import urllib.request
import urllib.parse
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

API_BASE = "https://live.performa.intio.tv/api/v1"
PAGE_BASE = "https://play.wiener-staatsoper.at/event"


def fetch_all_events() -> list[dict]:
    url = f"{API_BASE}/events/?platform=web&organization=vso&page_size=100"
    results = []
    while url:
        with urllib.request.urlopen(url) as r:
            data = json.loads(r.read())
        results.extend(data["results"])
        url = data.get("next")
    return results


def fetch_event(event_id: str) -> dict:
    with urllib.request.urlopen(f"{API_BASE}/events/{event_id}/") as r:
        return json.loads(r.read())


def search(query: str, year: str | None = None) -> dict | None:
    events = fetch_all_events()

    q = query.lower()
    matches = [e for e in events if q in e["title"].lower()]

    if year:
        matches = [e for e in matches if e.get("begin_time", "").startswith(year)]

    if not matches:
        return None

    # Sort: video streams preferred (tags), then most recent
    def score(e):
        date = e.get("begin_time", "")
        return date

    matches.sort(key=score, reverse=True)

    if len(matches) > 1:
        print(f"Found {len(matches)} matches, picking most recent:")
        for e in matches[:5]:
            print(f"  {e['begin_time'][:10]}  {e['title']}  [{e['id']}]")

    return matches[0]


def format_metadata(event: dict) -> str:
    """Build a descriptive filename from event metadata."""
    title = event.get("title", "unknown")
    date = (event.get("begin_time") or "")[:10]

    # Extract conductor from cast
    conductor = None
    for c in event.get("cast", []):
        role_name = c.get("role", {}).get("name", "").lower()
        if "conductor" in role_name or "leitung" in role_name:
            conductor = c.get("person", {}).get("name")
            break

    parts = [title]
    if date:
        parts.append(date)
    if conductor:
        parts.append(conductor)

    name = " - ".join(parts)
    # Sanitise for filesystem
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name


def print_event_info(event: dict) -> None:
    print(f"\nTitle:      {event['title']}")
    print(f"Date:       {(event.get('begin_time') or '')[:10]}")
    print(f"VOD avail:  {event.get('vod_availability', '?')} after broadcast")

    roles: dict[str, list[str]] = {}
    for c in event.get("cast", []):
        role = c.get("role", {}).get("name", "Unknown")
        person = c.get("person", {}).get("name", "?")
        roles.setdefault(role, []).append(person)
    for role, people in roles.items():
        print(f"{role+':':<12} {', '.join(people)}")


def find_m3u8(page_url: str) -> str | None:
    found = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.on("request", lambda r: found.append(r.url) if "master.m3u8" in r.url or ".m3u8" in r.url else None)

        print(f"\nOpening {page_url} ...")
        page.goto(page_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(6000)
        browser.close()

    return found[0] if found else None


def download(m3u8_url: str, filename: str, output_dir: str = "~/Downloads") -> None:
    output_dir = str(Path(output_dir).expanduser())
    subprocess.run([
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", f"{output_dir}/{filename}.%(ext)s",
        m3u8_url,
    ], check=True)


def list_events(year: str | None = None) -> None:
    events = fetch_all_events()
    if year:
        events = [e for e in events if (e.get("begin_time") or "").startswith(year)]
    events.sort(key=lambda e: e.get("begin_time", ""), reverse=True)

    current_year = None
    for e in events:
        date = (e.get("begin_time") or "")[:10]
        y = date[:4]
        if y != current_year:
            current_year = y
            print(f"\n── {y} ──────────────────────────────────────")
        print(f"  {date}  {e['title']:<40}  {e['id']}")
    print(f"\n{len(events)} events total")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python wso_download.py --list [year]")
        print("       python wso_download.py <name-or-url> [year] [output-dir]")
        sys.exit(1)

    args = sys.argv[1:]

    if args[0] == "--list":
        year = args[1] if len(args) > 1 else None
        list_events(year)
        sys.exit(0)
    out_dir = "~/Downloads"

    # Parse args: url or query, optional 4-digit year, optional output dir
    if args[0].startswith("http"):
        page_url = args[0]
        out_dir = args[1] if len(args) > 1 else out_dir
        # Extract event ID from URL to get metadata
        m = re.search(r'/event/([0-9a-f-]{36})', page_url)
        event = fetch_event(m.group(1)) if m else {}
    else:
        year = next((a for a in args[1:] if re.match(r'^\d{4}$', a)), None)
        out_dir = next((a for a in args[1:] if not re.match(r'^\d{4}$', a)), out_dir)
        query = args[0]

        event = search(query, year)
        if not event:
            print(f"ERROR: No results found for '{query}'" + (f" in {year}" if year else ""))
            sys.exit(1)
        page_url = f"{PAGE_BASE}/{event['id']}"

    print_event_info(event)
    filename = format_metadata(event)
    print(f"\nOutput file: {filename}.mp4")

    m3u8 = find_m3u8(page_url)
    if not m3u8:
        print("ERROR: No m3u8 stream found. Make sure you're logged in in the browser window.")
        sys.exit(1)

    print(f"Stream found, downloading...")
    download(m3u8, filename, out_dir)
    print("Done!")
