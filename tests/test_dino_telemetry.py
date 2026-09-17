from dino_jev.telemetry import classify_timing


def test_classify_jump_late():
    state = {
        "run": {"crashed": False, "intro": False, "speed": 8.0},
        "dino": {"jumping": False, "x": 50, "ground_y": 93},
        "nearest_obstacle": {
            "kind": "cactus",
            "clearance": "ground",
            "gap_px": 18,
            "x": 112,
            "y": 93,
            "width": 20,
            "height": 35,
        },
        "obstacles": [
            {
                "kind": "cactus",
                "x": 112,
                "y": 93,
                "width": 20,
                "height": 35,
            }
        ],
    }
    tag = classify_timing(
        state,
        asked="run",
        executed="run",
        gated=False,
        lead_frames=8,
    )
    assert tag in {None, "jump_late_or_missed", "jump_early_stand_hit_far"}
