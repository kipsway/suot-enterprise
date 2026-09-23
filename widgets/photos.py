import os
from typing import Any, Optional, List

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
    QFileDialog,
)

from app_core.config import RUNTIME_PATHS
from app_core.i18n import I18n


def _abs_photo_path(path: str) -> str:
    if not path:
        return ""
    if path.startswith("__MEDIA__"):
        return os.path.join(RUNTIME_PATHS.media_dir, path[9:])
    if not os.path.isabs(path):
        return os.path.join(RUNTIME_PATHS.app_dir, path)
    return path


def _rel_photo_path(path: str) -> str:
    try:
        rel = os.path.relpath(path, RUNTIME_PATHS.media_dir)
        if not rel.startswith(".."):
            return "__MEDIA__/" + rel.replace("\\", "/")
        rel2 = os.path.relpath(path, RUNTIME_PATHS.app_dir)
        return rel2.replace("\\", "/")
    except Exception:
        return path


class PhotoPreviewDialog(QDialog):
    def __init__(self, file_path: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle(I18n._("emp.photo"))
        self.setWindowFlags(Qt.Window)
        self.setMinimumSize(800, 600)
        self.resize(1000, 750)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignCenter)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        pix = QPixmap(_abs_photo_path(file_path))
        if not pix.isNull():
            screen = QApplication.primaryScreen().availableGeometry()
            max_w = screen.width() * 0.8
            max_h = screen.height() * 0.8
            pix = pix.scaled(
                int(max_w), int(max_h), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self._label.setPixmap(pix)
            self.setWindowTitle(os.path.basename(file_path))
        else:
            self._label.setText(I18n._("error.file_not_found"))
        scroll.setWidget(self._label)
        layout.addWidget(scroll)
        btn = QPushButton(I18n._("common.close"))
        btn.clicked.connect(self.close)
        layout.addWidget(btn, 0, Qt.AlignCenter)


class PhotoGalleryDialog(QDialog):
    def __init__(self, photos: List[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._photos = [_rel_photo_path(p) for p in (photos or [])]
        self.setWindowTitle(I18n._("emp.photo"))
        self.setMinimumSize(600, 450)
        self.resize(800, 600)
        self.setAcceptDrops(True)
        self._build_ui()
        self._render()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        heading = QLabel(I18n._("emp.photo"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)
        hint = QLabel(I18n._("common.add") + ": drag & drop")
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._grid = QGridLayout(self._content)
        self._grid.setSpacing(12)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton(I18n._("common.add"))
        add_btn.clicked.connect(self._add_photos)
        btn_layout.addWidget(add_btn)
        btn_layout.addStretch()
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _render(self) -> None:
        for i in reversed(range(self._grid.count())):
            item = self._grid.takeAt(i)
            if item and item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
        row, col = 0, 0
        for path in self._photos:
            card = self._create_thumbnail_card(path)
            self._grid.addWidget(card, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1

    def _create_thumbnail_card(self, path: str) -> QFrame:
        abs_path = _abs_photo_path(path)
        card = QFrame()
        card.setProperty("card", True)
        card.setFixedSize(160, 180)
        card.setCursor(QCursor(Qt.PointingHandCursor))
        cl = QVBoxLayout(card)
        cl.setContentsMargins(4, 4, 4, 4)
        cl.setSpacing(4)

        pix = QPixmap(abs_path)
        thumb = (
            pix.scaled(150, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if not pix.isNull()
            else QPixmap()
        )
        img_label = QLabel()
        if not thumb.isNull():
            img_label.setPixmap(thumb)
        else:
            img_label.setText("?")
            img_label.setAlignment(Qt.AlignCenter)
        img_label.setFixedSize(150, 120)
        img_label.setAlignment(Qt.AlignCenter)
        img_label.setStyleSheet("background: #F0F1F3; border-radius: 4px;")
        cl.addWidget(img_label, 0, Qt.AlignCenter)

        name_label = QLabel(os.path.basename(path)[:20])
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font-size: 11px; ;")
        name_label.setWordWrap(True)
        cl.addWidget(name_label)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setProperty("small", True)
        del_btn.clicked.connect(lambda checked, p=path: self._remove_photo(p))
        del_btn.move(130, 4)
        del_btn.setParent(img_label)

        img_label.mouseDoubleClickEvent = lambda e, p=path: self._preview_photo(p)
        return card

    def _add_photos(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            I18n._("common.add"),
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        )
        for f in files:
            rel = _rel_photo_path(f)
            if rel not in self._photos:
                self._photos.append(rel)
        self._render()

    def _remove_photo(self, path: str) -> None:
        if path in self._photos:
            self._photos.remove(path)
        self._render()

    def _preview_photo(self, path: str) -> None:
        dlg = PhotoPreviewDialog(_abs_photo_path(path), self)
        dlg.exec_()

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:
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
                    rel = _rel_photo_path(path)
                    if rel not in self._photos:
                        self._photos.append(rel)
            self._render()
            event.acceptProposedAction()

    def get_photos(self) -> List[str]:
        return self._photos
