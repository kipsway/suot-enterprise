"""First-run setup: installs dependencies, creates directories, initializes config."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = [
    "PyQt5>=5.15.0",
    "requests>=2.28.0",
    "openpyxl>=3.1.0",
    "python-docx>=1.1.0",
    "cryptography>=41.0.0",
    "pillow>=10.0.0",
    "python-telegram-bot>=20.0",
    "schedule>=1.2.0",
    "qrcode>=7.4.0",
    "pyzbar>=0.1.9",
    "opencv-python>=4.8.0",
    "vosk>=0.3.45",
    "beautifulsoup4>=4.12.0",
    "sseclient-py>=0.1.0",
    "reportlab>=4.0.0",
    "ldap3>=2.9.0",
]


def print_step(msg: str) -> None:
    print(f"  \u2022 {msg}")


def check_python() -> bool:
    if sys.version_info < (3, 10):
        print(
            f"  \u2716 Python 3.10+ required (current: {sys.version_info.major}.{sys.version_info.minor})"
        )
        return False
    print(
        f"  \u2714 Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    return True


def install_deps() -> bool:
    print_step("Installing / upgrading pip...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    print_step(f"Installing {len(REQUIREMENTS)} packages...")
    subprocess.check_call([sys.executable, "-m", "pip", "install"] + REQUIREMENTS)
    return True


def create_dirs() -> None:
    for d in ["resources/icons", "resources/sounds", "resources/themes", "build"]:
        (ROOT / d).mkdir(parents=True, exist_ok=True)
        print_step(f"Directory {d}/ ensured")


def verify_imports() -> bool:
    modules = [
        ("PyQt5.QtWidgets", "QApplication"),
        ("cryptography.fernet", "Fernet"),
        ("openpyxl", "Workbook"),
        ("docx", "Document"),
        ("PIL", "Image"),
        ("reportlab.lib.pagesizes", "A4"),
    ]
    ok = True
    for mod, attr in modules:
        try:
            __import__(mod, fromlist=[attr])
        except ImportError:
            print_step(f"\u2716 {mod} — FAILED")
            ok = False
    if ok:
        print_step("All critical imports verified")
    return ok


def write_requirements() -> None:
    path = ROOT / "requirements.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(REQUIREMENTS) + "\n")
    print_step("requirements.txt written")


def main() -> None:
    banner = r"""
   ╔══════════════════════════════════════════╗
   ║     СУОТ Enterprise — First-Run Setup    ║
   ╚══════════════════════════════════════════╝
    """
    print(banner)
    steps = [
        ("Python version", check_python),
        ("Creating directories", create_dirs),
        ("Writing requirements.txt", write_requirements),
        ("Installing dependencies (~200 MB)", install_deps),
        ("Verifying imports", verify_imports),
    ]
    for name, func in steps:
        print(f"\n[{name}]")
        try:
            func()
        except Exception as e:
            print(f"  \u2716 {e}")
            print("\n  Setup incomplete. Try: python scripts/setup.py")
            sys.exit(1)
    print("\n" + "=" * 50)
    print("  Setup complete! Run: python main.py")
    print("=" * 50)


if __name__ == "__main__":
    main()
