"""Часть 34: публикация сборки на сайт.

Копирует dist -> site/downloads/ и обновляет site/downloads/index.json
(версия, размер, SHA-256, дата, история версий).

Запуск:  python scripts/publish_site.py
"""

import hashlib
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
DL = os.path.join(ROOT, "site", "downloads")


def sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main() -> int:
    os.makedirs(DL, exist_ok=True)
    index_path = os.path.join(DL, "index.json")
    history = []
    if os.path.isfile(index_path):
        try:
            old = json.load(open(index_path, encoding="utf-8"))
            history = old.get("history", [])
        except Exception:
            history = []

    files = []
    for name in ("SUOT_Neo_portable.zip", "SUOT_Neo_setup.exe"):
        src = os.path.join(DIST, name)
        if not os.path.isfile(src):
            print("skip (нет в dist):", name)
            continue
        dst = os.path.join(DL, name)
        shutil.copy2(src, dst)
        size = os.path.getsize(dst)
        files.append(
            {
                "file": name,
                "size": size,
                "size_mb": round(size / 1048576, 1),
                "sha256": sha256(dst),
            }
        )
        print("published:", name, f"{size / 1048576:.1f} МБ")
        history.append(
            {
                "version": os.environ.get("SUOT_SITE_VERSION", "2.2.0"),
                "date": __import__("datetime").datetime.now().strftime("%Y-%m-%d"),
                "file": name,
                "size_mb": round(size / 1048576, 1),
            }
        )

    # история — не дублировать одинаковые версии подряд
    dedup = []
    seen = set()
    for h in history:
        key = (h["version"], h["file"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(h)
    history = dedup[:12]

    index = {
        "version": os.environ.get("SUOT_SITE_VERSION", "2.2.0"),
        "updated": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
        "releases": files,
        "history": history,
    }
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print("index.json:", DL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
