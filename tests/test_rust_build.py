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


def test_build_uses_uv_when_pip_missing(monkeypatch):
    import rust_build

    calls: list[list[str]] = []
    monkeypatch.setattr(rust_build.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(rust_build, "_pip_available", lambda: False)
    monkeypatch.setattr(rust_build, "_maturin_command", lambda: ["maturin"])
    monkeypatch.setattr(rust_build, "_run", lambda cmd: calls.append(list(cmd)) or True)

    assert rust_build.build_module()
    assert calls == [["maturin", "develop", "--release", "--uv"]]


def test_install_maturin_prefers_pip_then_uv(monkeypatch):
    import rust_build

    calls: list[list[str]] = []
    monkeypatch.setattr(rust_build.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(rust_build, "_run", lambda cmd: calls.append(list(cmd)) or True)

    monkeypatch.setattr(rust_build, "_pip_available", lambda: True)
    assert rust_build._install_maturin()
    assert calls[-1][1:4] == ["-m", "pip", "install"]

    monkeypatch.setattr(rust_build, "_pip_available", lambda: False)
    assert rust_build._install_maturin()
    assert calls[-1][:3] == ["/bin/uv", "pip", "install"]
