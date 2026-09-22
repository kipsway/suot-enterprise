"""Авто-релиз: любое изменение кода -> новая версия + сборка + публикация на сайт.

Поток:
  1) bump версии (app_core/version.py + все файлы, где она указана)
  2) сборка exe (PyInstaller) и portable-zip
  3) сборка setup.exe (Inno Setup)
  4) публикация на сайт (site/downloads + index.json + лендинг)
  5) git add/commit/push (инфраструктура GitHub Pages деплоит автоматически)

Запуск:  python scripts/release.py
Флаги:   --no-git  — не коммитить/пушить (только собрать и опубликовать локально)
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(ROOT, "app_core", "version.py")
ISCC = os.environ.get("SUOT_ISCC") or (
    r"C:\Users\ДДД\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
)

# Файлы, где упоминается старая версия (обновляются на новую).
VERSIONED = [
    "app_core/version.py",
    "app_core/config.py",
    "server/routers/help_api.py",
    "server/routers/backup_api.py",
    "suot_platform.py",
    "installer/suot_neo.iss",
    "web/js/app.js",
    "site/js/site.js",
    "site/index.html",
    "README.md",
    "docs/RUN_GUIDE.md",
]


def current_version() -> str:
    with open(VERSION_FILE, encoding="utf-8") as f:
        m = re.search(r'APP_VERSION = "([^"]+)"', f.read())
        return m.group(1) if m else "2.2.0"


def next_version() -> str:
    base, _, build = current_version().rpartition(".")
    if base and build.isdigit():
        return f"{base}.{int(build) + 1}"
    return "2.2.1"


def bump_version(new: str) -> None:
    old = current_version()
    # Старый формат может быть "2.2.0" или "2.2.0.X" — заменяем префикс целиком.
    for rel in VERSIONED:
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        text = open(path, encoding="utf-8").read()
        updated = text.replace(old, new)
        if updated != text:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(updated)
            print(f"  version: {rel}: {old} -> {new}")
    # version.py: инкремент build
    rep = os.path.join(ROOT, "app_core", "version.py")
    text = open(rep, encoding="utf-8").read()
    m = re.search(r"BUILD_NUMBER = (\d+)", text)
    build = (int(m.group(1)) + 1) if m else 1
    text = re.sub(r"BUILD_NUMBER = \d+", f"BUILD_NUMBER = {build}", text)
    with open(rep, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def run(cmd, cwd=ROOT) -> int:
    print(">>", " ".join(cmd))
    return subprocess.call(cmd, cwd=cwd)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-git", action="store_true", help="не коммитить/пушить")
    args = ap.parse_args()

    new = next_version()
    print(f"Новая версия: {new}")
    bump_version(new)

    print("\n[1/4] Сборка exe…")
    r = run([sys.executable, os.path.join("scripts", "build_exe.py")])
    if r != 0:
        return r

    print("\n[2/4] Portable ZIP…")
    r = run([sys.executable, os.path.join("scripts", "make_portable.py")])
    if r != 0:
        return r

    print("\n[3/4] Setup (Inno Setup)…")
    if not os.path.isfile(ISCC):
        print("Нет ISCC:", ISCC)
        return 1
    r = run([ISCC, os.path.join("installer", "suot_neo.iss")])
    if r != 0:
        return r

    print("\n[4/4] Публикация на сайт…")
    env = dict(os.environ)
    env["SUOT_SITE_VERSION"] = new
    r = subprocess.call(
        [sys.executable, os.path.join("scripts", "publish_site.py")], cwd=ROOT, env=env
    )
    if r != 0:
        return r

    if args.no_git:
        print("\nГотово (без git).")
        return 0

    print("\nGit commit + push…")
    tracked = [
        ".",
        ":!*_dbg*.py",
        ":!*_probe*.py",
        ":!*_mini*.py",
        ":!_bisect.py",
        ":!_cmt*.py",
        ":!_cmp*.py",
        ":!_p23_js.py",
        ":!_panecheck.py",
        ":!_tb.py",
        ":!_tbal.py",
        ":!_thead.py",
        ":!_tmp_check.py",
        ":!_use_dist.py",
        ":!_xdcheck.py",
        ":!_hdiff.py",
        ":!_i_diff.py",
        ":!_i_pg2.py",
        ":!_diff_out.txt",
        ":!debug.log",
        ":!test_import.py",
    ]
    run(["git", "add"] + tracked)
    run(
        [
            "git",
            "commit",
            "-m",
            f"release: v{new} — ОхранаТруда Про, автопубликация новой версии на сайт",
        ]
    )
    run(["git", "push"])
    print("\nГотово. Сайт: https://kipsway.github.io/suot-enterprise/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
