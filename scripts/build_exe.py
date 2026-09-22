"""Сборка desktop-приложения: pyinstaller -> dist/SUOT_Neo.

Запуск:  python scripts/build_exe.py
После сборки можно создать portable-ZIP: python scripts/make_portable.py
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    # Иконка (если ещё нет)
    if not os.path.isfile(os.path.join(ROOT, "resources", "app.ico")):
        subprocess.check_call(
            [sys.executable, os.path.join(ROOT, "scripts", "make_icon.py")], cwd=ROOT
        )

    for d in ("build", "dist"):
        shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        os.path.join("suot_neo.spec"),
    ]
    print(">>", " ".join(cmd))
    r = subprocess.call(cmd, cwd=ROOT)
    if r != 0:
        print("СБОРКА ПРОВАЛЕНА", file=sys.stderr)
        return r

    exe = os.path.join(ROOT, "dist", "SUOT_Neo", "SUOT_Neo.exe")
    if not os.path.isfile(exe):
        print("exe не найден:", exe, file=sys.stderr)
        return 1
    size_mb = (
        sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, dn, fn in os.walk(os.path.dirname(exe))
            for f in fn
        )
        / 1048576
    )
    print(f"OK: {exe}  ({size_mb:.0f} МБ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
