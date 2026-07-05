from PyQt5.QtWidgets import QApplication


class SafeApplication(QApplication):
    def notify(self, receiver, event):
        try:
            return super().notify(receiver, event)
        except Exception:
            import traceback
            traceback.print_exc()
            return False
