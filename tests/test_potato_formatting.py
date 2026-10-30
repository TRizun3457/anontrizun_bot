from potato.formatting import build_share_text

STATS = {
    "received": 7,
    "passed": 5,
    "exploded": 2,
    "best_pass_streak": 4,
    "achievements": ["potato_first"],
    "share_received": 1,
    "share_passed": 0,
    "share_exploded": 1,
    "share_streak": 0,
    "share_achievements": 1,
}


def test_non_vip_always_shares_everything():
    text = build_share_text(STATS, is_vip=False)
    for needle in ("Получено", "Отражено", "Взорвалось", "серия", "Достижений"):
        assert needle in text


def test_vip_share_respects_flags_and_decor():
    text = build_share_text(STATS, is_vip=True, decor="U・ᴥ・U")
    assert "Получено" in text and "Взорвалось" in text and "Достижений" in text
    assert "Отражено" not in text and "серия" not in text
    assert "U・ᴥ・U" in text and "VIP" in text
