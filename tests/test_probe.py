from krunker_jev.probe import _signals


def test_signals_detect_canvas_and_cloudflare():
    html = "<html><canvas id='game-overlay'></canvas><script>three.js</script>Play Cloudflare challenge</html>"
    signals = _signals(html)
    assert signals["mentions_canvas"] is True
    assert signals["mentions_webgl"] is True
    assert signals["has_play_text"] is True
    assert signals["game_overlay_id"] is True
    assert signals["cloudflare_challenge"] is True
