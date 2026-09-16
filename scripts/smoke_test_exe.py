"""Smoke-тест собранного .exe: запуск -> health 200 -> / отдаёт UI -> kill.

Запуск: python scripts/smoke_test_exe.py
"""

import http.client
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "dist", "SUOT_Neo", "SUOT_Neo.exe")
PORT = int(os.environ.get("SUOT_PORT", "8931"))


def main() -> int:
    if not os.path.isfile(EXE):
        print("exe не найден:", EXE)
        return 1
    env = {**os.environ, "SUOT_PORT": str(PORT)}
    proc = subprocess.Popen(
        [EXE],
        cwd=os.path.dirname(EXE),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    ok_health = False
    deadline = time.time() + 40
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode("utf-8", "replace")
            print("процесс завершился рано:\n", out[-800:])
            return 1
        try:
            c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=0.6)
            c.request("GET", "/api/health")
            r = c.getresponse()
            if r.status == 200:
                body = json.loads(r.read())
                ok_health = body.get("status") == "ok"
                break
        except Exception:
            time.sleep(0.4)
    print("health:", "OK" if ok_health else "FAIL")

    ok_ui = False
    try:
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=3)
        c.request("GET", "/")
        r = c.getresponse()
        html = r.read().decode("utf-8", "replace")
        ok_ui = r.status == 200 and ("ОхранаТруда" in html) and "alpine" in html
    except Exception as e:
        print("UI error:", e)
    print("ui:", "OK" if ok_ui else "FAIL")

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    code = 0 if (ok_health and ok_ui) else 1
    print("SMOKE:", "PASS" if code == 0 else "FAIL")
    return code


if __name__ == "__main__":
    sys.exit(main())
