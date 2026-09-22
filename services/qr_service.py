"""QR code generation and scanning."""

import io
import os
import tempfile
from typing import List, Optional

from PyQt5.QtCore import QByteArray, QBuffer
from PyQt5.QtGui import QImage, QPixmap


def generate_qr(data: str, box_size: int = 10, border: int = 2) -> Optional[QPixmap]:
    try:
        import qrcode
        from qrcode.image.pil import PilImage

        qr = qrcode.QRCode(box_size=box_size, border=border)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue())
        return pixmap
    except ImportError:
        return None


def generate_qr_to_file(
    data: str, output_path: str, box_size: int = 10, border: int = 2
) -> bool:
    try:
        import qrcode

        qr = qrcode.QRCode(box_size=box_size, border=border)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(output_path)
        return True
    except ImportError:
        return False


def scan_qr(image_path: str) -> List[str]:
    try:
        from pyzbar.pyzbar import decode
        from PIL import Image

        results = decode(Image.open(image_path))
        return [r.data.decode("utf-8", errors="replace") for r in results]
    except ImportError:
        return []


def scan_qr_from_pixmap(pixmap: QPixmap) -> List[str]:
    try:
        from pyzbar.pyzbar import decode
        from PIL import Image

        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        pixmap.save(buffer, "PNG")
        buffer.seek(0)
        img = Image.open(io.BytesIO(buffer.data()))
        results = decode(img)
        return [r.data.decode("utf-8", errors="replace") for r in results]
    except ImportError:
        return []
