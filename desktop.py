"""ОхранаТруда Про — запуск десктоп-окна (pywebview) поверх локального API.

Фолбэк: если WebView2 недоступен — интерфейс открывается в системном браузере.
Старая Qt-версия по-прежнему запускается через main.py.
"""

import sys, os, time, http.client, threading, webbrowser, traceback

HOST = "127.0.0.1"
PORT = int(os.environ.get("SUOT_PORT", "8899"))


def _log_path() -> str:
    """Лог рядом с exe; если папка недоступна для записи (Program Files
    без прав) — в %LOCALAPPDATA%\\SUOT_Neo, иначе диагностика теряется."""
    exe_dir = (
        os.path.dirname(os.path.abspath(sys.executable))
        if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__))
    )
    try:
        if os.access(exe_dir, os.W_OK):
            return os.path.join(exe_dir, "suot_neo.log")
    except Exception:
        pass
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "SUOT_Neo")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return os.path.join(d, "suot_neo.log")


LOG_PATH = _log_path()


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


# Один экземпляр приложения: не даём открыть второе окно на том же сервере.
_MUTEX_NAME = "SUOT_Neo_SingleInstance_v1"
_mutex_handle = None


def _acquire_single_instance() -> bool:
    """True — мы единственный экземпляр; False — уже запущен другой."""
    global _mutex_handle
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        _mutex_handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
        ERROR_ALREADY_EXISTS = 183
        return kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        return True


def _resolve_port() -> int:
    """Если порт занят чужим процессом — берём свободный (фронт ходит
    относительными /api, номер порта ему безразличен)."""
    import socket

    probe = socket.socket()
    try:
        probe.bind((HOST, PORT))
        return PORT
    except OSError:
        _log("Порт %d занят — подбираю свободный." % PORT)
        probe.close()
        free = socket.socket()
        free.bind((HOST, 0))
        port = int(free.getsockname()[1])
        free.close()
        return port
    finally:
        try:
            probe.close()
        except Exception:
            pass


def _start_server(port: int) -> "tuple":
    import uvicorn
    from server.app import app

    config = uvicorn.Config(
        app, host=HOST, port=port, log_level="warning", log_config=None
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def _wait_ready(port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        c = None
        try:
            c = http.client.HTTPConnection(HOST, port, timeout=0.4)
            c.request("GET", "/api/health")
            resp = c.getresponse()
            body = resp.read().decode("utf-8", "replace")
            # Проверяем тело, а не только 200: на порту может висеть чужой сервис.
            if resp.status == 200 and '"status"' in body and "ok" in body:
                return True
        except Exception:
            pass
        finally:
            try:
                if c is not None:
                    c.close()
            except Exception:
                pass
        time.sleep(0.2)
    return False


def main() -> int:
    _fix_streams()
    if not _acquire_single_instance():
        _log("Уже запущен другой экземпляр — второе окно не открываем.")
        return 0
    _log("Запуск сервера…")
    try:
        import server.app  # noqa: force import of the app

        _log("Импорт server.app: OK")
    except Exception as e:
        _log("ОШИБКА: не удалось импортировать применяемое приложение: %r" % e)
        traceback.print_exc()
        return 1
    port = _resolve_port()
    url = f"http://{HOST}:{port}"
    server, thread = _start_server(port)
    _log("uvicorn.Config создан: %s" % port)
    if not _wait_ready(port):
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
    _log("API готов: %s/api/health" % url)

    try:
        import webview

        webview.create_window(
            "ОхранаТруда Про",
            url,
            width=1440,
            height=900,
            min_size=(1100, 680),
            background_color="#0F1115",
        )
        _log("Открываю окно приложения…")
        webview.start()
        _log("Окно закрыто — останавливаю сервер…")
    except Exception as e:
        _log("WebView недоступен (%r) — открываю в браузере." % e)
        traceback.print_exc()
        try:
            ok = webbrowser.open(url)
            _log("Браузер открыт: %s" % ok)
        except Exception as be:
            _log("Не удалось открыть браузер: %r" % be)
            return 1
        _log("Работает в браузере.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            _log("Остановка по запросу.")
    finally:
        # Даём uvicorn завершить запросы и сбросить WAL, иначе daemon-поток
        # убивается в середине записи.
        try:
            server.should_exit = True
            thread.join(timeout=8)
        except Exception as se:
            _log("Остановка сервера: %r" % se)
    return 0


if __name__ == "__main__":
    sys.exit(main())
