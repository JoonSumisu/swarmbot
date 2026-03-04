from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if platform.system().lower().startswith("win") else "bin/python")


def _venv_bin(venv_dir: Path, name: str) -> Path:
    return venv_dir / ("Scripts" if platform.system().lower().startswith("win") else "bin") / (name + (".exe" if platform.system().lower().startswith("win") else ""))


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.check_call(cmd, cwd=str(cwd))


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    venv_dir = repo_root / ".venv"

    print(f"[swarmbot] repo: {repo_root}")
    print(f"[swarmbot] venv: {venv_dir}")

    if not venv_dir.exists():
        print("[swarmbot] creating venv ...")
        _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=repo_root)

    vpy = _venv_python(venv_dir)
    if not vpy.exists():
        raise RuntimeError(f"venv python not found: {vpy}")

    print("[swarmbot] upgrading pip/setuptools/wheel ...")
    _run([str(vpy), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=repo_root)

    print("[swarmbot] installing swarmbot into venv (editable) ...")
    _run([str(vpy), "-m", "pip", "install", "-e", "."], cwd=repo_root)

    sb = _venv_bin(venv_dir, "swarmbot")
    print()
    print("[swarmbot] done")
    if sb.exists():
        if platform.system().lower().startswith("win"):
            print(rf"  .\.venv\Scripts\swarmbot.exe --help")
            print(rf"  .\.venv\Scripts\swarmbot.exe daemon start")
        else:
            print("  ./.venv/bin/swarmbot --help")
            print("  ./.venv/bin/swarmbot daemon start")
        print("  source ./.venv/bin/activate  # 之后可直接运行 swarmbot")
    else:
        print(f"  {vpy} -m swarmbot.cli --help")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

