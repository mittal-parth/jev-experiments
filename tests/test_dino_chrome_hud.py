from dino_jev.chrome import APPLY_JS, ARCADE_JS, HUD_JS


def test_internat_hud_scripts_paint_typesafe_replies():
    assert "jev.reply = payload" in HUD_JS
    assert "paintHud" in HUD_JS
    assert "jev.reply = payload" in APPLY_JS
    assert "paintHud" in APPLY_JS
    assert "_replySeq" in HUD_JS
    assert "_replySeq" in APPLY_JS


def test_arcade_scales_logical_600_without_wiping_canvas_buffer():
    assert "canvas.width =" not in ARCADE_JS
    assert 'style.width = logicalW + "px"' in ARCADE_JS
    assert "setArcadeMode" in ARCADE_JS
    assert "window.innerHeight * 0.48" not in ARCADE_JS
