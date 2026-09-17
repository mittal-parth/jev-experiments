"""Inspect krunker.io from this machine without driving a live match."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

KRUNKER_URL = "https://krunker.io/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


def _fetch(url: str, timeout: float = 12.0) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(120_000).decode("utf-8", "replace")
            return {
                "ok": True,
                "status": getattr(response, "status", 200),
                "final_url": response.geturl(),
                "bytes": len(body),
                "body": body,
            }
    except HTTPError as exc:
        body = exc.read(8000).decode("utf-8", "replace") if exc.fp else ""
        return {
            "ok": False,
            "status": exc.code,
            "final_url": url,
            "bytes": len(body),
            "body": body,
            "error": str(exc),
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "ok": False,
            "status": None,
            "final_url": url,
            "bytes": 0,
            "body": "",
            "error": str(exc),
        }


def _chrome_dom(url: str) -> dict[str, Any] | None:
    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if chrome is None:
        return None
    try:
        completed = subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--virtual-time-budget=2500",
                "--dump-dom",
                url,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "status": None, "bytes": 0, "body": "", "error": str(exc)}
    body = completed.stdout or ""
    return {
        "ok": completed.returncode == 0 and bool(body.strip()),
        "status": completed.returncode,
        "bytes": len(body),
        "body": body[:120_000],
        "error": None if completed.returncode == 0 else (completed.stderr or "")[-400:],
    }


def _signals(html: str) -> dict[str, bool | int]:
    lowered = html.lower()
    return {
        "mentions_canvas": "canvas" in lowered,
        "mentions_webgl": "webgl" in lowered or "three.js" in lowered or "three.min" in lowered,
        "has_play_text": "play" in lowered,
        "cloudflare_challenge": "cloudflare" in lowered and ("challenge" in lowered or "cf-ray" in lowered),
        "game_overlay_id": "game-overlay" in lowered,
        "menu_holder": "menuholder" in lowered or "menu-holder" in lowered,
        "script_tags": lowered.count("<script"),
    }


def probe_krunker() -> dict[str, Any]:
    """Fetch public HTML and classify why a DOM agent cannot play a match."""
    http = _fetch(KRUNKER_URL)
    chrome = _chrome_dom(KRUNKER_URL)
    source = chrome if chrome and chrome.get("ok") else http
    html = str(source.get("body") or "")
    report = {
        "url": KRUNKER_URL,
        "http": {key: http[key] for key in ("ok", "status", "final_url", "bytes", "error") if key in http},
        "chrome": None
        if chrome is None
        else {key: chrome[key] for key in ("ok", "status", "bytes", "error")},
        "signals": _signals(html),
        "conclusion": {
            "lobby_might_be_dom": True,
            "match_is_canvas": True,
            "jev_cannot_see_pixels": True,
            "why_not_a_live_aimbot": (
                "Jev is text-only. Krunker matches render in WebGL/canvas, which "
                "browser-use/jev-ultrafast also excludes. Reading hidden player "
                "transforms from the client would be cheating, not a System One demo. "
                "The local arena is the Doom-shaped analogue: structured state in, "
                "typed actions out."
            ),
        },
    }
    return report


def main() -> None:
    print(json.dumps(probe_krunker(), indent=2))
