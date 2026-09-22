"""Auto-update script: checks GitHub releases and applies updates."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen

from services.database import DatabaseManager


class UpdateChecker:
    REPO = "user/suot-enterprise"
    UPDATE_INTERVAL_DAYS = 1

    def __init__(self) -> None:
        self.db = DatabaseManager()

    def check_now(self) -> Dict[str, Any]:
        try:
            url = f"https://api.github.com/repos/{self.REPO}/releases/latest"
            req = Request(
                url,
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "SUOT-Enterprise",
                },
            )
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())

            current_ver = self._current_version()
            latest_ver = data.get("tag_name", "").lstrip("v")
            assets = data.get("assets", [])

            download_url = ""
            for asset in assets:
                if asset["name"].endswith(".zip"):
                    download_url = asset["browser_download_url"]
                    break

            return {
                "current_version": current_ver,
                "latest_version": latest_ver,
                "update_available": self._compare_versions(latest_ver, current_ver) > 0,
                "download_url": download_url,
                "release_notes": data.get("body", "")[:2000],
                "published_at": data.get("published_at", ""),
            }
        except Exception as e:
            return {"error": str(e)}

    def apply_update(self, download_url: str) -> bool:
        try:
            tmp_dir = tempfile.mkdtemp(prefix="suot_update_")
            zip_path = os.path.join(tmp_dir, "update.zip")

            req = Request(download_url, headers={"User-Agent": "SUOT-Enterprise"})
            with urlopen(req, timeout=120) as resp:
                with open(zip_path, "wb") as f:
                    f.write(resp.read())

            extract_dir = os.path.join(tmp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            exclude = {"data", "backups", "media", "config"}

            for item in os.listdir(extract_dir):
                src = os.path.join(extract_dir, item)
                dst = os.path.join(app_dir, item)
                if os.path.basename(item) in exclude:
                    continue
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

            shutil.rmtree(tmp_dir, ignore_errors=True)
            self.db.upsert_setting("last_update", datetime.now().isoformat())
            return True
        except Exception:
            return False

    def _current_version(self) -> str:
        return self.db.get_setting("app_version", "1.0.0")

    @staticmethod
    def _compare_versions(v1: str, v2: str) -> int:
        parts1 = [int(x) for x in v1.split(".")]
        parts2 = [int(x) for x in v2.split(".")]
        for a, b in zip(parts1, parts2):
            if a != b:
                return a - b
        return len(parts1) - len(parts2)


def main() -> None:
    checker = UpdateChecker()
    result = checker.check_now()

    if "error" in result:
        print(f"Update check failed: {result['error']}")
        sys.exit(1)

    print(f"Current version: {result['current_version']}")
    print(f"Latest version: {result['latest_version']}")
    print(f"Update available: {result['update_available']}")

    if result["update_available"] and result.get("download_url"):
        print("Applying update...")
        if checker.apply_update(result["download_url"]):
            print("Update applied successfully. Please restart the application.")
        else:
            print("Update failed.")
            sys.exit(1)


if __name__ == "__main__":
    main()
