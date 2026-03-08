from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if platform.system().lower().startswith("win") else "bin/python")


def _venv_bin(venv_dir: Path, name: str) -> Path:
    return venv_dir / ("Scripts" if platform.system().lower().startswith("win") else "bin") / (name + (".exe" if platform.system().lower().startswith("win") else ""))


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.check_call(cmd, cwd=str(cwd))


def _install_eval_deps(python_bin: str, repo_root: Path) -> None:
    print("[swarmbot] installing eval dependencies ...")
    _run([python_bin, "-m", "pip", "install", "-U", "datasets"], cwd=repo_root)


def _install_venv(repo_root: Path, editable: bool = True) -> None:
    venv_dir = repo_root / ".venv"
    print(f"[swarmbot] venv: {venv_dir}")
    if not venv_dir.exists():
        print("[swarmbot] creating venv ...")
        _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=repo_root)
    vpy = _venv_python(venv_dir)
    if not vpy.exists():
        raise RuntimeError(f"venv python not found: {vpy}")
    print("[swarmbot] upgrading pip/setuptools/wheel ...")
    _run([str(vpy), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=repo_root)
    if editable:
        print("[swarmbot] installing swarmbot into venv (editable) ...")
        _run([str(vpy), "-m", "pip", "install", "-e", "."], cwd=repo_root)
    else:
        print("[swarmbot] installing swarmbot into venv ...")
        _run([str(vpy), "-m", "pip", "install", "."], cwd=repo_root)
    sb = _venv_bin(venv_dir, "swarmbot")
    print()
    print("[swarmbot] done (venv mode)")
    if sb.exists():
        if platform.system().lower().startswith("win"):
            print(rf"  .\.venv\Scripts\swarmbot.exe --help")
            print(rf"  .\.venv\Scripts\swarmbot.exe daemon start")
        else:
            print("  ./.venv/bin/swarmbot --help")
            print("  ./.venv/bin/swarmbot daemon start")
            print("  source ./.venv/bin/activate")
    else:
        print(f"  {vpy} -m swarmbot.cli --help")


def _install_pipx(repo_root: Path, editable: bool = False, with_eval_deps: bool = False) -> bool:
    pipx = shutil.which("pipx")
    if not pipx:
        return False
    print("[swarmbot] installing with pipx ...")
    cmd = [pipx, "install", "--force"]
    if editable:
        cmd.append("--editable")
    cmd.append(str(repo_root))
    _run(cmd, cwd=repo_root)
    print()
    print("[swarmbot] done (pipx mode)")
    print("  swarmbot --help")
    print("  swarmbot daemon start")
    print("  如命令未生效，请执行: pipx ensurepath")
    if with_eval_deps:
        py = shutil.which("python3") or shutil.which("python") or sys.executable
        _install_eval_deps(py, repo_root)
    return True


def _install_user(repo_root: Path, editable: bool = False, with_eval_deps: bool = False) -> bool:
    print("[swarmbot] installing with pip --user ...")
    try:
        _run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=repo_root)
        cmd = [sys.executable, "-m", "pip", "install", "--user"]
        if editable:
            cmd.append("-e")
        cmd.append(".")
        _run(cmd, cwd=repo_root)
    except Exception:
        return False
    user_base = Path(
        subprocess.check_output([sys.executable, "-m", "site", "--user-base"], cwd=str(repo_root), text=True).strip()
    )
    bin_dir = user_base / ("Scripts" if platform.system().lower().startswith("win") else "bin")
    print()
    print("[swarmbot] done (user mode)")
    print(f"  swarmbot --help")
    print(f"  swarmbot daemon start")
    if not platform.system().lower().startswith("win"):
        print(f"  如命令未找到，请加入 PATH: export PATH=\"{bin_dir}:$PATH\"")
    else:
        print(f"  如命令未找到，请将 {bin_dir} 加入 PATH")
    if with_eval_deps:
        _install_eval_deps(sys.executable, repo_root)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Swarmbot installer")
    parser.add_argument(
        "--mode",
        choices=["auto", "pipx", "user", "venv"],
        default="auto",
        help="安装模式: auto 优先 pipx, 其次 user, 最后 venv",
    )
    parser.add_argument(
        "--editable",
        action="store_true",
        help="以 editable 模式安装（开发调试推荐）",
    )
    parser.add_argument(
        "--with-eval-deps",
        action="store_true",
        help="安装回归评测依赖（如 datasets）",
    )
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    print(f"[swarmbot] repo: {repo_root}")

    if args.mode == "pipx":
        if _install_pipx(repo_root, editable=args.editable, with_eval_deps=args.with_eval_deps):
            return 0
        print("[swarmbot] pipx 未安装，安装失败。")
        return 1

    if args.mode == "user":
        if _install_user(repo_root, editable=args.editable, with_eval_deps=args.with_eval_deps):
            return 0
        print("[swarmbot] user 模式安装失败。")
        return 1

    if args.mode == "venv":
        _install_venv(repo_root, editable=args.editable)
        if args.with_eval_deps:
            _install_eval_deps(str(_venv_python(repo_root / ".venv")), repo_root)
        return 0

    if args.editable:
        print("[swarmbot] auto + editable: 使用 venv editable 安装。")
        _install_venv(repo_root, editable=True)
        if args.with_eval_deps:
            _install_eval_deps(str(_venv_python(repo_root / ".venv")), repo_root)
        return 0

    if _install_pipx(repo_root, editable=False, with_eval_deps=args.with_eval_deps):
        return 0
    if _install_user(repo_root, editable=False, with_eval_deps=args.with_eval_deps):
        return 0
    print("[swarmbot] auto 模式回退到 venv 安装。")
    _install_venv(repo_root, editable=False)
    if args.with_eval_deps:
        _install_eval_deps(str(_venv_python(repo_root / ".venv")), repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
