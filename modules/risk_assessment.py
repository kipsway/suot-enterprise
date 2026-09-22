from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QRect, QSize
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QFrame,
)

from app_core.i18n import I18n
from app_core.design_tokens import palette
from app_core.theme_engine import ThemeEngine
from app_core.utils import wrap_table_with_glow
from services.database import DatabaseManager
from widgets.glass_button import GlassButton
from widgets.glass_line_edit import GlassLineEdit
from widgets.glass_combo_box import GlassComboBox


RISK_MATRIX = [
    # consequence 1-5, probability 1-5 → risk_level
    # Level: 1-3 low, 4-6 medium, 7-12 high, 13-25 critical
    [1, 2, 3, 4, 5],
    [2, 4, 6, 8, 10],
    [3, 6, 9, 12, 15],
    [4, 8, 12, 16, 20],
    [5, 10, 15, 20, 25],
]

RISK_COLORS = {
    "low": "#34C759",
    "medium": "#FF9500",
    "high": "#FF3B30",
    "critical": "#FF2D55",
}

MATRIX_CELL_COLORS = [
    ["#34C759", "#34C759", "#FF9500", "#FF9500", "#FF3B30"],
    ["#34C759", "#FF9500", "#FF9500", "#FF3B30", "#FF3B30"],
    ["#FF9500", "#FF9500", "#FF3B30", "#FF3B30", "#FF2D55"],
    ["#FF9500", "#FF3B30", "#FF3B30", "#FF2D55", "#FF2D55"],
    ["#FF3B30", "#FF3B30", "#FF2D55", "#FF2D55", "#FF2D55"],
]


def calc_risk_level(prob: int, cons: int) -> int:
    if prob < 1 or prob > 5 or cons < 1 or cons > 5:
        return 1
    return RISK_MATRIX[prob - 1][cons - 1]


def risk_category(level: int) -> str:
    if level <= 3:
        return "low"
    if level <= 6:
        return "medium"
    if level <= 12:
        return "high"
    return "critical"


class RiskMatrixWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._highlight_prob = -1
        self._highlight_cons = -1
        self.setFixedSize(320, 320)

    def set_highlight(self, prob: int, cons: int) -> None:
        self._highlight_prob = prob
        self._highlight_cons = cons
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = ThemeEngine._current_theme == "dark"
        pal = palette(dark)

        cell_w = 50
        cell_h = 50
        offset_x = 50
        offset_y = 50
        margin = 2

        # Header
        f = self.font()
        f.setPointSize(8)
        p.setFont(f)

        for i in range(5):
            p.setPen(QColor(pal.text_secondary))
            p.drawText(
                QRect(offset_x + i * cell_w, 0, cell_w, offset_y),
                Qt.AlignCenter,
                str(i + 1),
            )
            p.drawText(
                QRect(0, offset_y + i * cell_h, offset_x, cell_h),
                Qt.AlignCenter,
                str(i + 1),
            )

        p.setPen(QColor(pal.text_tertiary))
        p.drawText(QRect(0, 0, offset_x, 20), Qt.AlignCenter, "P\\C")
        p.drawText(QRect(offset_x, 0, 200, 16), Qt.AlignCenter, "Последствия")
        p.drawText(QRect(0, offset_y, 16, 200), Qt.AlignCenter, "В")

        for row in range(5):
            for col in range(5):
                x = offset_x + col * cell_w + margin
                y = offset_y + row * cell_h + margin
                w = cell_w - margin * 2
                h = cell_h - margin * 2

                is_hl = (
                    row + 1 == self._highlight_prob and col + 1 == self._highlight_cons
                )
                color = QColor(MATRIX_CELL_COLORS[row][col])
                if is_hl:
                    color = color.lighter(130)

                path = QPainterPath()
                path.addRoundedRect(x, y, w, h, 4, 4)
                p.fillPath(path, color)
                p.setPen(QPen(QColor(255, 255, 255, 80), 0.5))
                p.drawPath(path)

                val = RISK_MATRIX[row][col]
                p.setPen(Qt.white)
                pf = self.font()
                pf.setPointSize(10)
                pf.setBold(True)
                p.setFont(pf)
                p.drawText(
                    QRect(int(x), int(y), int(w), int(h)), Qt.AlignCenter, str(val)
                )

        p.end()


class RiskEditDialog(QDialog):
    def __init__(
        self, record: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._record = record or {}
        self.setWindowTitle("Оценка риска")
        self.setMinimumSize(600, 450)
        self._build_ui()
        if record:
            self._load_data()
        self._update_matrix()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)

        left = QVBoxLayout()
        form = QFormLayout()
        form.setSpacing(6)

        self._title_edit = GlassLineEdit()
        self._title_edit.setPlaceholderText("Название риска")
        self._title_edit.setMinimumHeight(32)
        form.addRow("Риск:", self._title_edit)
        left.addLayout(form)

        desc_form = QFormLayout()
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Описание")
        self._desc_edit.setMaximumHeight(60)
        desc_form.addRow("Описание:", self._desc_edit)
        left.addLayout(desc_form)

        cat_form = QFormLayout()
        self._category_combo = GlassComboBox()
        self._category_combo.setMinimumHeight(32)
        self._category_combo.addItems(
            [
                "производственный",
                "пожарный",
                "экологический",
                "санитарный",
                "электрический",
                "механический",
                "химический",
                "эргономический",
                "общий",
            ]
        )
        cat_form.addRow("Категория:", self._category_combo)
        left.addLayout(cat_form)

        prob_form = QFormLayout()
        self._prob_spin = QSpinBox()
        self._prob_spin.setRange(1, 5)
        self._prob_spin.setValue(2)
        self._prob_spin.valueChanged.connect(self._update_matrix)
        prob_form.addRow("Вероятность (1-5):", self._prob_spin)
        left.addLayout(prob_form)

        cons_form = QFormLayout()
        self._cons_spin = QSpinBox()
        self._cons_spin.setRange(1, 5)
        self._cons_spin.setValue(2)
        self._cons_spin.valueChanged.connect(self._update_matrix)
        cons_form.addRow("Последствия (1-5):", self._cons_spin)
        left.addLayout(cons_form)

        self._level_label = QLabel("Уровень риска: 4 (medium)")
        self._level_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        left.addWidget(self._level_label)

        mit_form = QFormLayout()
        self._mitigation_edit = QTextEdit()
        self._mitigation_edit.setPlaceholderText("Меры по снижению риска")
        self._mitigation_edit.setMaximumHeight(80)
        mit_form.addRow("Меры:", self._mitigation_edit)
        left.addLayout(mit_form)

        self._status_combo = GlassComboBox()
        self._status_combo.addItems(["active", "mitigated", "closed"])
        self._status_combo.setMinimumHeight(32)
        mit_form.addRow("Статус:", self._status_combo)

        left.addSpacing(12)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        left.addWidget(btns)

        layout.addLayout(left, 1)

        self._matrix = RiskMatrixWidget()
        layout.addWidget(self._matrix)

    def _load_data(self) -> None:
        r = self._record
        self._title_edit.setText(r.get("title", ""))
        self._desc_edit.setPlainText(r.get("description", ""))
        cidx = self._category_combo.findText(r.get("category", "общий"))
        if cidx >= 0:
            self._category_combo.setCurrentIndex(cidx)
        self._prob_spin.setValue(int(r.get("probability", 2)))
        self._cons_spin.setValue(int(r.get("consequence", 2)))
        self._mitigation_edit.setPlainText(r.get("mitigation", ""))
        sidx = self._status_combo.findText(r.get("status", "active"))
        if sidx >= 0:
            self._status_combo.setCurrentIndex(sidx)

    def _update_matrix(self) -> None:
        prob = self._prob_spin.value()
        cons = self._cons_spin.value()
        level = calc_risk_level(prob, cons)
        cat = risk_category(level)
        self._level_label.setText(f"Уровень риска: {level} ({cat})")
        color = RISK_COLORS.get(cat, "#888")
        self._level_label.setStyleSheet(
            f"font-weight: bold; font-size: 14px; color: {color};"
        )
        self._matrix.set_highlight(prob, cons)

    def _save(self) -> None:
        prob = self._prob_spin.value()
        cons = self._cons_spin.value()
        level = calc_risk_level(prob, cons)
        self._data = {
            "title": self._title_edit.text().strip(),
            "description": self._desc_edit.toPlainText().strip(),
            "category": self._category_combo.currentText(),
            "probability": str(prob),
            "consequence": str(cons),
            "risk_level": str(level),
            "mitigation": self._mitigation_edit.toPlainText().strip(),
            "status": self._status_combo.currentText(),
        }
        self.accept()

    def result_data(self) -> Dict[str, str]:
        return getattr(self, "_data", {})


class RiskAssessmentTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = DatabaseManager()
        self._records: List[Dict[str, Any]] = []
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        toolbar = QHBoxLayout()
        add_btn = GlassButton("➕ " + I18n._("common.add"))
        add_btn.clicked.connect(self._add)
        toolbar.addWidget(add_btn)

        edit_btn = GlassButton("✏️ " + I18n._("common.edit"))
        edit_btn.clicked.connect(self._edit_selected)
        toolbar.addWidget(edit_btn)

        del_btn = GlassButton("🗑 " + I18n._("common.delete"))
        del_btn.clicked.connect(self._delete_selected)
        toolbar.addWidget(del_btn)

        refresh_btn = GlassButton("🔄")
        refresh_btn.setFixedSize(32, 32)
        refresh_btn.setProperty("flat", True)
        refresh_btn.clicked.connect(self._load)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        mid = QHBoxLayout()

        self._matrix_widget = RiskMatrixWidget()
        mid.addWidget(self._matrix_widget)

        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setFixedWidth(200)
        mid.addWidget(self._summary)
        layout.addLayout(mid)

        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            ["ID", "Риск", "Категория", "Вер.", "Посл.", "Уровень", "Статус", "Дата"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(True)
        self._table.doubleClicked.connect(self._edit_selected)
        layout.addWidget(wrap_table_with_glow(self._table, self), 1)

    def _load(self) -> None:
        try:
            self._records = self.db.fetch_all(
                "SELECT * FROM risk_assessments ORDER BY risk_level DESC"
            )
        except Exception:
            self._records = []
        self._table.setRowCount(0)
        level_counts: Dict[str, int] = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for r in self._records:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(r["id"])))
            self._table.setItem(row, 1, QTableWidgetItem(r.get("title", "")[:50]))
            self._table.setItem(row, 2, QTableWidgetItem(r.get("category", "")))
            self._table.setItem(row, 3, QTableWidgetItem(str(r.get("probability", 1))))
            self._table.setItem(row, 4, QTableWidgetItem(str(r.get("consequence", 1))))
            lvl = int(r.get("risk_level", 1))
            cat = risk_category(lvl)
            level_counts[cat] = level_counts.get(cat, 0) + 1
            lvl_item = QTableWidgetItem(str(lvl))
            lvl_item.setForeground(QColor(RISK_COLORS.get(cat, "#888")))
            self._table.setItem(row, 5, lvl_item)
            st = r.get("status", "active")
            st_item = QTableWidgetItem(st)
            st_item.setForeground(
                QColor(
                    "#34C759"
                    if st == "closed"
                    else "#FF9500"
                    if st == "mitigated"
                    else "#FF3B30"
                )
            )
            self._table.setItem(row, 6, st_item)
            self._table.setItem(row, 7, QTableWidgetItem(r.get("created_at", "")[:10]))
        self._table.resizeColumnsToContents()

        total = len(self._records)
        summary_text = (
            f"<b>Сводка рисков:</b><br>"
            f"Всего: {total}<br>"
            f"🟢 Низких: {level_counts.get('low', 0)}<br>"
            f"🟠 Средних: {level_counts.get('medium', 0)}<br>"
            f"🔴 Высоких: {level_counts.get('high', 0)}<br>"
            f"💥 Критических: {level_counts.get('critical', 0)}"
        )
        self._summary.setText(summary_text)

    def _add(self) -> None:
        dlg = RiskEditDialog(None, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.result_data()
            try:
                self.db.execute(
                    "INSERT INTO risk_assessments (title, description, category, "
                    "probability, consequence, risk_level, mitigation, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        data["title"],
                        data["description"],
                        data["category"],
                        data["probability"],
                        data["consequence"],
                        data["risk_level"],
                        data["mitigation"],
                        data["status"],
                    ),
                )
                self.db.conn.commit()
                self._load()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _edit_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        dlg = RiskEditDialog(self._records[row], self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.result_data()
            rid = self._records[row]["id"]
            try:
                self.db.execute(
                    "UPDATE risk_assessments SET title=?, description=?, category=?, "
                    "probability=?, consequence=?, risk_level=?, mitigation=?, status=? WHERE id=?",
                    (
                        data["title"],
                        data["description"],
                        data["category"],
                        data["probability"],
                        data["consequence"],
                        data["risk_level"],
                        data["mitigation"],
                        data["status"],
                        rid,
                    ),
                )
                self.db.conn.commit()
                self._load()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _delete_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        reply = QMessageBox.question(
            self,
            I18n._("common.confirm"),
            I18n._("common.delete") + "?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            rid = self._records[row]["id"]
            try:
                self.db.execute("DELETE FROM risk_assessments WHERE id=?", (rid,))
                self.db.conn.commit()
                self._load()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
