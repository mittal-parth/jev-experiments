"""Confirm chrome://dino/ is the offline runner with structured state."""

from __future__ import annotations

from typing import Any

from dino_jev.chrome import ChromeDino


def probe_dino(*, headed: bool = False) -> dict[str, Any]:
    """Launch Chromium, open chrome://dino/, and snapshot Runner.getInstance()."""
    session = ChromeDino(headed=headed, speed_cap=None)
    try:
        before = session.observe()
        session.start_run()
        after = session.observe()
        return {
            "url": "chrome://dino/",
            "runner": {
                "getInstance": True,
                "playing_before": before["run"]["playing"],
                "playing_after_start": after["run"]["playing"],
                "crashed": after["run"]["crashed"],
                "speed": after["run"]["speed"],
                "dino": after["dino"],
            },
            "conclusion": {
                "live_chrome_dino": True,
                "structured_state": True,
                "jev_cannot_see_pixels": True,
                "why_this_is_easier_than_krunker": (
                    "chrome://dino/ is still a canvas, but Chromium keeps the "
                    "whole runner on Runner.getInstance() — pose, speed, and "
                    "obstacles. That is the Doom-shaped observation. Keys "
                    "execute the intent. The canvas is a view, not model input."
                ),
            },
        }
    finally:
        session.close()
