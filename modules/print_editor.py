import json, os, re, base64, mimetypes
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Callable
from PyQt5.QtCore import Qt, QTimer, QEvent, QPoint, QObject, QSizeF, QSettings, QRegExp
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QKeySequence,
    QPainter,
    QPen,
    QTextCharFormat,
    QTextFormat,
    QTextListFormat,
    QSyntaxHighlighter,
    QTextDocument,
    QTextCursor,
    QPixmap,
    QTransform,
    QTextLength,
    QTextTable,
    QTextFrame,
    QTextBlockFormat,
    QIcon,
    QDesktopServices,
)
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QSlider,
    QScrollArea,
    QTextEdit,
    QToolButton,
    QFontComboBox,
    QColorDialog,
    QInputDialog,
    QMessageBox,
    QFileDialog,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QSizePolicy,
    QShortcut,
    QDialogButtonBox,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QTextBrowser,
    QPlainTextEdit,
    QGridLayout,
)
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
from widgets.glass_button import GlassButton
from widgets.glass_checkbox import GlassCheckBox
from widgets.glass_line_edit import GlassLineEdit
from widgets.glass_combo_box import GlassComboBox

from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from services.database import DatabaseManager
from widgets.ribbon import RibbonWidget
from modules.reminders import ReminderEngine
from widgets.toast import ToastNotification
from modules.print_engine import PrintEngine


class _ViewResizeFilter(QObject):
    def __init__(self, view: QGraphicsView, callback: Callable[[], None]) -> None:
        super().__init__(view)
        self._callback = callback

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Resize:
            try:
                if isinstance(obj.parent(), QGraphicsView):
                    self._callback()
            except RuntimeError:
                pass
        return super().eventFilter(obj, event)


class FieldHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._rule = QRegExp(r"\{[^{}]+\}")
        self._fmt = QTextCharFormat()
        self._fmt.setForeground(QColor("#4B7BFF"))
        self._fmt.setFontWeight(QFont.Bold)

    def highlightBlock(self, text: str) -> None:
        idx = self._rule.indexIn(text)
        while idx >= 0:
            length = self._rule.matchedLength()
            self.setFormat(idx, length, self._fmt)
            idx = self._rule.indexIn(text, idx + length)


class RulerWidget(QWidget):
    def __init__(self, editor: QTextEdit) -> None:
        super().__init__(editor.parent())
        self._editor = editor
        self.setFixedHeight(22)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

    def update_position(self) -> None:
        eg = self._editor.geometry()
        self.setGeometry(eg.x(), eg.y() - self.height(), eg.width(), self.height())
        self.show()
        self.update()

    def paintEvent(self, event: Any) -> None:
        if self.width() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#F0F2F5"))
        painter.setPen(QPen(QColor("#C0C4CC"), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        step = max(30, self.width() // 20)
        painter.setPen(QPen(QColor("#8E8E93"), 1))
        font = QFont("Segoe UI", 6)
        painter.setFont(font)
        for x in range(step, self.width(), step):
            painter.drawLine(x, self.height() - 8, x, self.height() - 1)
            if x % (step * 2) == 0 and step >= 25:
                painter.drawText(x - 6, 8, f"{x}")
        painter.setPen(QPen(QColor("#4B7BFF"), 2))
        painter.drawLine(0, 0, 0, self.height())
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())


class PageGuideWidget(QWidget):
    def __init__(self, editor: QTextEdit, owner: "PrintTemplateEditor") -> None:
        super().__init__(editor.parent())
        self._editor = editor
        self._owner = owner
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

    def paintEvent(self, event: Any) -> None:
        if not self._editor.isVisible() or self.width() <= 0 or self.height() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#D6DAE1"))
        pen.setWidth(1)
        painter.setPen(pen)
        fm = QFont("Segoe UI", 8)
        painter.setFont(fm)
        try:
            page_count = max(1, self._editor.document().pageCount())
        except Exception:
            page_count = 1
        pw, ph = self._owner._orientations.get(self._owner._orientation, (794, 1123))
        scale = max(0.05, self._owner._editor.width() / float(pw)) if pw else 1.0
        page_h = max(1, int(ph * scale))
        for page in range(1, page_count):
            y = page * page_h - self._owner._editor.verticalScrollBar().value()
            if y < -50 or y > self.height() + 50:
                continue
            for i in range(4):
                alpha = max(0, 20 - i * 5)
                painter.setPen(QPen(QColor(0, 0, 0, alpha)))
                painter.drawLine(
                    20 + i, y + 1 + i, max(20, self.width() - 20 - i), y + 1 + i
                )
            painter.setPen(pen)
            painter.drawLine(18, y, max(18, self.width() - 18), y)
            painter.setPen(QColor("#8E8E93"))
            painter.drawText(24, y - 6, f"A4 \u2022 {page + 1}")
            painter.setPen(pen)


class PrintTemplateEditor(QDialog):
    ORDER_FIELDS = [
        ("id", "ID"),
        ("date", I18n._("common.date")),
        ("company", I18n._("emp.company")),
        ("responsible", I18n._("viol.responsible")),
        ("deadline", I18n._("viol.deadline")),
        ("description", I18n._("viol.description")),
        ("recommended_action", "Рекомендации"),
        ("fine", I18n._("viol.fine")),
        ("photos_section", I18n._("emp.photo")),
        ("app_name", I18n._("app.name")),
        ("generated_at", I18n._("common.date")),
        ("record_number", I18n._("template.record_number")),
        ("violation_number", I18n._("template.violation_number")),
        ("violation_index", I18n._("template.violation_index")),
        ("page_number", I18n._("template.insert_page_number")),
    ]
    REPORT_FIELDS = [
        ("company_name", I18n._("company.name")),
        ("date", I18n._("common.date")),
        ("emp_count", I18n._("company.employees_count")),
        ("viol_count", I18n._("company.violations_count")),
        ("fines_total", I18n._("company.fines_total")),
        ("overdue_count", I18n._("stat.overdue_total")),
        ("table_html", "HTML " + I18n._("common.table")),
        ("app_name", I18n._("app.name")),
        ("generated_at", I18n._("common.date")),
    ]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.db = DatabaseManager()
        self.setWindowTitle(I18n._("template.edit"))
        screen = QApplication.primaryScreen().availableGeometry()
        sw, sh = screen.width(), screen.height()
        w = min(1650, sw - 40)
        h = min(900, sh - 80)
        self.setMinimumSize(1200, 600)
        self.resize(w, h)
        self.move(max(0, (sw - w) // 2), max(0, (sh - h) // 2))
        self._current_id: int = 0
        self._saved: bool = True
        self.selected_id: Optional[int] = None
        self._page_width: int = 794
        self._page_height: int = 1123
        self._page_margin_left: int = 60
        self._page_margin_right: int = 60
        self._page_margin_top: int = 50
        self._page_margin_bottom: int = 50
        self._zoom_level: int = 100
        self._show_page_shadow: bool = True
        self._orientations: Dict[str, Tuple[int, int]] = {
            "portrait": (794, 1123),
            "landscape": (1123, 794),
        }
        self._orientation: str = "portrait"
        settings = QSettings("SUOT", "PrintTemplate")
        self._page_margin_left = int(
            settings.value("page_margin_left", self._page_margin_left)
        )
        self._page_margin_right = int(
            settings.value("page_margin_right", self._page_margin_right)
        )
        self._page_margin_top = int(
            settings.value("page_margin_top", self._page_margin_top)
        )
        self._page_margin_bottom = int(
            settings.value("page_margin_bottom", self._page_margin_bottom)
        )
        self._show_page_shadow = str(settings.value("page_shadow", "true")).lower() in (
            "1",
            "true",
            "yes",
        )
        self._orientation = settings.value("page_orientation", self._orientation)
        self._build_ui()
        self._load_templates()
        self._apply_page_margins()
        QTimer.singleShot(200, self._fit_page)
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(self._auto_save)
        self._auto_save_timer.start(300000)

    def closeEvent(self, event: Any) -> None:
        if not self._saved:
            result = QMessageBox.question(
                self,
                I18n._("template.edit"),
                I18n._("common.confirm_close"),
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if result == QMessageBox.Save:
                self._save_template()
                event.accept()
            elif result == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def handle_ribbon_action(self, action: str) -> None:
        editor = getattr(self, "_editor", None)
        if not editor:
            return
        c = editor.textCursor()
        if action == "bold":
            editor.setFontWeight(
                QFont.Bold if editor.fontWeight() != QFont.Bold else QFont.Normal
            )
        elif action == "italic":
            editor.setFontItalic(not editor.fontItalic())
        elif action == "underline":
            editor.setFontUnderline(not editor.fontUnderline())
        elif action.startswith("align_"):
            flags = {
                "left": Qt.AlignLeft,
                "center": Qt.AlignHCenter,
                "right": Qt.AlignRight,
                "justify": Qt.AlignJustify,
            }
            al = flags.get(action[6:], Qt.AlignLeft)
            fmt = c.blockFormat()
            fmt.setAlignment(al)
            c.setBlockFormat(fmt)
            editor.setTextCursor(c)
        elif action == "zoom_in":
            self._zoom(10)
        elif action == "zoom_out":
            self._zoom(-10)
        elif action == "zoom_reset":
            self._zoom_level = 100
            self._apply_zoom()
        elif action == "insert_image":
            self._insert_image()
        elif action == "insert_link":
            self._insert_link()
        elif action == "insert_table":
            self._insert_table()

    def _build_ui(self) -> None:
        is_dark_tmpl = ThemeEngine._current_theme == "dark"
        self.setStyleSheet(
            f"PrintTemplateEditor {{ background: {'#1C1C1E' if is_dark_tmpl else '#F5F5F7'}; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(3)

        self._ribbon = RibbonWidget(self)
        layout.addWidget(self._ribbon)

        _rh = 26

        def _sep() -> QFrame:
            s = QFrame()
            s.setFrameShape(QFrame.VLine)
            s.setStyleSheet("color:#D0D4DC;")
            return s

        def _tb(emoji, tip, cb, w=30) -> QToolButton:
            b = QToolButton()
            b.setText(emoji)
            b.setToolTip(tip)
            b.setFixedSize(w, _rh)
            b.clicked.connect(cb)
            return b

        def _make_btn(text: str, cb, w=70) -> QPushButton:
            b = GlassButton(text)
            b.setFixedHeight(_rh)
            b.setMinimumWidth(w)
            b.clicked.connect(cb)
            return b

        # ═══ Ряд 1: Тип + Шаблон + Имя + Файл ══════════════════════════
        row1 = QHBoxLayout()
        row1.setSpacing(3)
        row1.addWidget(QLabel(I18n._("print.template") + ":"))
        self._type_combo = GlassComboBox()
        self._type_combo.addItem(I18n._("print.order"), "order")
        self._type_combo.addItem(I18n._("print.report"), "report")
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._type_combo.setMinimumWidth(90)
        self._type_combo.setFixedHeight(_rh)
        row1.addWidget(self._type_combo)
        self._template_combo = GlassComboBox()
        self._template_combo.setMinimumWidth(160)
        self._template_combo.setFixedHeight(_rh)
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        row1.addWidget(self._template_combo)
        self._template_name_edit = GlassLineEdit()
        self._template_name_edit.setPlaceholderText(I18n._("template.name"))
        self._template_name_edit.setMinimumWidth(140)
        self._template_name_edit.setFixedHeight(_rh)
        row1.addWidget(self._template_name_edit)
        self._template_search = GlassLineEdit()
        self._template_search.setPlaceholderText("🔍" + I18n._("common.find"))
        self._template_search.setFixedHeight(_rh)
        self._template_search.setMaximumWidth(100)
        self._template_search.textChanged.connect(self._filter_templates)
        row1.addWidget(self._template_search)
        row1.addWidget(_sep())
        row1.addWidget(_tb("➕", I18n._("common.add"), self._new_template))
        row1.addWidget(_tb("💾", I18n._("common.save"), self._save_template))
        row1.addWidget(
            _tb("📋", I18n._("template.duplicate"), self._duplicate_template)
        )
        row1.addWidget(_tb("✏️", I18n._("common.rename"), self._rename_template))
        row1.addWidget(_tb("🗑️", I18n._("common.delete"), self._delete_template))
        row1.addWidget(_tb("✅", I18n._("template.select"), self._select_and_close))
        row1.addWidget(_tb("📂", "Импорт", self._import_template))
        row1.addWidget(_tb("📤", "Экспорт", self._export_template))
        row1.addStretch()
        layout.addLayout(row1)

        # ═══ Ряд 2: Страница + Масштаб ══════════════════════════════════
        row2 = QHBoxLayout()
        row2.setSpacing(3)
        row2.addWidget(QLabel("📄" + I18n._("template.page_settings") + ":"))
        row2.addWidget(_sep())
        # margin spins with compact labels
        for attr, label, rmin, rmax in [
            ("_margin_left_spin", "←", 10, 160),
            ("_margin_right_spin", "→", 10, 160),
            ("_margin_top_spin", "↑", 10, 180),
            ("_margin_bottom_spin", "↓", 10, 180),
        ]:
            row2.addWidget(QLabel(label))
            spin = QSpinBox()
            spin.setRange(rmin, rmax)
            spin.setFixedWidth(54)
            spin.setFixedHeight(_rh)
            spin.setSuffix("")
            setattr(self, attr, spin)
            row2.addWidget(spin)
        self._margin_left_spin.setValue(self._page_margin_left)
        self._margin_right_spin.setValue(self._page_margin_right)
        self._margin_top_spin.setValue(self._page_margin_top)
        self._margin_bottom_spin.setValue(self._page_margin_bottom)
        row2.addWidget(_sep())
        row2.addWidget(QLabel(I18n._("template.margin_preset") + ":"))
        self._margin_preset_combo = GlassComboBox()
        self._margin_preset_combo.addItem(I18n._("template.margin_normal"), "normal")
        self._margin_preset_combo.addItem(I18n._("template.margin_narrow"), "narrow")
        self._margin_preset_combo.addItem(I18n._("template.margin_wide"), "wide")
        self._margin_preset_combo.setMinimumWidth(70)
        self._margin_preset_combo.setFixedHeight(_rh)
        row2.addWidget(self._margin_preset_combo)
        self._page_shadow_cb = GlassCheckBox(I18n._("template.page_shadow"))
        self._page_shadow_cb.setChecked(self._show_page_shadow)
        self._page_shadow_cb.setFixedHeight(_rh)
        row2.addWidget(self._page_shadow_cb)
        row2.addWidget(_sep())
        row2.addWidget(QLabel(I18n._("print.orientation") + ":"))
        self._orientation_combo = GlassComboBox()
        self._orientation_combo.addItem(I18n._("print.portrait"), "portrait")
        self._orientation_combo.addItem(I18n._("print.landscape"), "landscape")
        self._orientation_combo.setMinimumWidth(70)
        self._orientation_combo.setFixedHeight(_rh)
        self._orientation_combo.currentIndexChanged.connect(
            self._on_orientation_changed
        )
        row2.addWidget(self._orientation_combo)
        saved_orientation_idx = self._orientation_combo.findData(self._orientation)
        if saved_orientation_idx >= 0:
            self._orientation_combo.setCurrentIndex(saved_orientation_idx)
        row2.addWidget(_sep())
        self._zoom_slider = QSlider(Qt.Horizontal)
        self._zoom_slider.setRange(10, 400)
        self._zoom_slider.setValue(self._zoom_level)
        self._zoom_slider.setFixedWidth(100)
        self._zoom_slider.setFixedHeight(18)
        self._zoom_slider.setToolTip(I18n._("common.zoom"))
        self._zoom_slider.valueChanged.connect(self._apply_zoom_slider)
        row2.addWidget(self._zoom_slider)
        self._zoom_label = GlassButton()
        self._zoom_label.setFixedSize(46, _rh)
        self._zoom_label.setStyleSheet("font-weight:bold; font-size:10px; padding:0;")
        self._zoom_label.setToolTip(I18n._("common.reset_zoom"))
        self._zoom_label.clicked.connect(self._reset_zoom)
        row2.addWidget(self._zoom_label)
        row2.addStretch()
        layout.addLayout(row2)

        # ═══ Ряд 3: Формат ══════════════════════════════════════════════
        row3 = QHBoxLayout()
        row3.setSpacing(3)
        row3.addWidget(QLabel("🎨" + I18n._("common.format") + ":"))
        row3.addWidget(_sep())
        self._heading_combo = GlassComboBox()
        self._heading_combo.addItem(I18n._("common.paragraph"), "p")
        self._heading_combo.addItem(I18n._("template.heading1"), "h1")
        self._heading_combo.addItem(I18n._("template.heading2"), "h2")
        self._heading_combo.addItem(I18n._("template.heading3"), "h3")
        self._heading_combo.setMinimumWidth(95)
        self._heading_combo.setFixedHeight(_rh)
        self._heading_combo.currentIndexChanged.connect(self._on_heading_changed)
        row3.addWidget(self._heading_combo)
        row3.addWidget(QLabel(I18n._("common.size") + ":"))
        self._size_combo = GlassComboBox()
        self._size_combo.setEditable(True)
        self._size_combo.setMinimumWidth(48)
        self._size_combo.setFixedHeight(_rh)
        for s in (
            "8",
            "9",
            "10",
            "11",
            "12",
            "14",
            "16",
            "18",
            "20",
            "22",
            "24",
            "28",
            "32",
            "36",
            "40",
            "48",
            "56",
            "64",
            "72",
        ):
            self._size_combo.addItem(s)
        self._size_combo.setCurrentText("12")
        self._size_combo.currentTextChanged.connect(self._on_size_changed)
        row3.addWidget(self._size_combo)
        row3.addWidget(_tb("🧹", I18n._("common.clear"), self._clear_formatting))
        row3.addWidget(_sep())
        for txt, tip, attr, cb in [
            ("B", "Жирный (Ctrl+B)", "_bold_btn", self._toggle_bold),
            ("I", "Курсив (Ctrl+I)", "_italic_btn", self._toggle_italic),
            ("U", "Подчёркнутый (Ctrl+U)", "_underline_btn", self._toggle_underline),
            ("S", "Зачёркнутый", "_strike_btn", self._toggle_strikethrough),
        ]:
            b = QToolButton()
            b.setText(txt)
            b.setCheckable(True)
            b.setFixedSize(28, _rh)
            b.setToolTip(tip)
            b.clicked.connect(cb)
            if txt == "B":
                b.setFont(QFont("Segoe UI", 9, QFont.Bold))
            elif txt == "I":
                b.setFont(QFont("", -1, -1, True))
            elif txt == "U":
                f = QFont("", -1, -1)
                f.setUnderline(True)
                b.setFont(f)
            elif txt == "S":
                f = QFont("", -1, -1)
                f.setStrikeOut(True)
                b.setFont(f)
            setattr(self, attr, b)
            row3.addWidget(b)
        row3.addWidget(_sep())
        self._font_combo = QFontComboBox()
        self._font_combo.setMinimumWidth(110)
        self._font_combo.setFixedHeight(_rh)
        self._font_combo.setFontFilters(QFontComboBox.AllFonts)
        self._font_combo.currentFontChanged.connect(self._on_font_changed)
        row3.addWidget(self._font_combo)
        self._color_btn = QToolButton()
        self._color_btn.setText("A")
        self._color_btn.setFixedSize(28, _rh)
        self._color_btn.setStyleSheet("color:#1a365d; font-weight:bold;")
        self._color_btn.setToolTip(I18n._("common.format"))
        self._color_btn.clicked.connect(self._pick_color)
        row3.addWidget(self._color_btn)
        row3.addWidget(_sep())
        for txt, tip, attr, align in [
            ("≡L", I18n._("common.align_left"), "_align_left_btn", Qt.AlignLeft),
            ("≡C", I18n._("common.align_center"), "_align_center_btn", Qt.AlignCenter),
            ("≡R", I18n._("common.align_right"), "_align_right_btn", Qt.AlignRight),
        ]:
            b = QToolButton()
            b.setText(txt)
            b.setCheckable(True)
            b.setFixedSize(28, _rh)
            b.setToolTip(tip)
            b.clicked.connect(lambda a=align: self._set_alignment(a))
            setattr(self, attr, b)
            row3.addWidget(b)
        row3.addWidget(_sep())
        self._bullet_btn = QToolButton()
        self._bullet_btn.setText("•")
        self._bullet_btn.setCheckable(True)
        self._bullet_btn.setFixedSize(28, _rh)
        self._bullet_btn.setToolTip("Список")
        self._bullet_btn.clicked.connect(self._toggle_bullet)
        row3.addWidget(self._bullet_btn)
        self._number_btn = QToolButton()
        self._number_btn.setText("1.")
        self._number_btn.setCheckable(True)
        self._number_btn.setFixedSize(28, _rh)
        self._number_btn.setToolTip("Нумерация")
        self._number_btn.clicked.connect(self._toggle_number)
        row3.addWidget(self._number_btn)
        row3.addWidget(_sep())
        row3.addWidget(_tb("↔→", "Увеличить отступ", self._indent))
        row3.addWidget(_tb("←↔", "Уменьшить отступ", self._unindent))
        row3.addWidget(_sep())
        row3.addWidget(
            _tb(
                "↩",
                I18n._("common.undo") + " (Ctrl+Z)",
                lambda: self._editor.undo() if hasattr(self, "_editor") else None,
                28,
            )
        )
        row3.addWidget(
            _tb(
                "↪",
                I18n._("common.redo") + " (Ctrl+Y)",
                lambda: self._editor.redo() if hasattr(self, "_editor") else None,
                28,
            )
        )
        row3.addWidget(_sep())
        row3.addWidget(_tb("Aa↓", "нижний регистр", self._case_lower))
        row3.addWidget(_tb("Aa↑", "ВЕРХНИЙ РЕГИСТР", self._case_upper))
        row3.addWidget(_tb("Aa⇔", "Заглавные", self._case_title))
        row3.addWidget(_tb("Ω", "Спецсимволы", self._special_chars))
        row3.addWidget(_sep())
        self._quick_style_combo = GlassComboBox()
        self._quick_style_combo.setFixedHeight(_rh)
        self._quick_style_combo.setMinimumWidth(110)
        self._quick_style_combo.addItem("🎨 Стиль...", "")
        self._quick_style_combo.addItem("📋 Цитата", "quote")
        self._quick_style_combo.addItem("⚠️ Предупреждение", "alert")
        self._quick_style_combo.addItem("💻 Код", "code")
        self._quick_style_combo.activated.connect(self._apply_quick_style)
        row3.addWidget(self._quick_style_combo)
        row3.addWidget(_sep())
        row3.addWidget(QLabel("Инт:"))
        self._line_spacing_spin = QDoubleSpinBox()
        self._line_spacing_spin.setRange(0.5, 3.0)
        self._line_spacing_spin.setSingleStep(0.1)
        self._line_spacing_spin.setValue(1.0)
        self._line_spacing_spin.setFixedWidth(50)
        self._line_spacing_spin.setFixedHeight(_rh)
        self._line_spacing_spin.valueChanged.connect(self._apply_line_spacing)
        row3.addWidget(self._line_spacing_spin)
        row3.addWidget(_sep())
        row3.addWidget(_tb("◁", "По левому краю", self._align_left, 26))
        row3.addWidget(_tb("≡", "По центру", self._align_center, 26))
        row3.addWidget(_tb("▷", "По правому краю", self._align_right, 26))
        row3.addWidget(_tb("⊞", "По ширине", self._align_justify, 26))
        row3.addWidget(_sep())
        row3.addWidget(
            _tb("📊", I18n._("stat.document_stats"), self._document_stats, 30)
        )
        row3.addWidget(_sep())
        row3.addWidget(_tb("📋", "Вставить без форматирования", self._paste_plain, 30))
        row3.addStretch()
        layout.addLayout(row3)

        # ═══ Ряд 4: Вставка + Поля ══════════════════════════════════════
        row4 = QHBoxLayout()
        row4.setSpacing(3)
        row4.addWidget(QLabel("📦" + I18n._("template.insert_table") + ":"))
        row4.addWidget(_sep())
        row4.addWidget(
            _tb("📊", I18n._("template.insert_table"), self._insert_table, 32)
        )
        row4.addWidget(
            _tb("📝", I18n._("template.insert_header"), self._insert_header_block, 32)
        )
        row4.addWidget(
            _tb(
                "✍️",
                I18n._("template.insert_signature"),
                self._insert_signature_block,
                32,
            )
        )
        row4.addWidget(
            _tb("🔧", I18n._("template.auto_format"), self._auto_format_document, 32)
        )
        row4.addWidget(_tb("↔", I18n._("template.fit_width"), self._fit_width, 32))
        row4.addWidget(_tb("🖼", "Вставить картинку", self._insert_image, 32))
        row4.addWidget(_sep())
        self._field_search = GlassLineEdit()
        self._field_search.setPlaceholderText("🔍" + I18n._("common.search") + "...")
        self._field_search.setMinimumHeight(_rh)
        self._field_search.setMaximumWidth(100)
        self._field_search.textChanged.connect(self._filter_field_tree)
        row4.addWidget(self._field_search)
        self._field_combo = GlassComboBox()
        self._field_combo.setEditable(True)
        self._field_combo.setInsertPolicy(QComboBox.NoInsert)
        self._field_combo.setMinimumWidth(160)
        self._field_combo.setFixedHeight(_rh)
        self._field_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._field_combo.activated[int].connect(self._on_field_combo_selected)
        self._field_combo.lineEdit().setPlaceholderText("🔍 Поле...")
        row4.addWidget(self._field_combo)
        row4.addWidget(_sep())
        row4.addWidget(
            _tb("▶", I18n._("template.repeat_start"), self._insert_repeat_block_start)
        )
        row4.addWidget(
            _tb("■", I18n._("template.repeat_end"), self._insert_repeat_block_end)
        )
        row4.addWidget(_sep())
        self._quick_blocks_combo = GlassComboBox()
        self._quick_blocks_combo.setFixedHeight(_rh)
        self._quick_blocks_combo.setMinimumWidth(110)
        self._quick_blocks_combo.addItem(I18n._("template.block_title"), "title")
        self._quick_blocks_combo.addItem(
            I18n._("template.block_violations"), "violations"
        )
        self._quick_blocks_combo.addItem(I18n._("template.insert_header"), "header")
        self._quick_blocks_combo.addItem(
            I18n._("template.insert_signature"), "signature"
        )
        row4.addWidget(self._quick_blocks_combo)
        row4.addWidget(_tb("➕", I18n._("common.add"), self._insert_quick_block))
        row4.addWidget(_sep())
        row4.addWidget(
            _tb(
                "👁",
                I18n._("template.preview_multi"),
                lambda: self._preview_template(multi_sample=True),
            )
        )
        row4.addWidget(_tb("🎨", "Фон страницы", self._page_bg_color))
        row4.addWidget(_sep())
        row4.addWidget(QLabel("№:"))
        self._page_num_fmt = GlassComboBox()
        self._page_num_fmt.setFixedHeight(_rh)
        self._page_num_fmt.setMinimumWidth(80)
        self._page_num_fmt.addItem("{n}", "n")
        self._page_num_fmt.addItem("{n}/{total}", "n_total")
        self._page_num_fmt.addItem("Стр.{n}", "page_n")
        self._page_num_fmt.currentIndexChanged.connect(lambda: None)
        row4.addWidget(self._page_num_fmt)
        row4.addStretch()
        layout.addLayout(row4)

        # ── Скрытое дерево полей ─────────────────────────────────────
        self._field_tree = QTreeWidget()
        self._field_tree.setHeaderHidden(True)
        self._field_tree.setRootIsDecorated(True)
        self._field_tree.setIndentation(16)
        self._field_tree.itemDoubleClicked.connect(
            lambda item, _: self._insert_field(item)
        )
        self._field_tree.setVisible(False)

        # ═══ Ряд 5: Редактор ════════════════════════════════════════════
        self._editor_scroll = QScrollArea()
        self._editor_scroll.setWidgetResizable(True)
        self._editor_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._editor_scroll.setStyleSheet(
            "QScrollArea { border: none; background: #E8ECF1; }"
            "QScrollBar:vertical { width: 14px; background: #E8ECF1; margin: 0; }"
            "QScrollBar::handle:vertical { background: #B0B0B0; min-height: 24px; border-radius: 5px; margin: 2px; }"
            "QScrollBar::handle:vertical:hover { background: #909090; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }"
        )

        self._editor_container = QWidget()
        self._editor_container.setStyleSheet("background: #E8ECF1;")
        self._editor_container_layout = QVBoxLayout(self._editor_container)
        self._editor_container_layout.setContentsMargins(14, 14, 14, 14)
        self._editor_container_layout.setAlignment(Qt.AlignCenter)

        self._editor = QTextEdit()
        self._editor.setAcceptRichText(True)
        self._editor.setContextMenuPolicy(Qt.CustomContextMenu)
        self._editor.customContextMenuRequested.connect(self._editor_context_menu)
        self._editor.setMinimumWidth(400)
        self._editor.setMinimumHeight(250)
        self._editor.document().setDocumentMargin(0)
        self._editor.document().setDefaultFont(QFont("Segoe UI", 11))
        self._editor.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #2C3E50; border: 1px solid #C0C4CC; "
            "border-radius: 2px; padding: 40px 50px; font-size: 11pt; }"
        )
        self._editor.cursorPositionChanged.connect(self._update_format_buttons)
        self._editor.selectionChanged.connect(self._update_format_buttons)
        self._editor.textChanged.connect(self._update_status)
        self._editor.textChanged.connect(self._sync_editor_height)
        self._editor.textChanged.connect(lambda: setattr(self, "_saved", False))
        self._editor.verticalScrollBar().valueChanged.connect(
            lambda _: self._update_page_guide()
        )
        self._editor.textChanged.connect(self._update_word_count)
        self._field_hl = FieldHighlighter(self._editor.document())
        QShortcut(QKeySequence.Save, self, self._save_template)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_B), self, self._toggle_bold)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_I), self, self._toggle_italic)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_U), self, self._toggle_underline)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_F), self, self._find_text)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_H), self, self._find_replace)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_Plus), self, self._increase_font_size)
        QShortcut(QKeySequence(Qt.CTRL + Qt.Key_Minus), self, self._decrease_font_size)
        settings = QSettings("SUOT", "PrintTemplate")
        saved_font = settings.value("font_family", "Segoe UI")
        saved_size = int(settings.value("font_size", 11))
        if saved_font:
            self._editor.setCurrentFont(QFont(saved_font, saved_size))
            self._font_combo.setCurrentFont(QFont(saved_font, saved_size))
        self._size_combo.setCurrentText(str(saved_size))
        for spin in (
            self._margin_left_spin,
            self._margin_right_spin,
            self._margin_top_spin,
            self._margin_bottom_spin,
        ):
            spin.valueChanged.connect(self._apply_page_margins)
        self._margin_preset_combo.currentIndexChanged.connect(self._apply_margin_preset)
        self._page_shadow_cb.toggled.connect(self._apply_page_margins)
        self._template_name_edit.textChanged.connect(self._update_status)
        self._editor_container_layout.addWidget(self._editor)
        self._ruler = RulerWidget(self._editor)
        self._page_guide = PageGuideWidget(self._editor, self)
        self._page_guide.raise_()
        self._editor_scroll.setWidget(self._editor_container)
        layout.addWidget(self._editor_scroll, 1)

        # ═══ Нижняя панель ══════════════════════════════════════════════
        bottom = QHBoxLayout()
        bottom.setSpacing(3)
        _bot_h = 26
        self._reset_btn = GlassButton("🔄" + I18n._("template.reset"))
        self._reset_btn.setFixedHeight(_bot_h)
        self._reset_btn.setFixedWidth(60)
        self._reset_btn.clicked.connect(self._reset_template)
        bottom.addWidget(self._reset_btn)
        self._page_nav_label = QLabel("📄")
        self._page_nav_label.setStyleSheet("font-size:11px;")
        bottom.addWidget(self._page_nav_label)
        self._page_nav_spin = QSpinBox()
        self._page_nav_spin.setPrefix("")
        self._page_nav_spin.setMinimum(1)
        self._page_nav_spin.setMaximum(9999)
        self._page_nav_spin.setFixedWidth(80)
        self._page_nav_spin.setFixedHeight(_bot_h)
        self._page_nav_spin.valueChanged.connect(self._go_to_page)
        bottom.addWidget(self._page_nav_spin)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            "color:#8E8E93; font-size:10px; padding:0 4px;"
        )
        bottom.addWidget(self._status_label)
        self._word_count_label = QLabel("")
        self._word_count_label.setStyleSheet(
            "color:#8E8E93; font-size:10px; padding:0 4px;"
        )
        bottom.addWidget(self._word_count_label, 1)
        for emoji, tip, cb in [
            ("📏", "Линейка", self._toggle_ruler),
            ("📐", "Ед. изм.", self._toggle_ruler_units),
            ("📝", "Заметки", self._template_notes),
            ("📑", "Структура", self._document_outline),
            ("📕", "PDF", self._export_pdf),
            ("</>", "HTML код", self._show_html_source),
            ("⭐", "Избранное", self._toggle_favorite),
            ("⬅", "Первая стр.", self._go_first_page),
            ("➡", "Посл. стр.", self._go_last_page),
            ("🔍", I18n._("common.find"), self._find_text),
            ("🔎", "Найти/Заменить", self._find_replace),
            ("📅", I18n._("template.insert_date"), self._insert_date),
            ("#", I18n._("template.insert_page_number"), self._insert_page_number),
            ("🖨", I18n._("common.print"), self._quick_print),
            ("👁", I18n._("template.preview"), self._preview_template),
            ("⛶", I18n._("common.fullscreen"), self._toggle_fullscreen),
            ("❌", I18n._("common.close"), self.accept),
        ]:
            bottom.addWidget(_tb(emoji, tip, cb, 30))
        layout.addLayout(bottom)

    def _build_field_tree(self) -> None:
        self._field_tree.clear()
        self._field_combo.blockSignals(True)
        self._field_combo.clear()
        self._field_combo.addItem("— " + I18n._("common.select") + " —", "")
        template_type = self._type_combo.currentData()
        fields_group = QTreeWidgetItem([I18n._("template.variables_group")])
        f = fields_group.font(0)
        f.setBold(True)
        fields_group.setFont(0, f)
        self._field_tree.addTopLevelItem(fields_group)
        available = (
            self.ORDER_FIELDS if template_type == "order" else self.REPORT_FIELDS
        )
        for key, label in available:
            item = QTreeWidgetItem([f"{{{key}}} — {label}"])
            item.setData(0, Qt.UserRole, key)
            fields_group.addChild(item)
            self._field_combo.addItem(f"{{{key}}} — {label}", key)
        fields_group.setExpanded(True)
        for table_key, table_label in [
            ("employees", I18n._("tab.employees")),
            ("violations", I18n._("tab.violations")),
            ("custom_ledger", I18n._("tab.custom_ledger")),
        ]:
            cols = self.db.get_columns_config(table_key)
            if not cols:
                continue
            ti = QTreeWidgetItem([table_label])
            ff = ti.font(0)
            ff.setBold(True)
            ti.setFont(0, ff)
            for c in cols:
                item = QTreeWidgetItem(
                    [f"{{{{{table_key}.{c['name']}}}}} — {c['name']}"]
                )
                item.setData(0, Qt.UserRole, f"{table_key}.{c['name']}")
                ti.addChild(item)
                self._field_combo.addItem(
                    f"{{{{{table_key}.{c['name']}}}}} — {c['name']}",
                    f"{table_key}.{c['name']}",
                )
            self._field_tree.addTopLevelItem(ti)
        self._field_combo.blockSignals(False)

    def _on_field_combo_selected(self, idx: int) -> None:
        key = self._field_combo.currentData()
        if key:
            self._editor.insertPlainText("{" + key + "}")
        self._field_combo.setCurrentIndex(0)

    def _insert_field(self, item: QTreeWidgetItem) -> None:
        key = item.data(0, Qt.UserRole)
        if key:
            self._editor.insertPlainText(f"{{{key}}}")

    def _toggle_bold(self) -> None:
        self._editor.setFontWeight(
            QFont.Bold if self._bold_btn.isChecked() else QFont.Normal
        )

    def _toggle_italic(self) -> None:
        self._editor.setFontItalic(self._italic_btn.isChecked())

    def _toggle_underline(self) -> None:
        self._editor.setFontUnderline(self._underline_btn.isChecked())

    def _toggle_strikethrough(self) -> None:
        fmt = self._editor.currentCharFormat()
        fmt.setFontStrikeOut(self._strike_btn.isChecked())
        self._editor.mergeCurrentCharFormat(fmt)

    def _on_heading_changed(self, idx: int) -> None:
        tag = self._heading_combo.itemData(idx)
        cursor = self._editor.textCursor()
        fmt = cursor.blockFormat()
        if tag == "p":
            fmt.setProperty(QTextFormat.BlockTrailingHorizontalRulerWidth, -1)
            cursor.setBlockFormat(fmt)
            cfmt = self._editor.currentCharFormat()
            cfmt.setFontPointSize(11)
            self._editor.setCurrentCharFormat(cfmt)
        elif tag == "h1":
            fmt.setProperty(QTextFormat.BlockTrailingHorizontalRulerWidth, -1)
            cursor.setBlockFormat(fmt)
            cfmt = self._editor.currentCharFormat()
            cfmt.setFontPointSize(22)
            cfmt.setFontWeight(QFont.Bold)
            self._editor.setCurrentCharFormat(cfmt)
        elif tag == "h2":
            cfmt = self._editor.currentCharFormat()
            cfmt.setFontPointSize(18)
            cfmt.setFontWeight(QFont.Bold)
            self._editor.setCurrentCharFormat(cfmt)
        elif tag == "h3":
            cfmt = self._editor.currentCharFormat()
            cfmt.setFontPointSize(14)
            cfmt.setFontWeight(QFont.Bold)
            self._editor.setCurrentCharFormat(cfmt)

    def _on_font_changed(self, font: QFont) -> None:
        self._editor.setCurrentFont(font)
        settings = QSettings("SUOT", "PrintTemplate")
        settings.setValue("font_family", font.family())

    def _on_size_changed(self, text: str) -> None:
        try:
            sz = float(text)
            self._editor.setFontPointSize(sz)
            settings = QSettings("SUOT", "PrintTemplate")
            settings.setValue("font_size", int(sz))
        except ValueError:
            pass

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(
            self._editor.textColor(), self, I18n._("common.format")
        )
        if c.isValid():
            self._editor.setTextColor(c)
            self._color_btn.setStyleSheet(f"color: {c.name()}; font-weight: bold;")

    def _set_alignment(self, align: int) -> None:
        self._editor.setAlignment(align)
        self._align_left_btn.setChecked(align == Qt.AlignLeft)
        self._align_center_btn.setChecked(align == Qt.AlignCenter)
        self._align_right_btn.setChecked(align == Qt.AlignRight)

    def _apply_page_margins(self) -> None:
        self._page_margin_left = self._margin_left_spin.value()
        self._page_margin_right = self._margin_right_spin.value()
        self._page_margin_top = self._margin_top_spin.value()
        self._page_margin_bottom = self._margin_bottom_spin.value()
        self._show_page_shadow = self._page_shadow_cb.isChecked()
        settings = QSettings("SUOT", "PrintTemplate")
        settings.setValue("page_margin_left", self._page_margin_left)
        settings.setValue("page_margin_right", self._page_margin_right)
        settings.setValue("page_margin_top", self._page_margin_top)
        settings.setValue("page_margin_bottom", self._page_margin_bottom)
        settings.setValue("page_shadow", self._show_page_shadow)
        settings.setValue("page_orientation", self._orientation)
        shadow = (
            "" if not self._show_page_shadow else "selection-background-color:#DCEBFF;"
        )
        page_border = "border: 1px solid #C0C4CC;"
        if self._show_page_shadow:
            page_border = "border: 1px solid #C7CDD8;"
        self._editor.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #2C3E50; "
            f"{page_border} border-radius: 2px; padding: {self._page_margin_top}px {self._page_margin_right}px {self._page_margin_bottom}px {self._page_margin_left}px; "
            f"font-size: 11pt; {shadow}}}"
        )
        container_style = "background: #E8ECF1;"
        if self._show_page_shadow:
            container_style = "background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #EEF2F7, stop:1 #E3E7ED);"
        self._editor_container.setStyleSheet(container_style)
        self._sync_editor_height()

    def _apply_margin_preset(self) -> None:
        preset = self._margin_preset_combo.currentData()
        if preset == "narrow":
            vals = (30, 30, 30, 30)
        elif preset == "wide":
            vals = (90, 90, 70, 70)
        else:
            vals = (60, 60, 50, 50)
        spins = (
            self._margin_left_spin,
            self._margin_right_spin,
            self._margin_top_spin,
            self._margin_bottom_spin,
        )
        for spin, val in zip(spins, vals):
            spin.blockSignals(True)
            spin.setValue(val)
            spin.blockSignals(False)
        self._apply_page_margins()

    def _insert_quick_block(self) -> None:
        block = self._quick_blocks_combo.currentData()
        if block == "title":
            self._editor.insertHtml(
                "<h1 style='text-align:center;'>Документ</h1><p style='text-align:center;'>{company}</p><p><br></p>"
            )
        elif block == "violations":
            self._insert_repeat_block_start()
            self._insert_repeat_block_end()
        elif block == "header":
            self._insert_header_block()
        elif block == "signature":
            self._insert_signature_block()
        self._sync_editor_height()

    def _insert_repeat_block_start(self) -> None:
        self._editor.insertHtml(
            "<div data-repeat='violations' style='border:1px dashed #7C8AA5; background:#F7F9FC; padding:12px; margin:12px 0; border-radius:8px;'>"
            "<div style='font-size:10pt; color:#4B5563; margin-bottom:8px; font-weight:bold;'>"
            "ПОВТОРЯЕМЫЙ БЛОК: 1-е, 2-е, 3-е и следующие предписания</div>"
            "<div style='font-size:9.5pt; color:#6B7280; margin-bottom:10px;'>"
            "Используйте {violation_index} или {violation_number}, чтобы показывать номер предписания внутри списка.</div>"
        )
        self._editor.insertPlainText(
            "Предписание {violation_index}\nОписание: {description}\nСрок: {deadline}\nМеры: {recommended_action}\nШтраф: {fine}"
        )
        self._sync_editor_height()

    def _insert_repeat_block_end(self) -> None:
        self._editor.insertHtml(
            "<div style='font-size:10pt; color:#4B5563; margin-top:10px; font-weight:bold;'>КОНЕЦ ПОВТОРЯЕМОГО БЛОКА</div></div><p><br></p>"
        )
        self._sync_editor_height()

    def _insert_page_number(self) -> None:
        self._editor.insertPlainText("{page_number}")

    def _duplicate_template(self) -> None:
        html = self._editor.toHtml().strip()
        if not html:
            ToastNotification.notify(I18n._("error.invalid_data"), "error", 3000)
            return
        base_name = (
            self._template_name_edit.text().strip()
            or self._template_combo.currentText().rsplit(" ", 1)[0].strip()
        )
        new_name, ok = QInputDialog.getText(
            self,
            I18n._("template.duplicate"),
            I18n._("template.name"),
            text=base_name + " (копия)",
        )
        if not ok or not new_name.strip():
            return
        template_type = self._type_combo.currentData()
        new_id = self.db.save_print_template(new_name.strip(), template_type, html)
        self._current_id = new_id
        self._load_templates()
        for i in range(self._template_combo.count()):
            if self._template_combo.itemData(i) == new_id:
                self._template_combo.setCurrentIndex(i)
                break
        self._template_name_edit.setText(new_name.strip())

    def _update_format_buttons(self) -> None:
        fmt = self._editor.currentCharFormat()
        self._bold_btn.setChecked(self._editor.fontWeight() >= QFont.Bold)
        self._italic_btn.setChecked(fmt.fontItalic())
        self._underline_btn.setChecked(fmt.fontUnderline())
        self._strike_btn.setChecked(fmt.fontStrikeOut())
        a = self._editor.alignment()
        self._align_left_btn.setChecked(a == Qt.AlignLeft)
        self._align_center_btn.setChecked(a == Qt.AlignCenter)
        self._align_right_btn.setChecked(a == Qt.AlignRight)
        cursor = self._editor.textCursor()
        self._bullet_btn.setChecked(
            bool(cursor.currentList())
            and cursor.currentList().format().style() == QTextListFormat.ListDisc
        )
        self._number_btn.setChecked(
            bool(cursor.currentList())
            and cursor.currentList().format().style() == QTextListFormat.ListDecimal
        )
        self._heading_combo.blockSignals(True)
        html = self._editor.toHtml()
        if "<h1>" in html:
            self._heading_combo.setCurrentIndex(1)
        elif "<h2>" in html:
            self._heading_combo.setCurrentIndex(2)
        elif "<h3>" in html:
            self._heading_combo.setCurrentIndex(3)
        else:
            self._heading_combo.setCurrentIndex(0)
        self._heading_combo.blockSignals(False)

    def _on_type_changed(self) -> None:
        self._load_templates()
        self._build_field_tree()

    def _on_template_changed(self, idx: int) -> None:
        self._load_template_content(idx)

    def _load_templates(self) -> None:
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        template_type = self._type_combo.currentData()
        suffix = " 📄" if template_type == "order" else " 📊"
        for t in self.db.get_print_templates(template_type):
            self._template_combo.addItem(t["name"] + suffix, t["id"])
        self._template_combo.blockSignals(False)
        if self._template_combo.count():
            self._template_combo.setCurrentIndex(0)
            self._load_template_content(0)
        else:
            self._editor.clear()
            self._current_id = 0
        self._build_field_tree()
        self._update_status()

    def _update_status(self) -> None:
        plain = self._editor.toPlainText()
        chars = len(plain)
        words = len(plain.split()) if plain.strip() else 0
        try:
            pages = self._editor.document().pageCount()
        except Exception:
            pages = 1
        name = (
            self._template_name_edit.text().strip()
            or self._template_combo.currentText()
            or I18n._("template.untitled")
        )
        repeat_used = " | 🔁" if "ПОВТОРЯЕМЫЙ БЛОК" in plain else ""
        self._status_label.setText(
            f"{name}  |  {I18n._('common.count')}: {chars} {I18n._('template.chars')}, {words} {I18n._('template.words')}{repeat_used}"
        )
        self._update_page_nav(keep_position=True)

    def _editor_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self._editor)
        menu.setStyleSheet("""
            QMenu { background: #2C2C2E; color: #FFFFFF; border: 1px solid #3A3A3C;
                    border-radius: 8px; padding: 4px; }
            QMenu::item { padding: 8px 28px 8px 14px; border-radius: 4px; }
            QMenu::item:selected { background: #0A84FF; color: #FFFFFF; }
            QMenu::separator { height: 1px; background: #3A3A3C; margin: 4px 10px; }
        """)
        menu.addAction(
            I18n._("common.undo"), lambda: self._editor.undo(), QKeySequence.Undo
        )
        menu.addAction(
            I18n._("common.redo"), lambda: self._editor.redo(), QKeySequence.Redo
        )
        menu.addSeparator()
        menu.addAction(
            I18n._("common.cut"), lambda: self._editor.cut(), QKeySequence.Cut
        )
        menu.addAction(
            I18n._("common.copy"), lambda: self._editor.copy(), QKeySequence.Copy
        )
        menu.addAction(
            I18n._("common.paste"), lambda: self._editor.paste(), QKeySequence.Paste
        )
        menu.addSeparator()
        menu.addAction(
            I18n._("common.select_all"),
            lambda: self._editor.selectAll(),
            QKeySequence.SelectAll,
        )
        cursor = self._editor.textCursor()
        pos_in_doc = cursor.position()
        root = self._editor.document().rootFrame()
        in_table = False
        for fr in root.childFrames():
            if isinstance(fr, QTextTable):
                if fr.firstPosition() <= pos_in_doc <= fr.lastPosition():
                    in_table = True
                    break
        if in_table:
            menu.addSeparator()
            menu.addAction("↔ 100%", lambda: self._resize_table(100))
            menu.addAction("↔ 75%", lambda: self._resize_table(75))
            menu.addAction("↔ 50%", lambda: self._resize_table(50))
            menu.addAction("↔ 25%", lambda: self._resize_table(25))
        menu.exec_(self._editor.viewport().mapToGlobal(pos))

    def _filter_field_tree(self, text: str) -> None:
        for i in range(self._field_tree.topLevelItemCount()):
            parent = self._field_tree.topLevelItem(i)
            parent.setHidden(True)
            visible = False
            for j in range(parent.childCount()):
                child = parent.child(j)
                match = not text or text.lower() in child.text(0).lower()
                child.setHidden(not match)
                if match:
                    visible = True
            parent.setHidden(not visible)
            if visible:
                parent.setExpanded(True)
        self._field_combo.blockSignals(True)
        current = self._field_combo.currentIndex()
        for i in range(self._field_combo.count()):
            if i == 0:
                continue
            item_text = self._field_combo.itemText(i)
            self._field_combo.setItemHidden(
                i, bool(text) and text.lower() not in item_text.lower()
            )
        if current > 0 and self._field_combo.isItemHidden(current):
            self._field_combo.setCurrentIndex(0)
        self._field_combo.blockSignals(False)

    def _load_template_content(self, idx: int) -> None:
        if idx < 0:
            return
        tid = self._template_combo.itemData(idx)
        if not tid:
            return
        t = self.db.fetch_one("SELECT * FROM print_templates WHERE id=?", (tid,))
        if t:
            self._current_id = t["id"]
            self._editor.setHtml(t.get("html_content", ""))
            self._template_name_edit.setText(t.get("name", ""))

    def _new_template(self) -> None:
        name, ok = QInputDialog.getText(
            self, I18n._("template.register"), I18n._("template.name_prompt")
        )
        if not ok or not name.strip():
            return
        template_type = self._type_combo.currentData()
        t = (
            I18n._("print.order")
            if template_type == "order"
            else I18n._("print.report")
        )
        default_html = f"<h1>{t}</h1><p>« {I18n._('template.edit')} »</p>"
        try:
            new_id = self.db.save_print_template(
                name.strip(), template_type, default_html
            )
            self._current_id = new_id
            self._load_templates()
            for i in range(self._template_combo.count()):
                if self._template_combo.itemData(i) == new_id:
                    self._template_combo.setCurrentIndex(i)
                    break
            self._editor.setHtml(default_html)
            self._template_name_edit.setText(name.strip())
            ToastNotification.notify(I18n._("common.success"), "success", 3000)
        except Exception:
            ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _save_template(self) -> None:
        html = self._editor.toHtml().strip()
        if not html:
            ToastNotification.notify(I18n._("error.invalid_data"), "error", 3000)
            return
        name = (
            self._template_name_edit.text().strip()
            or self._template_combo.currentText().strip()
        )
        if not name:
            ToastNotification.notify(I18n._("error.invalid_data"), "error", 3000)
            return
        template_type = self._type_combo.currentData()
        try:
            if self._current_id:
                self.db.save_print_template(
                    name, template_type, html, template_id=self._current_id
                )
            else:
                new_id = self.db.save_print_template(name, template_type, html)
                self._current_id = new_id
            self._load_templates()
            for i in range(self._template_combo.count()):
                if self._template_combo.itemData(i) == self._current_id:
                    self._template_combo.setCurrentIndex(i)
                    break
            self._template_name_edit.setText(name)
            ToastNotification.notify(I18n._("common.saved"), "success", 3000)
            self._saved = True
        except Exception:
            ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    def _auto_save(self) -> None:
        if self._editor.document().isModified():
            self._save_template()
            self._editor.document().setModified(False)

    def _delete_template(self) -> None:
        if not self._current_id:
            return
        reply = QMessageBox.question(
            self,
            I18n._("common.confirm"),
            I18n._("template.delete_confirm"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.db.execute("DELETE FROM print_templates WHERE id=?", (self._current_id,))
        self._current_id = 0
        self._load_templates()
        ToastNotification.notify(I18n._("common.done"), "success", 3000)

    def _reset_template(self) -> None:
        reply = QMessageBox.question(
            self,
            I18n._("common.confirm"),
            I18n._("template.reset") + "?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        template_type = self._type_combo.currentData()
        defaults = self.db.fetch_one(
            "SELECT * FROM print_templates WHERE template_type=? AND is_default=1",
            (template_type,),
        )
        if defaults:
            self._editor.setHtml(defaults.get("html_content", ""))
            ToastNotification.notify(I18n._("common.done"), "success", 3000)

    def _rename_template(self) -> None:
        tid = self._template_combo.currentData()
        if not tid:
            ToastNotification.notify(I18n._("common.no_data"), "warning", 3000)
            return
        old_name = self._template_combo.currentText().rsplit(" ", 1)[0]
        new_name, ok = QInputDialog.getText(
            self, I18n._("common.rename"), I18n._("template.name"), text=old_name
        )
        if ok and new_name.strip():
            self.db.execute(
                "UPDATE print_templates SET name=? WHERE id=?", (new_name.strip(), tid)
            )
            self._template_name_edit.setText(new_name.strip())
            self._load_templates()
            ToastNotification.notify(I18n._("common.done"), "success", 3000)

    def _zoom_in(self) -> None:
        self._zoom_level = min(400, self._zoom_level + 10)
        self._apply_zoom()

    def _zoom_out(self) -> None:
        self._zoom_level = max(5, self._zoom_level - 10)
        self._apply_zoom()

    def _reset_zoom(self) -> None:
        self._zoom_level = 100
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        self._zoom_label.setText(f"{self._zoom_level}%")
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(self._zoom_level)
        self._zoom_slider.blockSignals(False)
        self._resize_editor()
        self._sync_editor_height()

    def _apply_zoom_slider(self, val: int) -> None:
        self._zoom_level = val
        self._apply_zoom()

    def _resize_editor(self) -> None:
        vs = self._editor_scroll.viewport().size()
        page_padding = 60
        fit_width = max(520, vs.width() - page_padding)
        fit_height = max(700, vs.height() - page_padding)

        pw, ph = self._orientations[self._orientation]
        width_scale = fit_width / float(pw)
        height_scale = fit_height / float(ph)
        fit_scale = min(width_scale, height_scale)
        fit_scale = max(0.2, fit_scale)
        zoom_scale = fit_scale * (self._zoom_level / 100.0)

        w = max(420, int(pw * zoom_scale))
        h = max(594, int(ph * zoom_scale))

        self._editor.setMinimumSize(w, h)
        self._editor.setMaximumWidth(w)
        self._editor.setMaximumHeight(16777215)
        self._editor.resize(w, h)
        self._editor.document().setPageSize(QSizeF(w, h))

    def _fit_page(self) -> None:
        self._zoom_level = 100
        self._apply_zoom()

    def _fit_width(self) -> None:
        vs = self._editor_scroll.viewport().size()
        pw, ph = self._orientations[self._orientation]
        w = max(520, vs.width() - 40)
        h = max(594, int(w * (ph / float(pw))))
        self._editor.setMinimumSize(w, h)
        self._editor.setMaximumWidth(w)
        self._editor.resize(w, h)
        self._zoom_level = 100
        self._zoom_label.setText("100%")
        self._sync_editor_height()

    def _get_page_pixel_height(self) -> int:
        pw, ph = self._orientations[self._orientation]
        return max(1, int(self._editor.width() * (ph / float(pw))))

    def _update_page_guide(self) -> None:
        if not hasattr(self, "_page_guide"):
            return
        self._page_guide.setGeometry(self._editor.geometry())
        self._page_guide.show()
        self._page_guide.raise_()
        self._page_guide.update()
        if hasattr(self, "_ruler"):
            self._ruler.update_position()

    def _update_page_nav(self, keep_position: bool = False) -> None:
        try:
            total = max(1, self._editor.document().pageCount())
        except Exception:
            total = 1
        current = min(self._page_nav_spin.value(), total) if keep_position else 1
        self._page_nav_spin.blockSignals(True)
        self._page_nav_spin.setMaximum(total)
        self._page_nav_spin.setValue(current)
        self._page_nav_spin.setSuffix(" / " + str(total))
        self._page_nav_spin.blockSignals(False)

    def _go_to_page(self, page: int) -> None:
        try:
            pw, ph = self._orientations[self._orientation]
            scale = self._editor.width() / float(pw) if pw else 1.0
            page_h = max(594, int(ph * scale))
            scroll_to = (page - 1) * page_h
            self._editor.verticalScrollBar().setValue(scroll_to)
        except Exception:
            pass

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(50, self._update_page_guide)
        if event.oldSize().width() != event.size().width():
            QTimer.singleShot(
                200, lambda: (self._update_page_guide(), self._sync_editor_height())
            )

    def _sync_editor_height(self) -> None:
        pw, ph = self._orientations[self._orientation]
        scale = self._editor.width() / float(pw) if pw else 1.0
        page_h = max(594, int(ph * scale))
        self._editor.document().setPageSize(QSizeF(self._editor.width(), page_h))
        page_count = self._editor.document().pageCount()
        target_h = max(page_h, page_count * page_h)
        self._editor.setMinimumHeight(target_h)
        self._editor.resize(self._editor.width(), target_h)
        self._update_page_guide()
        self._update_page_nav()

    def _on_orientation_changed(self, idx: int) -> None:
        self._orientation = self._orientation_combo.itemData(idx)
        self._apply_page_margins()
        self._fit_page()
        self._sync_editor_height()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _insert_table(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("template.insert_table"))
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setMinimumSize(420, 240)
        dlg.resize(520, 260)
        dlg.setStyleSheet(
            "QDialog { background: #F5F5F7; }"
            "QSpinBox { min-height: 30px; min-width: 90px; padding-right: 26px; }"
            "QSpinBox::up-button, QSpinBox::down-button { width: 24px; border-left: 1px solid #C0C4CC; background: #FFFFFF; }"
            "QSpinBox::up-arrow { image: none; width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-bottom: 6px solid #2C3E50; }"
            "QSpinBox::down-arrow { image: none; width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 6px solid #2C3E50; }"
        )
        lay = QVBoxLayout(dlg)
        lay.setSpacing(8)

        preview_label = QLabel(I18n._("template.insert_table") + ":")
        preview_label.setStyleSheet("font-weight: bold;")
        lay.addWidget(preview_label)

        rows_hint = QLabel(
            "<b>"
            + I18n._("template.table_rows")
            + "</b>  <span style='color:#6B7280;'>"
            + I18n._("template.table_hint_rows")
            + "</span>"
        )
        rows_hint.setWordWrap(True)
        lay.addWidget(rows_hint)
        rl = QHBoxLayout()
        rs = QSpinBox()
        rs.setRange(1, 20)
        rs.setValue(3)
        rs.setMinimumHeight(28)
        rs.setStyleSheet(
            "QSpinBox { padding: 4px 28px 4px 8px; border: 1px solid #999; border-radius: 6px; background: #FFFFFF; color: #2C3E50; }"
            "QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 24px; border-left: 1px solid #999; border-top-right-radius: 6px; }"
            "QSpinBox::up-arrow { width: 8px; height: 8px; }"
            "QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; border-left: 1px solid #999; border-bottom-right-radius: 6px; }"
            "QSpinBox::down-arrow { width: 8px; height: 8px; }"
        )
        rl.addWidget(rs)
        lay.addLayout(rl)
        cols_hint = QLabel(
            "<b>"
            + I18n._("template.table_columns")
            + "</b>  <span style='color:#6B7280;'>"
            + I18n._("template.table_hint_columns")
            + "</span>"
        )
        cols_hint.setWordWrap(True)
        lay.addWidget(cols_hint)
        cl = QHBoxLayout()
        cs = QSpinBox()
        cs.setRange(1, 10)
        cs.setValue(3)
        cs.setMinimumHeight(28)
        cs.setStyleSheet(
            "QSpinBox { padding: 4px 28px 4px 8px; border: 1px solid #999; border-radius: 6px; background: #FFFFFF; color: #2C3E50; }"
            "QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 24px; border-left: 1px solid #999; border-top-right-radius: 6px; }"
            "QSpinBox::up-arrow { width: 8px; height: 8px; }"
            "QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; border-left: 1px solid #999; border-bottom-right-radius: 6px; }"
            "QSpinBox::down-arrow { width: 8px; height: 8px; }"
        )
        cl.addWidget(cs)
        lay.addLayout(cl)
        btn_lay = QHBoxLayout()
        ok_btn = GlassButton(I18n._("common.ok"))
        ok_btn.clicked.connect(dlg.accept)
        btn_lay.addWidget(ok_btn)
        cancel_btn = GlassButton(I18n._("common.cancel"))
        cancel_btn.clicked.connect(dlg.reject)
        btn_lay.addWidget(cancel_btn)
        lay.addLayout(btn_lay)
        if dlg.exec_() != QDialog.Accepted:
            return
        rows, cols = rs.value(), cs.value()
        col_width = round(100 / max(1, cols), 2)
        table_html = (
            "<table border='1' cellspacing='0' cellpadding='0' "
            "style='border-collapse:collapse;width:100%;table-layout:fixed;margin:8px 0;'>"
        )
        for r in range(rows):
            table_html += "<tr>"
            for c in range(cols):
                table_html += (
                    f"<td style='width:{col_width}%;padding:8px;vertical-align:top;"
                    "word-break:break-word;overflow-wrap:anywhere;'>"
                    "&nbsp;</td>"
                )
            table_html += "</tr>"
        table_html += "</table>"
        table_html += (
            "<style>table img, td img {max-width:100%;height:auto;display:block;} "
            "table p {margin:0 0 6px 0;} table td {vertical-align:top;}</style>"
            "<p><br></p>"
        )
        self._editor.insertHtml(table_html)
        self._sync_editor_height()

    def _resize_table(self, pct: int) -> None:
        cursor = self._editor.textCursor()
        pos = cursor.position()
        doc = self._editor.document()
        root = doc.rootFrame()
        target_table = None
        for fr in root.childFrames():
            if isinstance(fr, QTextTable):
                if fr.firstPosition() <= pos <= fr.lastPosition():
                    target_table = fr
                    break
        if not target_table:
            return
        col_count = target_table.columns()
        col_pct = round(pct / max(1, col_count), 2)
        fmt = target_table.format()
        widths = [QTextLength(QTextLength.PercentageLength, col_pct)] * col_count
        fmt.setColumnWidthConstraints(widths)
        target_table.setFormat(fmt)
        self._sync_editor_height()

    def _clear_formatting(self) -> None:
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            html = cursor.selection().toHtml()
            html = re.sub(r'style="[^"]*"', "", html)
            html = re.sub(r"<span[^>]*>", "", html)
            html = re.sub(r"</span>", "", html)
            html = re.sub(r"<font[^>]*>", "", html)
            html = re.sub(r"</font>", "", html)
            cursor.insertHtml(html)
        else:
            dfmt = self._editor.currentCharFormat()
            dfmt.setFont(QFont("Segoe UI", 11))
            dfmt.setFontWeight(QFont.Normal)
            dfmt.setFontItalic(False)
            dfmt.setFontUnderline(False)
            dfmt.setFontStrikeOut(False)
            dfmt.setForeground(QColor("#2C3E50"))
            self._editor.setCurrentCharFormat(dfmt)

    def _apply_line_spacing(self, val: float) -> None:
        cursor = self._editor.textCursor()
        fmt = cursor.blockFormat()
        fmt.setLineHeight(val * 100, QTextBlockFormat.ProportionalHeight)
        cursor.setBlockFormat(fmt)
        self._editor.setTextCursor(cursor)

    def _auto_format_document(self) -> None:
        html = self._editor.toHtml().strip()
        if not html:
            return
        html = re.sub(
            r"<table(?![^>]*table-layout:fixed)([^>]*)>",
            r"<table\1 style='width:100%;border-collapse:collapse;table-layout:fixed;margin:8px 0;'>",
            html,
        )
        html = re.sub(
            r"<td(?![^>]*vertical-align:top)([^>]*)>",
            r"<td\1 style='padding:8px;vertical-align:top;word-break:break-word;overflow-wrap:anywhere;'>",
            html,
        )
        html = re.sub(
            r"<img(?![^>]*max-width:100%)([^>]*)>",
            r"<img\1 style='max-width:100%;height:auto;display:block;'>",
            html,
        )
        html = html.replace("<p></p>", "<p><br></p>")
        self._editor.blockSignals(True)
        self._editor.setHtml(html)
        self._editor.blockSignals(False)
        self._sync_editor_height()
        self._update_status()

    def _insert_header_block(self) -> None:
        self._editor.insertHtml(
            "<table style='width:100%; border-collapse:collapse; margin-bottom:16px;'><tr>"
            "<td style='width:50%; vertical-align:top;'><b>{company}</b><br>{date}</td>"
            "<td style='width:50%; text-align:right; vertical-align:top;'>№ {record_number}</td>"
            "</tr></table><p><br></p>"
        )
        self._sync_editor_height()

    def _insert_signature_block(self) -> None:
        self._editor.insertHtml(
            "<p><br></p><table style='width:100%; border-collapse:collapse; margin-top:20px;'><tr>"
            "<td style='width:60%;'>Ответственный: {responsible}</td>"
            "<td style='width:40%; text-align:right;'>Подпись: ____________</td>"
            "</tr></table>"
        )
        self._sync_editor_height()

    def _find_text(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(I18n._("common.find"))
        dlg.setFixedSize(360, 140)
        lay = QVBoxLayout(dlg)
        search_input = GlassLineEdit()
        search_input.setPlaceholderText(I18n._("common.find"))
        lay.addWidget(search_input)
        case_cb = GlassCheckBox(I18n._("template.match_case"))
        lay.addWidget(case_cb)
        btn_lay = QHBoxLayout()

        def _do_find():
            flags = QTextDocument.FindFlags()
            if case_cb.isChecked():
                flags |= QTextDocument.FindCaseSensitively
            self._editor.find(search_input.text(), flags)

        find_btn = GlassButton(I18n._("common.find"))
        find_btn.clicked.connect(_do_find)
        btn_lay.addWidget(find_btn)
        close_btn = GlassButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.accept)
        btn_lay.addWidget(close_btn)
        lay.addLayout(btn_lay)
        search_input.returnPressed.connect(_do_find)
        dlg.exec_()

    def _insert_separator(self) -> None:
        self._editor.insertHtml(
            "<hr style='border:none;border-top:1px solid #C0C4CC;margin:12px 0;'>"
        )

    def _insert_page_break(self) -> None:
        self._editor.insertHtml(
            "<div style='page-break-before:always; border-top: 2px dashed #A0A4AC; "
            "margin: 30px 0 10px 0; padding: 4px 0; text-align: center;'>"
            "<span style='background:#E8ECF1; color:#8E8E93; font-size:9pt; "
            "padding:2px 16px; border-radius:8px;'>📄 A4</span></div>"
        )

    def _insert_date(self) -> None:
        self._editor.insertPlainText(datetime.now().strftime("%d.%m.%Y"))

    def _quick_print(self) -> None:
        PrintEngine.print_document(self._editor.toHtml(), self)

    def _insert_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите изображение",
            "",
            "Изображения (*.png *.jpg *.jpeg *.gif *.bmp)",
        )
        if not path:
            return
        size_mb = os.path.getsize(path) / (1024 * 1024)
        if size_mb > 10:
            QMessageBox.warning(
                self,
                "Ошибка",
                f"Файл слишком большой ({size_mb:.1f} МБ). Максимум 10 МБ.",
            )
            return
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        ext = path.rsplit(".", 1)[-1].lower()
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "bmp": "image/bmp",
        }.get(ext, "image/png")
        self._editor.insertHtml(
            f'<p><img src="data:{mime};base64,{b64}" '
            f'style="max-width:100%;height:auto;display:block;margin:8px 0;"></p>'
        )
        self._sync_editor_height()

    def _indent(self) -> None:
        cursor = self._editor.textCursor()
        block = cursor.block()
        fmt = block.blockFormat()
        fmt.setIndent(fmt.indent() + 1)
        cursor.setBlockFormat(fmt)
        self._editor.setTextCursor(cursor)

    def _unindent(self) -> None:
        cursor = self._editor.textCursor()
        block = cursor.block()
        fmt = block.blockFormat()
        fmt.setIndent(max(0, fmt.indent() - 1))
        cursor.setBlockFormat(fmt)
        self._editor.setTextCursor(cursor)

    def _import_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Импорт шаблона", "", "HTML файлы (*.html *.htm);;Все файлы (*)"
        )
        if path:
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
            self._editor.blockSignals(True)
            self._editor.setHtml(html)
            self._editor.blockSignals(False)
            self._sync_editor_height()
            self._update_status()
            ToastNotification.notify(I18n._("template.imported"), "success", 3000)

    def _export_template(self) -> None:
        html = self._editor.toHtml().strip()
        if not html:
            ToastNotification.notify(I18n._("error.invalid_data"), "error", 3000)
            return
        name = self._template_name_edit.text().strip() or "template"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт шаблона",
            f"{name}.html",
            "HTML файлы (*.html *.htm);;Все файлы (*)",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            ToastNotification.notify(I18n._("template.exported"), "success", 3000)

    def _toggle_ruler(self) -> None:
        if hasattr(self, "_ruler"):
            self._ruler.setVisible(not self._ruler.isVisible())
            if self._ruler.isVisible():
                self._ruler.update_position()

    def _export_pdf(self) -> None:
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPrinter.A4)
        dlg = QPrintDialog(printer, self)
        if dlg.exec_() == QPrintDialog.Accepted:
            self._editor.document().print_(printer)
            ToastNotification.notify(I18n._("template.pdf_sent"), "success", 3000)

    def _show_html_source(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("template.html_source"))
        dlg.resize(700, 500)
        lay = QVBoxLayout(dlg)
        editor = QPlainTextEdit()
        editor.setPlainText(self._editor.toHtml())
        editor.setStyleSheet("font-family:Consolas,'Courier New'; font-size:10pt;")
        editor.setReadOnly(True)
        lay.addWidget(editor, 1)
        btn = GlassButton(I18n._("common.close"))
        btn.clicked.connect(dlg.accept)
        hlay = QHBoxLayout()
        hlay.addStretch()
        hlay.addWidget(btn)
        lay.addLayout(hlay)
        dlg.exec_()

    def _toggle_favorite(self) -> None:
        name = (
            self._template_name_edit.text().strip()
            or self._template_combo.currentText().strip()
        )
        if not name:
            ToastNotification.notify(I18n._("template.no_active"), "warning", 3000)
            return
        if name.startswith("★ "):
            new_name = name[2:]
            ToastNotification.notify(I18n._("template.favorite_removed"), "info", 3000)
        else:
            new_name = "★ " + name
            ToastNotification.notify(I18n._("template.favorite_added"), "success", 3000)
        if self._current_id:
            self.db.execute(
                "UPDATE print_templates SET name=? WHERE id=?",
                (new_name, self._current_id),
            )
            self._template_name_edit.setText(new_name)
            self._load_templates()

    def _case_lower(self) -> None:
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(cursor.selectedText().lower())

    def _case_upper(self) -> None:
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(cursor.selectedText().upper())

    def _case_title(self) -> None:
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(cursor.selectedText().title())

    def _special_chars(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("template.special_chars"))
        dlg.setFixedSize(420, 260)
        lay = QVBoxLayout(dlg)
        glyphs = "©®™§°±¶•·←↑→↓↔↕♦♥♣♠◘○◙♂♀♪♫☼►◄↕‼¶§▬↨↑↓→←∟↔▲▼"
        glay = QGridLayout()
        glay.setSpacing(4)
        row = col = 0
        for ch in glyphs:
            btn = GlassButton(ch)
            btn.setFixedSize(32, 32)
            btn.setStyleSheet("font-size:14px;")
            btn.clicked.connect(
                lambda checked, c=ch: (self._editor.insertPlainText(c), dlg.accept())
            )
            glay.addWidget(btn, row, col)
            col += 1
            if col > 9:
                col = 0
                row += 1
        lay.addLayout(glay)
        close_btn = GlassButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.reject)
        lay.addWidget(close_btn)
        dlg.exec_()

    def _apply_quick_style(self, idx: int) -> None:
        style = self._quick_style_combo.itemData(idx)
        if not style:
            return
        self._quick_style_combo.setCurrentIndex(0)
        html = self._editor.toHtml()
        cursor = self._editor.textCursor()
        if style == "quote":
            cursor.insertHtml(
                '<blockquote style="border-left:4px solid #4B7BFF; margin:12px 0; padding:8px 16px; background:#F7F9FC; color:#4B5563;">Цитата</blockquote>'
            )
        elif style == "alert":
            cursor.insertHtml(
                '<div style="border:1px solid #FFC107; background:#FFF8E1; border-radius:8px; padding:12px; margin:12px 0; color:#856404;">⚠️ Внимание!</div>'
            )
        elif style == "code":
            cursor.insertHtml(
                '<pre style="background:#1E1E2E; color:#D4D4D4; border-radius:6px; padding:12px; font-family:Consolas; font-size:10pt;">код</pre>'
            )
        self._sync_editor_height()

    def _page_bg_color(self) -> None:
        color = QColorDialog.getColor(QColor("#FFFFFF"), self, "Цвет фона страницы")
        if color.isValid():
            self._editor.setStyleSheet(
                re.sub(
                    r"background:#[A-Fa-f0-9]{6}",
                    f"background:{color.name()}",
                    self._editor.styleSheet(),
                )
                if "background:#" in self._editor.styleSheet()
                else self._editor.styleSheet()
                + f" QTextEdit {{ background: {color.name()}; }}"
            )

    def _filter_templates(self, text: str) -> None:
        if not text:
            if hasattr(self, "_saved_template_items"):
                self._template_combo.blockSignals(True)
                self._template_combo.clear()
                for name, data in self._saved_template_items:
                    self._template_combo.addItem(name, data)
                self._template_combo.blockSignals(False)
                del self._saved_template_items
            return
        if not hasattr(self, "_saved_template_items"):
            self._saved_template_items = [
                (self._template_combo.itemText(i), self._template_combo.itemData(i))
                for i in range(self._template_combo.count())
            ]
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        for name, data in self._saved_template_items:
            if text.lower() in (name or "").lower():
                self._template_combo.addItem(name, data)
        self._template_combo.blockSignals(False)

    def _update_word_count(self) -> None:
        text = self._editor.toPlainText()
        words = len(text.split()) if text.strip() else 0
        chars = len(text)
        self._word_count_label.setText(f"{words} / {chars}")

    def _template_notes(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("template.notes_title"))
        dlg.resize(400, 300)
        lay = QVBoxLayout(dlg)
        notes = QTextEdit()
        notes.setPlainText(
            self._template_notes_text if hasattr(self, "_template_notes_text") else ""
        )
        notes.setPlaceholderText(I18n._("template.notes_placeholder"))
        lay.addWidget(notes, 1)
        hlay = QHBoxLayout()
        save_btn = GlassButton(I18n._("common.save"))

        def _save_notes():
            self._template_notes_text = notes.toPlainText()
            ToastNotification.notify(I18n._("template.notes_saved"), "success", 2000)
            dlg.accept()

        save_btn.clicked.connect(_save_notes)
        hlay.addStretch()
        hlay.addWidget(save_btn)
        close_btn = GlassButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.reject)
        hlay.addWidget(close_btn)
        lay.addLayout(hlay)
        dlg.exec_()

    def _document_outline(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("template.document_outline"))
        dlg.resize(300, 400)
        lay = QVBoxLayout(dlg)
        tree = QTreeWidget()
        tree.setHeaderLabels(["Заголовок"])
        tree.setAnimated(True)
        tree.setIndentation(12)
        doc = self._editor.document()
        block = doc.begin()
        level_map = {}
        root_items = {}
        while block != doc.end():
            fmt = block.blockFormat()
            level = fmt.headingLevel()
            if level > 0:
                text = block.text()[:80]
                item = QTreeWidgetItem([text if text else "(пусто)"])
                item.setData(0, Qt.UserRole, block.position())
                if level == 1:
                    tree.addTopLevelItem(item)
                    level_map = {1: item}
                    root_items[1] = item
                else:
                    parent = level_map.get(level - 1) or root_items.get(1) or tree
                    if isinstance(parent, QTreeWidgetItem):
                        parent.addChild(item)
                    else:
                        tree.addTopLevelItem(item)
                    level_map[level] = item
                for k in list(level_map.keys()):
                    if k > level:
                        del level_map[k]
            block = block.next()

        def _go_to(pos):
            cursor = self._editor.textCursor()
            cursor.setPosition(pos)
            self._editor.setTextCursor(cursor)
            self._editor.setFocus()
            dlg.accept()

        tree.itemDoubleClicked.connect(
            lambda item, col: _go_to(item.data(0, Qt.UserRole))
        )
        lay.addWidget(tree, 1)
        close_btn = GlassButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.reject)
        lay.addWidget(close_btn)
        dlg.exec_()

    # ═══ 10 global changes ═══════════════════════════════════════════

    def _find_replace(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(I18n._("common.find") + " / " + I18n._("common.replace"))
        dlg.setFixedSize(400, 200)
        lay = QVBoxLayout(dlg)
        find_lay = QHBoxLayout()
        find_lay.addWidget(QLabel(I18n._("common.find") + ":"))
        find_input = GlassLineEdit()
        find_input.setPlaceholderText(I18n._("common.find"))
        find_lay.addWidget(find_input, 1)
        lay.addLayout(find_lay)
        repl_lay = QHBoxLayout()
        repl_lay.addWidget(QLabel(I18n._("common.replace") + ":"))
        repl_input = GlassLineEdit()
        repl_input.setPlaceholderText(I18n._("common.replace"))
        repl_lay.addWidget(repl_input, 1)
        lay.addLayout(repl_lay)
        case_cb = GlassCheckBox(I18n._("template.match_case"))
        lay.addWidget(case_cb)
        btn_lay = QHBoxLayout()

        def _make_btn(text: str, cb) -> QPushButton:
            b = QPushButton(text)
            b.clicked.connect(cb)
            return b

        def _find():
            text = find_input.text()
            if not text:
                return
            flags = (
                QTextDocument.FindFlags()
                if not case_cb.isChecked()
                else QTextDocument.FindCaseSensitively
            )
            if not self._editor.find(text, flags):
                cursor = self._editor.textCursor()
                cursor.movePosition(QTextCursor.Start)
                self._editor.setTextCursor(cursor)
                self._editor.find(text, flags)

        def _replace():
            text = find_input.text()
            if not text:
                return
            cursor = self._editor.textCursor()
            if cursor.hasSelection() and cursor.selectedText() == text:
                cursor.insertText(repl_input.text())
            self._editor.find(text)

        def _replace_all():
            text = find_input.text()
            if not text:
                return
            cursor = self._editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self._editor.setTextCursor(cursor)
            count = 0
            while self._editor.find(text):
                self._editor.textCursor().insertText(repl_input.text())
                count += 1
            ToastNotification.notify(
                I18n._("common.replaced_count", count=count), "info", 3000
            )

        btn_lay.addWidget(_make_btn(I18n._("common.find"), _find))
        btn_lay.addWidget(_make_btn(I18n._("common.replace"), _replace))
        btn_lay.addWidget(_make_btn(I18n._("template.replace_all"), _replace_all))
        btn_lay.addStretch()
        btn_lay.addWidget(_make_btn(I18n._("common.close"), dlg.reject))
        lay.addLayout(btn_lay)
        dlg.exec_()

    def _document_stats(self) -> None:
        doc = self._editor.document()
        text = self._editor.toPlainText()
        words = len(text.split()) if text.strip() else 0
        chars = len(text)
        chars_no_space = len(text.replace(" ", ""))
        paras = doc.blockCount()
        pages = max(1, int(doc.pageCount()))
        lines = 0
        block = doc.begin()
        while block != doc.end():
            lines += block.lineCount()
            block = block.next()
        msg = (
            f"📊 {I18n._('stat.words')}: {words}\n"
            f"🔤 {I18n._('stat.characters')}: {chars}\n"
            f"✏️ {I18n._('stat.characters_no_spaces')}: {chars_no_space}\n"
            f"📝 {I18n._('stat.paragraphs')}: {paras}\n"
            f"📄 {I18n._('stat.pages')}: {pages}\n"
            f"📏 {I18n._('stat.lines')}: {lines}"
        )
        QMessageBox.information(self, I18n._("stat.document_stats"), msg)

    def _increase_font_size(self) -> None:
        cursor = self._editor.textCursor()
        fmt = cursor.charFormat()
        size = fmt.fontPointSize()
        if size <= 0:
            size = 11
        fmt.setFontPointSize(min(72, size + 1))
        cursor.setCharFormat(fmt)
        self._editor.setTextCursor(cursor)
        self._update_format_buttons()

    def _decrease_font_size(self) -> None:
        cursor = self._editor.textCursor()
        fmt = cursor.charFormat()
        size = fmt.fontPointSize()
        if size <= 0:
            size = 11
        fmt.setFontPointSize(max(6, size - 1))
        cursor.setCharFormat(fmt)
        self._editor.setTextCursor(cursor)
        self._update_format_buttons()

    def _align_left(self) -> None:
        self._editor.setAlignment(Qt.AlignLeft)

    def _align_center(self) -> None:
        self._editor.setAlignment(Qt.AlignCenter)

    def _align_right(self) -> None:
        self._editor.setAlignment(Qt.AlignRight)

    def _align_justify(self) -> None:
        self._editor.setAlignment(Qt.AlignJustify)

    def _paste_plain(self) -> None:
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            cursor = self._editor.textCursor()
            cursor.insertText(text)
            ToastNotification.notify(I18n._("template.pasted_plain"), "info", 2000)

    def _toggle_ruler_units(self) -> None:
        self._ruler_units = getattr(self, "_ruler_units", "cm")
        self._ruler_units = "in" if self._ruler_units == "cm" else "cm"
        unit_name = (
            I18n._("template.ruler_cm")
            if self._ruler_units == "cm"
            else I18n._("template.ruler_in")
        )
        ToastNotification.notify(f"{I18n._('common.ruler')}: {unit_name}", "info", 2000)
        if hasattr(self, "_ruler"):
            self._ruler.update()

    def _go_first_page(self) -> None:
        self._editor.verticalScrollBar().setValue(0)
        self._page_nav_spin.setValue(1)

    def _go_last_page(self) -> None:
        scrollbar = self._editor.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        doc = self._editor.document()
        total = max(1, int(doc.pageCount()))
        self._page_nav_spin.setValue(total)

    def _toggle_bullet(self) -> None:
        cursor = self._editor.textCursor()
        block = cursor.block()
        fmt = block.blockFormat()
        if fmt.indent() > 0 or cursor.currentList():
            cursor.currentList().remove(cursor.block())
        else:
            cursor.insertList(QTextListFormat.ListDisc)
        self._bullet_btn.setChecked(cursor.currentList() is not None)

    def _toggle_number(self) -> None:
        cursor = self._editor.textCursor()
        block = cursor.block()
        fmt = block.blockFormat()
        if fmt.indent() > 0 or cursor.currentList():
            cursor.currentList().remove(cursor.block())
        else:
            cursor.insertList(QTextListFormat.ListDecimal)
        self._number_btn.setChecked(cursor.currentList() is not None)

    def _preview_template(self, multi_sample: bool = False) -> None:
        try:
            dlg = QDialog(self)
            dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
            dlg.setWindowTitle(I18n._("template.preview"))
            screen = QApplication.primaryScreen().availableGeometry()
            dlg.resize(int(screen.width() * 0.85), int(screen.height() * 0.85))
            dlg.move(
                (screen.width() - dlg.width()) // 2,
                (screen.height() - dlg.height()) // 2,
            )
            layout = QVBoxLayout(dlg)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            pbrowser = QTextBrowser()
            pbrowser.setStyleSheet(
                "QTextBrowser { background: #FFFFFF; color: #2C3E50; border: none; "
                "padding: 30px 40px; font-size: 11pt; }"
            )
            pbrowser.document().setDefaultFont(QFont("Segoe UI", 11))

            raw_html = self._editor.toHtml().strip()
            rendered = raw_html
            if raw_html:
                if self._type_combo.currentData() == "order":
                    if multi_sample:
                        records = [
                            {
                                "id": 1,
                                "data_json": {
                                    "description": "Описание нарушения 1",
                                    "deadline": "01.07.2026",
                                    "recommended_action": "Устранить 1",
                                    "fine": "1000",
                                    "responsible": "Ответственный 1",
                                    "company": "ООО Тест",
                                    "date": "01.06.2026",
                                },
                            },
                            {
                                "id": 2,
                                "data_json": {
                                    "description": "Описание нарушения 2",
                                    "deadline": "05.07.2026",
                                    "recommended_action": "Устранить 2",
                                    "fine": "2000",
                                    "responsible": "Ответственный 2",
                                    "company": "ООО Тест",
                                    "date": "01.06.2026",
                                },
                            },
                            {
                                "id": 3,
                                "data_json": {
                                    "description": "Описание нарушения 3",
                                    "deadline": "10.07.2026",
                                    "recommended_action": "Устранить 3",
                                    "fine": "3000",
                                    "responsible": "Ответственный 3",
                                    "company": "ООО Тест",
                                    "date": "01.06.2026",
                                },
                            },
                        ]
                        repeat_start = (
                            "ПОВТОРЯЕМЫЙ БЛОК: 1-е, 2-е, 3-е и следующие предписания"
                        )
                        repeat_end = "КОНЕЦ ПОВТОРЯЕМОГО БЛОКА"
                        if repeat_start in raw_html and repeat_end in raw_html:
                            before, rest = raw_html.split(repeat_start, 1)
                            block, after = rest.split(repeat_end, 1)
                            parts = []
                            for index, rec in enumerate(records, start=1):
                                rendered_part = block
                                for key, val in rec["data_json"].items():
                                    rendered_part = rendered_part.replace(
                                        f"{{{key}}}", str(val)
                                    )
                                rendered_part = rendered_part.replace(
                                    "{id}", str(rec["id"])
                                )
                                rendered_part = rendered_part.replace(
                                    "{record_number}", str(rec["id"])
                                )
                                rendered_part = rendered_part.replace(
                                    "{violation_number}", str(index)
                                )
                                rendered_part = rendered_part.replace(
                                    "{violation_index}", str(index)
                                )
                                rendered_part = rendered_part.replace(
                                    "{page_number}", str(index)
                                )
                                parts.append(rendered_part)
                            rendered = (
                                "<html><body>"
                                + before
                                + "".join(parts)
                                + after
                                + "</body></html>"
                            )
                        else:
                            rendered_parts = []
                            for index, rec in enumerate(records, start=1):
                                rendered_part = raw_html
                                for key, val in rec["data_json"].items():
                                    rendered_part = rendered_part.replace(
                                        f"{{{key}}}", str(val)
                                    )
                                rendered_part = rendered_part.replace(
                                    "{id}", str(rec["id"])
                                )
                                rendered_part = rendered_part.replace(
                                    "{record_number}", str(rec["id"])
                                )
                                rendered_part = rendered_part.replace(
                                    "{violation_number}", str(index)
                                )
                                rendered_part = rendered_part.replace(
                                    "{violation_index}", str(index)
                                )
                                rendered_part = rendered_part.replace(
                                    "{page_number}", str(index)
                                )
                                rendered_parts.append(rendered_part)
                            rendered = (
                                "<html><body>"
                                + rendered_parts[0]
                                + "".join(
                                    "<div style='page-break-before:always; margin:0; padding:0; height:1px;'></div>"
                                    + p
                                    for p in rendered_parts[1:]
                                )
                                + "</body></html>"
                            )
                    else:
                        sample = {
                            "id": "1",
                            "date": "01.06.2026",
                            "company": "ООО Тест",
                            "responsible": "Иванов И.И.",
                            "deadline": "30.07.2026",
                            "description": "Тестовое описание нарушения",
                            "recommended_action": "Устранить нарушение",
                            "fine": "5000",
                            "photos_section": "",
                            "app_name": "SUOT",
                            "generated_at": "01.06.2026",
                            "record_number": "1",
                            "page_number": "1",
                        }
                        rendered = PrintEngine.render_order(
                            sample, photos=[], template_html=raw_html
                        )
                else:
                    rendered = PrintEngine.render_report(
                        "ООО Тест", template_html=raw_html
                    )
                pbrowser.setHtml(rendered)
            layout.addWidget(pbrowser, 1)

            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(12, 8, 12, 8)
            print_btn = GlassButton("🖨 " + I18n._("common.print"))
            print_btn.clicked.connect(
                lambda: PrintEngine.print_document(pbrowser.toHtml(), dlg)
            )
            btn_layout.addWidget(print_btn)
            btn_layout.addStretch()
            close_btn = GlassButton(I18n._("common.close"))
            close_btn.clicked.connect(dlg.accept)
            btn_layout.addWidget(close_btn)
            layout.addLayout(btn_layout)

            dlg.exec_()
        except Exception as exc:
            QMessageBox.critical(self, I18n._("template.preview_error"), str(exc))

    def _select_and_close(self) -> None:
        if self._current_id:
            self.selected_id = self._current_id
        self.accept()
