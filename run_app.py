#!/usr/bin/env python3
"""Entry point for Docker deployment. Supports headless REST API mode."""

import os
import sys


def main() -> None:
    if os.environ.get("SUOT_HEADLESS", "0") == "1":
        from services.rest_api import RESTAPIServer

        server = RESTAPIServer()
        print("Starting SUOT REST API server on port 8888...")
        server.start()
        try:
            import time

            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("Shutting down...")
    else:
        from PyQt5.QtWidgets import QApplication
        from modules.login import LoginDialog
        from modules.main_window import MainWindow

        app = QApplication(sys.argv)
        app.setApplicationName("SUOT Enterprise")

        dlg = LoginDialog()
        if dlg.exec_() != LoginDialog.Accepted:
            sys.exit(0)
        user = dlg.authenticated_user()

        window = MainWindow(user=user)
        window.show()
        sys.exit(app.exec_())


if __name__ == "__main__":
    main()
