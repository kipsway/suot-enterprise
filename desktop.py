"""ОхранаТруда Про — запуск десктоп-окна (pywebview) поверх локального API.

Фолбэк: если WebView2 недоступен — интерфейс открывается в системном браузере.
Старая Qt-версия по-прежнему запускается через main.py.
"""

import sys, os, time, http.client, threading, webbrowser, traceback

HOST = "127.0.0.1"
PORT = int(os.environ.get("SUOT_PORT", "8899"))
URL = f"http://{HOST}:{PORT}"

LOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(sys.executable))
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__)),
    "suot_neo.log",
)


def _log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")
    except Exception:
        pass


def _fix_streams() -> None:
    # windowed-сборка: sys.stdout/stderr = None — uvicorn падает при логировании
    if sys.stdout is None or sys.stderr is None:
        try:
            import io

            err = io.StringIO()
            sys.stdout = err
            sys.stderr = err
        except Exception:
            pass


def _start_server() -> "uvicorn.Server":
    import uvicorn
    from server.app import app

    config = uvicorn.Config(
        app, host=HOST, port=PORT, log_level="warning", log_config=None
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    return server


def _wait_ready(timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            c = http.client.HTTPConnection(HOST, PORT, timeout=0.4)
            c.request("GET", "/api/health")
            if c.getresponse().status == 200:
                return True
        except Exception:
            time.sleep(0.15)
    return False


def main() -> int:
    _fix_streams()
    _log("Запуск сервера…")
    try:
        import server.app  # noqa: force import of the app

        _log("Импорт server.app: OK")
    except Exception as e:
        _log("ОШИБКА: не удалось импортировать применяемое приложение: %r" % e)
        traceback.print_exc()
        return 1
    server = _start_server()
    _log("uvicorn.Config создан: %s" % PORT)
    threading.Timer(
        2.0, lambda: _log("threads alive: %d" % threading.active_count())
    ).start()
    if not _wait_ready():
        _log("ОШИБКА: сервер не поднялся")
        try:
            import app_core.config as cfg

            _log("Папка приложения: %s" % cfg.RUNTIME_PATHS.app_dir)
            _log("Путь БД: %s" % cfg.RUNTIME_PATHS.database_path)
            writable = os.access(
                os.path.dirname(cfg.RUNTIME_PATHS.database_path), os.W_OK
            )
            _log("Право записи в папку: %s" % writable)
        except Exception as ex:
            _log("Диагностика путей не удалась: %r" % ex)
        traceback.print_exc()
        return 1
    _log("API готов: %s/api/health" % URL)

    try:
        import webview

        webview.create_window(
            "ОхранаТруда Про",
            URL,
            width=1440,
            height=900,
            min_size=(1100, 680),
            background_color="#0F1115",
        )
        _log("Открываю окно приложения…")
        webview.start()
        _log("Окно закрыто.")
        return 0
    except Exception as e:
        _log("WebView недоступен (%r) — открываю в браузере." % e)
        traceback.print_exc()
        webbrowser.open(URL)
        _log("Работает в браузере.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
