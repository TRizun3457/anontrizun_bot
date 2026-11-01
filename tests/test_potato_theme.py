import random

from potato.theme import banner, bar, fmt_duration, holder_text, poison_text, rank_for


def test_ranks_progress():
    assert rank_for(0)[1] == "Росток" and rank_for(0)[2] == 1
    assert rank_for(5)[1] == "Картошка фри"
    assert rank_for(100)[1] == "Картофельный бастион"
    _emoji, title, nxt = rank_for(10**6)
    assert title == "Король картошки" and nxt is None


def test_bar_bounds():
    assert bar(0, 10) == "▱" * 10
    assert bar(5, 10) == "▰" * 5 + "▱" * 5
    assert bar(99, 10) == "▰" * 10
    assert bar(1, 0) == "▰" * 10


def test_vip_and_regular_banners_differ():
    assert "✦" in banner("Т", True) and "❖" in banner("Т", True)
    assert "◈" in banner("Т", False) and "❖" not in banner("Т", False)
    assert "🐶" in banner("Т", True, "🐶")


def test_holder_texts():
    rng = random.Random(1)
    normal = holder_text("normal", "30 мин.", "12:30", False, rng)
    assert "Гнилая картошка" in normal and "12:30" in normal and "сгниёт" in normal
    rot = holder_text("rot", "1 ч.", None, False, rng)
    assert "ДЕНЬ ГНИЕНИЯ" in rot and "Сгниёт в" not in rot
    vip = holder_text("normal", "30 мин.", "12:30", True, rng)
    assert "Золотая гнилушка" in vip


def test_poison_text_no_explosion_wording():
    for vip in (True, False):
        text = poison_text(vip).lower()
        assert "сгнило" in text and "взр" not in text and "бабах" not in text


def test_fmt_duration():
    assert fmt_duration(600) == "10 мин."
    assert fmt_duration(5400) == "1 ч. 30 мин."


def test_banners_use_symbols_not_color_squares():
    for vip in (True, False):
        text = banner("Т", vip)
        assert "🟨" not in text and "🟩" not in text


def test_tree_layout():
    from potato.theme import tree

    assert tree(["a"]) == "╺ a"
    assert tree(["a", "b", "c"]) == "┌ a\n├ b\n└ c"
