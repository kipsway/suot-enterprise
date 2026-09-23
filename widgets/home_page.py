from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPainter, QPainterPath, QPen, QColor
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QDialog,
    QDialogButtonBox,
)

from app_core.design_tokens import RADIUS, palette
from app_core.theme_engine import ThemeEngine
from app_core.i18n import I18n
from services.database import DatabaseManager
from widgets.glass_button import GlassButton
from widgets.toast import ToastNotification


_STAT_CARDS = [
    ("Всего сотрудников", "employees", lambda r: len(r)),
    (
        "Нарушений (мес.)",
        "violations",
        lambda r: sum(
            1
            for rec in r
            if "data_json" in rec
            and isinstance(rec.get("data_json"), dict)
            and rec["data_json"]
            .get("date", "")
            .startswith(datetime.now().strftime("%Y-%m"))
        ),
    ),
    (
        "Происшествий (мес.)",
        "incidents",
        lambda r: sum(
            1
            for rec in r
            if "data_json" in rec
            and isinstance(rec.get("data_json"), dict)
            and rec["data_json"]
            .get("date", "")
            .startswith(datetime.now().strftime("%Y-%m"))
        ),
    ),
]


class _TileButton(QPushButton):
    def __init__(
        self, label: str, icon: str, color: str, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._emoji = icon
        self._label_color = color
        self.setText(f"{icon}  {label}")
        self.setFixedSize(160, 100)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = ThemeEngine._current_theme == "dark"
        pal = palette(dark)
        r = 12
        from PyQt5.QtCore import QRectF

        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), r, r)
        bg = QColor(pal.bg_secondary)
        p.fillPath(path, bg)
        p.setPen(QPen(QColor(pal.border), 0.5))
        p.drawPath(path)
        p.setPen(QColor(self._label_color))
        f = self.font()
        f.setPointSize(10)
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, self.text())
        p.end()


class _StatCard(QFrame):
    def __init__(
        self, label: str, value: str, color: str, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._value = value
        self._color = color
        self.setFixedSize(200, 90)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = ThemeEngine._current_theme == "dark"
        pal = palette(dark)
        r = 12
        from PyQt5.QtCore import QRectF

        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), r, r)
        bg = QColor(pal.bg_secondary)
        p.fillPath(path, bg)
        p.setPen(QPen(QColor(pal.border), 0.5))
        p.drawPath(path)
        p.setPen(QColor(self._color))
        f = self.font()
        f.setPointSize(22)
        f.setBold(True)
        p.setFont(f)
        p.drawText(
            self.rect().adjusted(16, 12, -16, -8),
            Qt.AlignLeft | Qt.AlignBottom,
            self._value,
        )
        p.setPen(QColor(pal.text_secondary))
        f.setPointSize(10)
        f.setBold(False)
        p.setFont(f)
        p.drawText(
            self.rect().adjusted(16, 8, -16, -16),
            Qt.AlignLeft | Qt.AlignTop,
            self._label,
        )
        p.end()


class HomePage(QWidget):
    navigateTo = pyqtSignal(str)

    def __init__(
        self, user: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._user = user or {}
        self._db = DatabaseManager()
        self._edit_mode = False
        self._build_ui()
        ThemeEngine.on_change(self._rebuild)

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(24)

        layout.addLayout(self._build_header())
        layout.addLayout(self._build_stats())
        layout.addLayout(self._build_modules())
        layout.addLayout(self._build_recent())

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _rebuild(self) -> None:
        old_layout = self.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
                elif item and item.layout():
                    sub = item.layout()
                    while sub.count():
                        sub_item = sub.takeAt(0)
                        if sub_item and sub_item.widget():
                            sub_item.widget().deleteLater()
            from PyQt5 import sip

            sip.delete(old_layout)
        self._build_ui()

    def _build_header(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        name = self._user.get("full_name", self._user.get("username", "Пользователь"))
        title = QLabel(f"С возвращением, {name}")
        f = self.font()
        f.setPointSize(22)
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)
        subtitle = QLabel(datetime.now().strftime("%A, %d %B %Y"))
        f2 = self.font()
        f2.setPointSize(12)
        subtitle.setFont(f2)
        dark = ThemeEngine._current_theme == "dark"
        subtitle.setStyleSheet(f"color: {palette(dark).text_secondary}")
        layout.addWidget(subtitle)
        return layout

    def _build_stats(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(12)
        db = DatabaseManager()
        for label, table, fn in _STAT_CARDS:
            records = db.get_json_records(table)
            val = str(fn(records))
            card = _StatCard(label, val, "#007AFF")
            layout.addWidget(card)
        layout.addStretch()
        return layout

    def _build_modules(self) -> QVBoxLayout:
        outer = QVBoxLayout()
        header = QHBoxLayout()
        htitle = QLabel("Модули")
        f = self.font()
        f.setPointSize(14)
        f.setBold(True)
        htitle.setFont(f)
        header.addWidget(htitle)
        header.addStretch()

        self._edit_toggle = GlassButton("⚙️")
        self._edit_toggle.setFixedSize(32, 32)
        self._edit_toggle.setProperty("flat", True)
        self._edit_toggle.setToolTip("Настроить плитки")
        self._edit_toggle.setCheckable(True)
        self._edit_toggle.toggled.connect(self._toggle_edit_mode)
        header.addWidget(self._edit_toggle)
        outer.addLayout(header)

        self._tiles_layout = QHBoxLayout()
        self._tiles_layout.setSpacing(12)
        self._rebuild_tiles()
        outer.addLayout(self._tiles_layout)

        self._add_panel_widget = QWidget()
        self._add_panel = QHBoxLayout(self._add_panel_widget)
        self._add_panel.setSpacing(8)
        self._add_panel_widget.setVisible(False)
        outer.addWidget(self._add_panel_widget)

        return outer

    def _rebuild_tiles(self) -> None:
        while self._tiles_layout.count():
            item = self._tiles_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        tiles = self._db.load_home_layout()
        for i, t in enumerate(tiles):
            self._tiles_layout.addWidget(self._make_tile(t, i, len(tiles)))
        self._tiles_layout.addStretch()

    def _make_tile(self, t: Dict[str, Any], index: int, total: int) -> QWidget:
        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(2)

        btn = _TileButton(
            t.get("label", ""), t.get("icon", "📁"), t.get("color", "#007AFF")
        )
        btn.clicked.connect(
            lambda checked, k=t["key"]: self.navigateTo.emit(f"tab.{k}")
        )
        cl.addWidget(btn)

        if self._edit_mode:
            controls = QHBoxLayout()
            controls.setSpacing(2)
            left_btn = GlassButton("◀")
            left_btn.setFixedSize(24, 20)
            left_btn.setProperty("flat", True)
            left_btn.setEnabled(index > 0)
            left_btn.clicked.connect(
                lambda checked, idx=index: self._move_tile(idx, -1)
            )
            controls.addWidget(left_btn)

            right_btn = GlassButton("▶")
            right_btn.setFixedSize(24, 20)
            right_btn.setProperty("flat", True)
            right_btn.setEnabled(index < total - 1)
            right_btn.clicked.connect(
                lambda checked, idx=index: self._move_tile(idx, 1)
            )
            controls.addWidget(right_btn)

            remove_btn = GlassButton("✕")
            remove_btn.setFixedSize(24, 20)
            remove_btn.setProperty("flat", True)
            remove_btn.setStyleSheet("color: #FF3B30;")
            remove_btn.clicked.connect(lambda checked, k=t["key"]: self._remove_tile(k))
            controls.addWidget(remove_btn)
            cl.addLayout(controls)

        return container

    def _move_tile(self, index: int, direction: int) -> None:
        tiles = self._db.load_home_layout()
        new_idx = index + direction
        if new_idx < 0 or new_idx >= len(tiles):
            return
        tiles[index], tiles[new_idx] = tiles[new_idx], tiles[index]
        self._db.save_home_layout(tiles)
        self._rebuild_tiles()

    def _remove_tile(self, key: str) -> None:
        tiles = self._db.load_home_layout()
        tiles = [t for t in tiles if t["key"] != key]
        self._db.save_home_layout(tiles)
        self._rebuild_tiles()
        self._refresh_add_panel()

    def _toggle_edit_mode(self, enabled: bool) -> None:
        self._edit_mode = enabled
        self._edit_toggle.setText("✓" if enabled else "⚙️")
        self._add_panel_widget.setVisible(enabled)
        if enabled:
            self._refresh_add_panel()
        self._rebuild_tiles()

    def _refresh_add_panel(self) -> None:
        while self._add_panel.count():
            item = self._add_panel.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        available = self._db.all_available_modules()
        for mod in available:
            if mod["visible"]:
                continue
            btn = GlassButton(f"+ {mod['icon']} {mod['label']}")
            btn.setProperty("flat", True)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda checked, m=mod: self._add_tile(m))
            self._add_panel.addWidget(btn)
        if self._add_panel.count() == 0:
            label = QLabel("Все модули уже добавлены")
            self._add_panel.addWidget(label)
        self._add_panel.addStretch()

    def _add_tile(self, mod: Dict[str, Any]) -> None:
        tiles = self._db.load_home_layout()
        tiles.append(
            {
                "key": mod["key"],
                "label": mod["label"],
                "color": mod["color"],
                "icon": mod["icon"],
            }
        )
        self._db.save_home_layout(tiles)
        self._refresh_add_panel()
        self._rebuild_tiles()
        ToastNotification.notify(f"Добавлено: {mod['label']}", "success", 2000)

    def _build_recent(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        title = QLabel("Последние записи")
        f = self.font()
        f.setPointSize(14)
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)

        recent: List[Dict[str, Any]] = []
        db = DatabaseManager()
        tables = ["incidents", "violations", "employees", "ppe"]
        for t in tables:
            records = db.get_json_records(t)
            for rec in records[:5]:
                dj = rec.get("data_json", {})
                recent.append(
                    {
                        "table": t,
                        "id": rec.get("id", 0),
                        "title": dj.get(
                            "name",
                            dj.get("full_name", dj.get("title", f"#{rec['id']}")),
                        ),
                        "date": dj.get("date", ""),
                        "description": str(
                            dj.get(
                                "description", dj.get("notes", dj.get("position", ""))
                            )
                            or ""
                        )[:60],
                    }
                )

        recent.sort(key=lambda x: x.get("date", ""), reverse=True)
        recent = recent[:10]

        dark = ThemeEngine._current_theme == "dark"
        pal = palette(dark)
        for i, rec in enumerate(recent):
            row = QHBoxLayout()
            row.setSpacing(8)

            icon = QLabel(rec.get("title", "—")[:2])
            icon.setFixedSize(32, 32)
            icon.setAlignment(Qt.AlignCenter)
            icon.setStyleSheet(f"""
                QLabel {{
                    background: {pal.bg_tertiary};
                    border-radius: 6px;
                    font-size: 14px;
                    color: {pal.text_primary};
                }}
            """)
            row.addWidget(icon)

            text = QLabel(f"<b>{rec['title']}</b> — {rec['description']}")
            text.setStyleSheet(f"color: {pal.text_primary}; font-size: 12px;")
            row.addWidget(text, 1)

            date_lbl = QLabel(rec.get("date", "")[:10])
            date_lbl.setStyleSheet(f"color: {pal.text_tertiary}; font-size: 11px;")
            row.addWidget(date_lbl)

            layout.addLayout(row)

        return layout
