"""Portable-ZIP: упаковывает dist/SUOT_Neo в SUOT_Neo_portable.zip."""

import io
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "dist", "SUOT_Neo")
OUT = os.path.join(ROOT, "dist", "SUOT_Neo_portable.zip")


def main() -> int:
    if not os.path.isdir(SRC):
        print("Сначала соберите: python scripts/build_exe.py")
        return 1
    # ЗАПУСК.bat рядом с exe
    bat = os.path.join(SRC, "ЗАПУСК.bat")
    with open(bat, "w", encoding="cp866", errors="replace") as f:
        f.write('@echo off\r\nstart "" "%~dp0SUOT_Neo.exe"\r\n')

    # Ярлыки входа (рабочий стол + Пуск) — по запросу пользователя
    sc_src = os.path.join(ROOT, "scripts", "make_shortcut.bat")
    if os.path.isfile(sc_src):
        io.open(os.path.join(SRC, "ЯРЛЫКИ.bat"), "wb").write(
            io.open(sc_src, "rb").read()
        )

    if os.path.isfile(OUT):
        os.remove(OUT)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, _, fn in os.walk(SRC):
            for f in fn:
                fp = os.path.join(dp, f)
                z.write(fp, os.path.relpath(fp, SRC))
    size = os.path.getsize(OUT) / 1048576
    print(f"OK: {OUT} ({size:.0f} МБ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
