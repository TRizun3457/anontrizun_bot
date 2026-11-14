import importlib
import importlib.util
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger("rust_build")

ROOT = Path(__file__).resolve().parent
RUST_DIR = ROOT / "database_rs"
MODULE_NAME = "database"
SOURCE_GLOBS = ("src/**/*.rs", "migrations/*.sql", "Cargo.toml", "build.rs")
BUILD_TIMEOUT_SECONDS = 1800


def newest_source_mtime(rust_dir: Path) -> float:
    newest = 0.0
    for pattern in SOURCE_GLOBS:
        for path in rust_dir.glob(pattern):
            if path.is_file():
                newest = max(newest, path.stat().st_mtime)
    return newest


def is_stale(module_mtime: float | None, source_mtime: float) -> bool:
    if source_mtime == 0.0:
        return False
    return module_mtime is None or module_mtime < source_mtime


def built_module_mtime() -> float | None:
    spec = importlib.util.find_spec(MODULE_NAME)
    origin = getattr(spec, "origin", None) if spec else None
    if not origin or not Path(origin).is_file():
        return None
    return Path(origin).stat().st_mtime


def _build_env() -> dict[str, str]:
    env = dict(os.environ)
    if sys.prefix != sys.base_prefix:
        env.setdefault("VIRTUAL_ENV", sys.prefix)
    return env


def _maturin_command() -> list[str] | None:
    probe = subprocess.run(
        [sys.executable, "-m", "maturin", "--version"],
        capture_output=True,
        check=False,
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", "maturin"]
    exe = shutil.which("maturin")
    return [exe] if exe else None


def _pip_available() -> bool:
    probe = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


def _install_maturin() -> bool:
    uv = shutil.which("uv")
    if _pip_available():
        return _run([sys.executable, "-m", "pip", "install", "maturin"])
    if uv:
        return _run([uv, "pip", "install", "--python", sys.executable, "maturin"])
    return False


def _run(cmd: Iterable[str]) -> bool:
    result = subprocess.run(
        list(cmd),
        cwd=ROOT,
        env=_build_env(),
        check=False,
        timeout=BUILD_TIMEOUT_SECONDS,
    )
    return result.returncode == 0


def build_module() -> bool:
    if shutil.which("cargo") is None:
        logger.error(
            "Не найден cargo: установите Rust (https://rustup.rs) и перезапустите бота."
        )
        return False
    command = _maturin_command()
    if command is None:
        logger.info("Устанавливаю maturin...")
        if not _install_maturin():
            logger.error(
                "Не удалось установить maturin (pip install maturin / uv pip install maturin)"
            )
            return False
        command = _maturin_command()
        if command is None:
            return False
    logger.info("Собираю Rust-модуль (первый раз может занять несколько минут)...")
    try:
        develop = [*command, "develop", "--release"]
        if not _pip_available() and shutil.which("uv"):
            develop.append("--uv")
        ok = _run(develop)
    except (OSError, subprocess.SubprocessError):
        logger.exception("Сборка Rust-модуля прервалась")
        return False
    if ok:
        importlib.invalidate_caches()
    return ok


def ensure_fresh_build() -> None:
    if os.getenv("AUTO_BUILD", "1").strip().lower() in {"0", "false", "no", "off"}:
        return
    if not RUST_DIR.is_dir() or MODULE_NAME in sys.modules:
        return
    if not is_stale(built_module_mtime(), newest_source_mtime(RUST_DIR)):
        return
    logger.warning("Rust-модуль устарел или не собран, запускаю автосборку.")
    if build_module():
        logger.info("Rust-модуль собран.")
    else:
        logger.error(
            "Автосборка не удалась. Соберите вручную: maturin develop --release"
        )
