from dino_jev.chrome import APPLY_JS, HUD_JS


def test_internat_hud_scripts_paint_typesafe_replies():
    assert "jev.reply = payload" in HUD_JS
    assert "paintHud" in HUD_JS
    assert "jev.reply = payload" in APPLY_JS
    assert "paintHud" in APPLY_JS
    assert "_replySeq" in HUD_JS
    assert "_replySeq" in APPLY_JS
