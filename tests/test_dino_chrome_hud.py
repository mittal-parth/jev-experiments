from dino_jev.chrome import APPLY_JS, ARCADE_JS, BOT_JS, HUD_JS, POLL_COMMAND_JS


def test_hud_scripts_paint_typesafe_replies():
    assert "jev.reply = payload" in HUD_JS
    assert "paintHud" in HUD_JS
    assert "jev.reply = payload" in APPLY_JS
    assert "paintHud" in APPLY_JS
    assert "_replySeq" in HUD_JS
    assert "_replySeq" in APPLY_JS


def test_arcade_scales_logical_600_and_rescales_hidpi():
    assert "inst.canvas.width = logicalW" in ARCADE_JS
    assert "updateCanvasScaling" in ARCADE_JS
    assert "setArcadeMode" in ARCADE_JS
    assert "window.innerHeight * 0.48" not in ARCADE_JS


def test_dino_page_mounts_clickable_start_button():
    assert "dino-jev-start" in BOT_JS
    assert "pendingCommand" in BOT_JS
    assert "pointer-events:auto" in BOT_JS
    assert "jev.pendingCommand" in POLL_COMMAND_JS


def test_jev_apply_delegates_to_apply_jev_intent():
    assert 'provider === "jev"' in APPLY_JS
    assert "applyJevIntent" in APPLY_JS
    assert "applyJevIntent" in BOT_JS
    assert "jumpClears" in BOT_JS


def test_bot_times_armed_jev_on_runner_frames():
    assert "timeArmed" in BOT_JS
    assert "holdsForClusteredHop" in BOT_JS
    assert "shouldCommitSingleJumpNow" in BOT_JS
    assert "decide(inst) === \"jump\"" in BOT_JS
    assert "jev.armedId != null" in BOT_JS
    assert 'jev.provider === "jev"' in BOT_JS
    assert 'jev.provider === "heuristic"' in BOT_JS
