import os
import time

from rust_build import is_stale, newest_source_mtime


def test_is_stale_rules():
    assert not is_stale(100.0, 0.0)
    assert is_stale(None, 50.0)
    assert is_stale(10.0, 20.0)
    assert not is_stale(20.0, 10.0)
    assert not is_stale(20.0, 20.0)


def test_newest_source_mtime_scans_rust_and_migrations(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "migrations").mkdir()
    old = tmp_path / "src" / "lib.rs"
    mig = tmp_path / "migrations" / "0008.sql"
    old.write_text("x")
    mig.write_text("y")
    past = time.time() - 1000
    os.utime(old, (past, past))
    assert abs(newest_source_mtime(tmp_path) - mig.stat().st_mtime) < 1
    assert newest_source_mtime(tmp_path / "nowhere") == 0.0
