"""Единая точка прогона тестов проекта.

Использование:
    python scripts/run_all_tests.py            # быстрые серверные + pytest-наборы
    python scripts/run_all_tests.py --e2e      # + браузерный smoke (wizard, EN)
    python scripts/run_all_tests.py --exe      # + smoke собранного dist\\SUOT_Neo\\SUOT_Neo.exe
    python scripts/run_all_tests.py --all      # всё, включая полный e2e-цикл

Каждый набор — отдельный скрипт tests/test_*.py (PASS/FAIL в stdout).
unittest/pytest-наборы (UNIT_SUITES) гоняются через `pytest -q` и парсятся по
строке "N passed". Smoke exe запускается только если exe реально собран.
Итог: таблица результатов + код выхода 0 (все зелёные) или 1.
"""

import argparse
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERVER_SUITES = [
    ("test_security_audit", 600),
    ("test_part1_server", 600),
    ("test_part24_server", 600),
    ("test_part25_server", 600),
    ("test_part26_server", 600),
    ("test_part27_server", 600),
    ("test_part28_server", 600),
    ("test_part30_server", 600),
    ("test_import_master", 600),
    ("test_export", 300),
    ("test_print", 300),
    ("test_pdf", 300),
    ("test_setup21", 300),
    ("test_help18", 300),
    ("test_settings17", 300),
    ("test_backup19", 300),
    ("test_reminders", 300),
    ("test_search_reports", 300),
    ("test_ai", 300),
    ("test_plugins19", 300),
    ("test_tasks_server", 600),
    ("test_views_server", 600),
]

# unittest/pytest-наборы без маркера "N OK, N FAIL" — гоняются через pytest.
UNIT_SUITES = [
    ("test_security", 300),
    ("test_cli", 300),
    ("test_enterprise", 300),
]

E2E_SMOKE = [
    ("test_wizard_e2e", 900),
    ("test_part29_en_e2e", 900),
    ("test_ux_focus_e2e", 600),
    ("test_next_nav_e2e", 600),
    ("test_nav_parity_e2e", 600),
]

# Smoke собранного exe: только если dist\SUOT_Neo\SUOT_Neo.exe существует.
EXE_SMOKE = [
    ("scripts/smoke_test_exe.py", 300),
]


# Полный e2e-цикл для --all: автодискавери всех tests/test_*.py,
# не вошедших в списки выше (каждый грузит свой сервер; долго).
def _discover_extra():
    seen = {n for n, _ in SERVER_SUITES + UNIT_SUITES + E2E_SMOKE}
    extra = []
    for fn in sorted(os.listdir(os.path.join(ROOT, "tests"))):
        if fn.startswith("test_") and fn.endswith(".py"):
            name = fn[:-3]
            if name not in seen and name != "__init__":
                extra.append((name, 900))
    return extra


# Таймауты для известных тяжёлых наборов в режиме --all.
HEAVY_TIMEOUTS = {"test_part2_e2e": 1500}

MARKER = re.compile(r"(\d+)\s+OK,\s+(\d+)\s+FAIL")


def run_suite(name: str, timeout: int):
    if "/" in name or "\\" in name:
        path = os.path.join(ROOT, name.replace("/", os.sep))
    else:
        path = os.path.join(ROOT, "tests", name + ".py")
    if not os.path.isfile(path):
        return {"name": name, "status": "SKIP (нет файла)", "ok": 0, "fail": 0}
    t0 = time.time()
    try:
        p = subprocess.run(
            [sys.executable, path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        out = (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return {
            "name": name,
            "status": f"FAIL (timeout {timeout}s)",
            "ok": 0,
            "fail": 1,
            "secs": int(time.time() - t0),
        }
    matches = MARKER.findall(out)
    secs = int(time.time() - t0)
    if matches:
        ok_n, fail_n = int(matches[-1][0]), int(matches[-1][1])
        status = "PASS" if fail_n == 0 and p.returncode == 0 else "FAIL"
        result = {
            "name": name,
            "status": status,
            "ok": ok_n,
            "fail": fail_n,
            "secs": secs,
        }
        if status == "FAIL":
            # Хвост вывода, чтобы видеть причину падения в CI-логе.
            lines = out.strip().splitlines()
            interesting = [
                ln for ln in lines if "FAIL " in ln or "Error" in ln or "error" in ln
            ]
            result["tail"] = "\n".join((interesting or lines)[-15:])
        return result
    if p.returncode != 0:
        tail = "\n".join(out.strip().splitlines()[-3:])
        return {
            "name": name,
            "status": "FAIL (rc!=0, нет маркера)",
            "ok": 0,
            "fail": 1,
            "secs": secs,
            "tail": tail,
        }
    return {
        "name": name,
        "status": "WARN (нет маркера, rc=0)",
        "ok": 0,
        "fail": 0,
        "secs": secs,
    }


def run_pytest_suite(name: str, timeout: int):
    """Прогон unittest/pytest-набора (без маркера 'N OK, N FAIL')."""
    path = os.path.join(ROOT, "tests", name + ".py")
    if not os.path.isfile(path):
        return {"name": name, "status": "SKIP (нет файла)", "ok": 0, "fail": 0}
    t0 = time.time()
    try:
        p = subprocess.run(
            [sys.executable, "-m", "pytest", path, "-q", "--no-header"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            env={**os.environ, "PYTHONPATH": ROOT},
        )
        out = (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return {
            "name": name,
            "status": f"FAIL (timeout {timeout}s)",
            "ok": 0,
            "fail": 1,
            "secs": int(time.time() - t0),
        }
    secs = int(time.time() - t0)
    m = re.findall(r"(\d+) passed", out)
    ok_n = int(m[-1]) if m else 0
    mf = re.findall(r"(\d+) (?:failed|error)", out)
    fail_n = int(mf[-1]) if mf else (0 if p.returncode == 0 else 1)
    if p.returncode != 0 and not m:
        tail = "\n".join(out.strip().splitlines()[-25:])
        return {
            "name": name,
            "status": "FAIL (rc!=0)",
            "ok": 0,
            "fail": fail_n,
            "secs": secs,
            "tail": tail,
        }
    status = "PASS" if p.returncode == 0 and fail_n == 0 else "FAIL"
    result = {"name": name, "status": status, "ok": ok_n, "fail": fail_n, "secs": secs}
    if status == "FAIL":
        # Хвост вывода pytest, чтобы видеть упавшие тесты в CI-логе.
        lines = out.strip().splitlines()
        interesting = [ln for ln in lines if ln.startswith("FAILED") or "Error" in ln]
        result["tail"] = "\n".join((interesting or lines)[-25:])
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--e2e", action="store_true", help="плюс браузерный smoke-набор")
    ap.add_argument(
        "--all", action="store_true", help="все наборы, включая полный e2e-цикл"
    )
    ap.add_argument(
        "--exe",
        action="store_true",
        help="плюс smoke собранного dist\\SUOT_Neo\\SUOT_Neo.exe",
    )
    args = ap.parse_args()

    suites = list(SERVER_SUITES)
    if args.e2e or args.all:
        suites += E2E_SMOKE
    if args.all:
        suites += [(n, HEAVY_TIMEOUTS.get(n, 900)) for n, _ in _discover_extra()]

    unit_suites = list(UNIT_SUITES)
    exe_suites = []
    if args.exe or args.all:
        exe_path = os.path.join(ROOT, "dist", "SUOT_Neo", "SUOT_Neo.exe")
        if os.path.isfile(exe_path):
            exe_suites = list(EXE_SMOKE)
        else:
            print(f"--- smoke exe пропущен (нет {exe_path})", flush=True)

    total_suites = len(suites) + len(unit_suites) + len(exe_suites)
    print(f"Наборов: {total_suites} (root={ROOT})\n")
    results = []
    for name, timeout in suites:
        print(f"--- {name} ...", flush=True)
        r = run_suite(name, timeout)
        results.append(r)
        extra = f" [{r['ok']} OK, {r['fail']} FAIL]" if "ok" in r else ""
        print(f"    {r['status']}{extra} ({r.get('secs', 0)}s)")
        if r.get("tail"):
            print("    " + r["tail"].replace("\n", "\n    "))

    for name, timeout in unit_suites + exe_suites:
        label = name if name.startswith("scripts/") else f"{name} (pytest)"
        print(f"--- {label} ...", flush=True)
        if name.endswith(".py") and name.startswith("scripts/"):
            r = run_suite(name, timeout)
        else:
            r = run_pytest_suite(name, timeout)
        r["name"] = label
        results.append(r)
        extra = f" [{r['ok']} OK, {r['fail']} FAIL]" if "ok" in r else ""
        print(f"    {r['status']}{extra} ({r.get('secs', 0)}s)")
        if r.get("tail"):
            print("    " + r["tail"].replace("\n", "\n    "))

    print("\n=== ИТОГ ===")
    total_ok = sum(r.get("ok", 0) for r in results)
    total_fail = sum(r.get("fail", 0) for r in results)
    bad = [r for r in results if r["status"] != "PASS"]
    for r in results:
        print(f"  {r['status']:24} {r['name']}")
    print(
        f"\nПроверок: {total_ok} OK, {total_fail} FAIL; "
        f"наборов с проблемами: {len(bad)}"
    )
    return 1 if (bad or total_fail) else 0


if __name__ == "__main__":
    raise SystemExit(main())
