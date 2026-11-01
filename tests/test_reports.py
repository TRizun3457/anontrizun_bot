from reports import (
    MAX_REPORT_LENGTH,
    ReportLimiter,
    format_report_header,
    is_too_long,
)


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_limiter_blocks_until_cooldown_passes():
    clock = Clock()
    limiter = ReportLimiter(cooldown=60, clock=clock)
    assert limiter.remaining(1) == 0
    limiter.mark(1)
    assert 0 < limiter.remaining(1) <= 60
    assert limiter.remaining(2) == 0
    clock.t += 59
    assert limiter.remaining(1) == 1
    clock.t += 1
    assert limiter.remaining(1) == 0


def test_limiter_prunes_old_entries():
    clock = Clock()
    limiter = ReportLimiter(cooldown=10, clock=clock)
    for uid in range(5100):
        limiter.mark(uid)
        clock.t += 0.001
    clock.t += 20
    limiter.mark(99999)
    assert len(limiter._last) == 1


def test_header_escapes_html_and_links_profile():
    header = format_report_header(42, "<b>Evil</b> & Co", "user_name")
    assert "&lt;b&gt;Evil&lt;/b&gt; &amp; Co" in header
    assert "tg://user?id=42" in header and "@user_name" in header
    assert "<code>42</code>" in header


def test_header_without_username_or_name():
    header = format_report_header(7, "  ", None)
    assert "нет username" in header and "Без имени" in header


def test_header_never_contains_anon_code_field():
    assert "код" not in format_report_header(7, "A", "b").lower()


def test_length_limit():
    assert not is_too_long(None)
    assert not is_too_long("x" * MAX_REPORT_LENGTH)
    assert is_too_long("x" * (MAX_REPORT_LENGTH + 1))


def test_cancel_text_variants():
    from reports import is_cancel_text

    for ok in ("/cancel", "cancel", " Отмена ", "/cancel@trizun_gay"):
        assert is_cancel_text(ok)
    for bad in (None, "", "не работает отмена платежа", "/start"):
        assert not is_cancel_text(bad)


def test_album_buffer_collects_sorted_and_flags_first():
    from reports import AlbumBuffer

    buf = AlbumBuffer()
    assert buf.add("g", 12) is True
    assert buf.add("g", 10) is False
    assert buf.add("g", 11) is False
    assert buf.add("g", 11) is False
    assert buf.pop("g") == [10, 11, 12]
    assert buf.pop("g") == []
    assert buf.add("g", 20) is True
