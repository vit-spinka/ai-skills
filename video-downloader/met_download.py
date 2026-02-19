#!/usr/bin/env python3
"""
Downloads Met Opera On Demand videos by name or URL.

Usage:
    python met_download.py "Dialogues des Carmelites" [output-dir]
    python met_download.py https://ondemand.metopera.org/performance/detail/<id> [output-dir]
"""

import sys
import json
import urllib.request
import urllib.parse
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "https://ondemand.metopera.org/performance/detail/"
SEARCH_API = "https://middleware.ondemand.metopera.org/client/search/"


def search(query: str) -> dict | None:
    url = SEARCH_API + urllib.parse.quote(query)
    with urllib.request.urlopen(url) as r:
        data = json.loads(r.read())

    videos = data.get("video", {}).get("results", [])
    audios = data.get("audio", {}).get("results", [])

    candidates = videos if videos else audios
    if not candidates:
        return None

    # Sort by performanceDate descending, most recent first
    candidates.sort(key=lambda x: x.get("performanceDate") or "", reverse=True)
    best = candidates[0]

    print(f"Found: {best['name']} ({best.get('performanceDate', '?')}) "
          f"[{'VIDEO' if videos else 'AUDIO'}]")
    if len(videos) + len(audios) > 1:
        print(f"  ({len(videos)} video, {len(audios)} audio versions available — picking most recent video)")

    return best


def find_m3u8(page_url: str) -> str | None:
    found = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.on("request", lambda r: found.append(r.url) if "master.m3u8" in r.url else None)

        print(f"Opening {page_url} ...")
        page.goto(page_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(5000)
        browser.close()

    return found[0] if found else None


def download(m3u8_url: str, title: str, output_dir: str = "~/Downloads") -> None:
    output_dir = str(Path(output_dir).expanduser())
    safe_title = "".join(c if c.isalnum() or c in " -_.,()'" else "_" for c in title)
    subprocess.run([
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", f"{output_dir}/{safe_title}.%(ext)s",
        m3u8_url,
    ], check=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python met_download.py <name-or-url> [output-dir]")
        sys.exit(1)

    arg = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "~/Downloads"

    # Determine if arg is a URL or a search query
    if arg.startswith("http"):
        page_url = arg
        title = "met-opera"
    else:
        result = search(arg)
        if not result:
            print(f"ERROR: No results found for '{arg}'")
            sys.exit(1)
        page_url = BASE_URL + result["id"]
        title = result["name"]

    m3u8 = find_m3u8(page_url)
    if not m3u8:
        print("ERROR: No m3u8 URL found. Make sure you're logged in to Met Opera in the browser window.")
        sys.exit(1)

    print(f"Downloading: {title}")
    download(m3u8, title, out_dir)
    print("Done!")
