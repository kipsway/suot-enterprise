"""Camera capture service via OpenCV."""

import os
import tempfile
from typing import List, Optional

from PyQt5.QtCore import QBuffer, QByteArray
from PyQt5.QtGui import QImage, QPixmap


class CameraService:
    def __init__(self, camera_index: int = 0):
        self._index = camera_index
        self._cap = None

    def is_available(self) -> bool:
        try:
            import cv2

            return True
        except ImportError:
            return False

    @staticmethod
    def list_cameras() -> List[int]:
        try:
            import cv2

            available = []
            for i in range(8):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    available.append(i)
                cap.release()
            return available
        except ImportError:
            return []

    def open(self) -> bool:
        if not self.is_available():
            return False
        import cv2

        self._cap = cv2.VideoCapture(self._index)
        return self._cap.isOpened()

    def close(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

    def capture_frame(self) -> Optional[QImage]:
        if not self._cap or not self._cap.isOpened():
            return None
        import cv2

        ret, frame = self._cap.read()
        if not ret:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QImage(rgb.data, w, h, w * ch, QImage.Format_RGB888)

    def capture_to_file(self, path: Optional[str] = None) -> Optional[str]:
        qimg = self.capture_frame()
        if qimg is None:
            return None
        out = path or tempfile.mktemp(suffix=".jpg")
        qimg.save(out, "JPG", 90)
        return out

    def capture_to_pixmap(self) -> Optional[QPixmap]:
        qimg = self.capture_frame()
        if qimg is None:
            return None
        return QPixmap.fromImage(qimg)
