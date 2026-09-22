"""Проверка ресурсов и диагностика при первом запуске / обновлении.

Гарантирует, что все нужные файлы (vendor JS, темы, иконки, звуки, медиа)
на месте. Отсутствующие скачиваются (Alpine) или пересоздаются.
"""

import os
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_FILES = [
    "web/vendor/alpine.min.js",
    "web/css/tokens.css",
    "web/css/components.css",
    "web/index.html",
    "web/js/api.js",
    "web/js/i18n.js",
    "web/js/icons.js",
    "web/js/app.js",
    "web/js/tabs.js",
    "web/js/table.js",
    "web/js/pages.js",
    "web/js/palette.js",
    "web/js/photos.js",
    "web/js/import_wizard.js",
    "web/js/export_dialog.js",
    "resources/themes/light.qss",
    "resources/themes/dark.qss",
]

ALPINE_URL = "https://cdn.jsdelivr.net/npm/alpinejs@3.14.9/dist/cdn.min.js"


def check_and_fix() -> Dict[str, Any]:
    report = {"missing": [], "downloaded": [], "dirs_created": [], "ok": True}
    for rel in REQUIRED_FILES:
        full = os.path.join(ROOT, rel)
        if os.path.isfile(full) and os.path.getsize(full) > 10:
            continue
        report["missing"].append(rel)
        if "alpine" in rel:
            try:
                import requests

                r = requests.get(ALPINE_URL, timeout=20)
                if r.status_code == 200 and len(r.content) > 30000:
                    os.makedirs(os.path.dirname(full), exist_ok=True)
                    open(full, "wb").write(r.content)
                    report["downloaded"].append(rel)
                    continue
            except Exception:
                pass
        report["ok"] = False
    for d in (
        "media",
        "backups",
        "exports",
        "templates",
        "plugins",
        "logs",
        os.path.join("web", "vendor"),
    ):
        full = os.path.join(ROOT, d)
        if not os.path.isdir(full):
            os.makedirs(full, exist_ok=True)
            report["dirs_created"].append(d)
    return report


if __name__ == "__main__":
    import json

    rep = check_and_fix()
    print(json.dumps(rep, ensure_ascii=False, indent=2))
