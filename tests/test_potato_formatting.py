from potato.formatting import build_share_text, format_achievements, format_stats

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
    for needle in ("Получено", "Отражено", "Сгнило", "серия", "Достижений"):
        assert needle in text


def test_vip_share_respects_flags_and_decor():
    text = build_share_text(STATS, is_vip=True, decor="U・ᴥ・U")
    assert "Получено" in text and "Сгнило" in text and "Достижений" in text
    assert "Отражено" not in text and "серия" not in text
    assert "U・ᴥ・U" in text and "VIP" in text


def _stats(**over):
    base = {
        "received": 3,
        "passed": 7,
        "exploded": 1,
        "best_pass_streak": 2,
        "started": 4,
        "enabled": 1,
        "fastest_pass_sec": 12,
        "achievements": ["potato_first", "potato_pass_1"],
    }
    base.update(over)
    return base


def test_menu_shows_rank_progress_and_poison_wording():
    text = format_stats(_stats(), is_vip=False)
    assert "Картошка фри" in text and "7/15" in text
    assert "Сгнило у вас" in text and "взор" not in text.lower()
    assert "🟩" in text and "🟨" not in text
    assert "для VIP" in text


def test_vip_menu_is_gold_with_pet_and_lock_note():
    text = format_stats(_stats(), True, strong_left=3600, pet="U・ᴥ・U", lock_note="x")
    assert "🟨" in text and "U・ᴥ・U" in text and "СИЛЬНОЕ ГНИЕНИЕ" in text
    assert "🔒 x" in text and "для VIP" not in text


def test_max_rank_has_no_next_threshold():
    assert "максимальный ранг" in format_stats(_stats(passed=300), False)


def test_achievements_screen_marks_unlocked_and_uses_poison_names():
    text = format_achievements(_stats(), is_vip=True)
    assert "✅ 🥔 Первая картошка" in text
    assert "Отравился" in text and "Бабах" not in text
    assert "🟨" in text
