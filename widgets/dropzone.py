import os
from typing import Any, Callable, List, Optional

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QWidget,
    QScrollArea,
)

from app_core.config import RUNTIME_PATHS
from app_core.i18n import I18n


class DropZone(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._photos: List[str] = []
        self._on_change: Optional[Callable] = None
        self.setAcceptDrops(True)
        self.setMinimumHeight(80)
        self.setProperty("card", True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        hint_layout = QHBoxLayout()
        self._hint = QLabel("📁 " + I18n._("dropzone.hint"))
        self._hint.setStyleSheet("font-size: 12px; color: #888;")
        self._hint.setAlignment(Qt.AlignCenter)
        hint_layout.addWidget(self._hint)

        self._browse_btn = QPushButton(I18n._("dropzone.browse"))
        self._browse_btn.setProperty("flat", True)
        self._browse_btn.clicked.connect(self._browse)
        hint_layout.addWidget(self._browse_btn)
        layout.addLayout(hint_layout)

        self._scroll = QScrollArea()
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(True)
        self._scroll.setMaximumHeight(100)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._thumb_container = QWidget()
        self._thumb_layout = QHBoxLayout(self._thumb_container)
        self._thumb_layout.setSpacing(6)
        self._thumb_layout.addStretch()
        self._scroll.setWidget(self._thumb_container)
        layout.addWidget(self._scroll)

        self.set_photos([])

    def set_photos(self, paths: List[str]) -> None:
        self._photos = list(paths)
        self._render_thumbs()

    def get_photos(self) -> List[str]:
        return list(self._photos)

    def on_change(self, callback: Callable) -> None:
        self._on_change = callback

    def _browse(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            I18n._("dropzone.browse"),
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All files (*.*)",
        )
        for f in files:
            if f not in self._photos:
                self._photos.append(f)
        self._render_thumbs()
        if self._on_change:
            self._on_change(self._photos)

    def _render_thumbs(self) -> None:
        for i in reversed(range(self._thumb_layout.count())):
            w = self._thumb_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._thumb_layout.addStretch()

        if not self._photos:
            self._hint.show()
            return
        self._hint.hide()

        for path in self._photos:
            thumb = self._make_thumb(path)
            self._thumb_layout.insertWidget(self._thumb_layout.count() - 1, thumb)

    def _make_thumb(self, path: str) -> QFrame:
        card = QFrame()
        card.setFixedSize(80, 80)
        card.setStyleSheet("background: #F0F1F3; border-radius: 6px;")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(2, 2, 2, 2)
        cl.setSpacing(0)

        pix = QPixmap(path)
        thumb = (
            pix.scaled(76, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if not pix.isNull()
            else QPixmap()
        )
        img = QLabel()
        if not thumb.isNull():
            img.setPixmap(thumb)
        else:
            img.setText("?")
        img.setAlignment(Qt.AlignCenter)
        img.setFixedSize(76, 56)
        cl.addWidget(img, 0, Qt.AlignCenter)

        name = os.path.basename(path)[:12]
        name_lbl = QLabel(name)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet("font-size: 9px; color: #666;")
        cl.addWidget(name_lbl, 0, Qt.AlignCenter)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(18, 18)
        del_btn.setStyleSheet(
            "QPushButton { background: #E74C3C; color: white; border-radius: 9px;"
            " font-size: 10px; font-weight: bold; }"
            "QPushButton:hover { background: #C0392B; }"
        )
        del_btn.clicked.connect(lambda checked, p=path: self._remove_photo(p))
        del_btn.move(60, 0)
        del_btn.setParent(card)
        return card

    def _remove_photo(self, path: str) -> None:
        if path in self._photos:
            self._photos.remove(path)
        self._render_thumbs()
        if self._on_change:
            self._on_change(self._photos)

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("border: 2px dashed #2196F3;")

    def dragLeaveEvent(self, event: Any) -> None:
        self.setStyleSheet("")

    def dropEvent(self, event: Any) -> None:
        self.setStyleSheet("")
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                ext = os.path.splitext(path)[1].lower()
                if ext in (
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".bmp",
                    ".gif",
                    ".webp",
                ) and os.path.isfile(path):
                    if path not in self._photos:
                        self._photos.append(path)
            self._render_thumbs()
            if self._on_change:
                self._on_change(self._photos)
            event.acceptProposedAction()
