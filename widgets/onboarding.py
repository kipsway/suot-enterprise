from typing import Any, Dict, Optional

from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_core.animation_manager import fade_in
from app_core.design_tokens import RADIUS, palette
from app_core.theme_engine import ThemeEngine
from services.database import DatabaseManager
from widgets.glass_button import GlassButton


_STEPS = [
    {
        "icon": "🏢",
        "title": "Добро пожаловать в SUOT Enterprise!",
        "text": "Система управления охраной труда. "
        "Помогает отслеживать сотрудников, нарушения, "
        "СИЗ, обучение и наряды-допуски.",
        "tip": "Нажмите «Далее» для знакомства с возможностями.",
    },
    {
        "icon": "👤",
        "title": "Управление сотрудниками",
        "text": "Ведите базу сотрудников с ФИО, должностью, "
        "подразделением и контактами. "
        "Привязывайте медосмотры и квалификацию.",
        "tip": "Ctrl+N — добавить сотрудника",
    },
    {
        "icon": "⚠️",
        "title": "Нарушения и предписания",
        "text": "Фиксируйте нарушения, выдавайте предписания "
        "с контролем сроков исполнения. "
        "Автоматический расчёт штрафов.",
        "tip": "Статус просрочки подсвечивается красным",
    },
    {
        "icon": "🛡️",
        "title": "СИЗ и инспекции",
        "text": "Учёт выдачи СИЗ, контроль сроков годности, "
        "цифровые инспекции с отметками о замене.",
        "tip": "Просроченные СИЗ выделяются в таблице",
    },
    {
        "icon": "🤖",
        "title": "AI-ассистент",
        "text": "Встроенный AI-помощник с поддержкой OpenAI, "
        "DeepSeek, Claude, Gemini, Ollama. "
        "Режимы: чат, поиск, агент (создание/изменение записей).",
        "tip": "Нажмите Ctrl+K для быстрого поиска",
    },
    {
        "icon": "📊",
        "title": "Аналитика и прогнозы",
        "text": "Статистика в реальном времени, прогноз рисков "
        "на основе исторических данных, "
        "AI-генерация отчётов и инсайтов.",
        "tip": "Данные обновляются автоматически",
    },
]


class OnboardingDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Добро пожаловать")
        self.setFixedSize(520, 400)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._step = 0
        self._build_ui()
        self._show_step(0)
        ThemeEngine.on_change(self.update)

        QTimer.singleShot(200, lambda: fade_in(self, duration=400))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget()
        self._card.setFixedSize(520, 400)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(32, 28, 32, 24)
        card_layout.setSpacing(12)

        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setFixedHeight(60)
        f = self.font()
        f.setPointSize(36)
        self._icon_label.setFont(f)
        card_layout.addWidget(self._icon_label)

        self._title_label = QLabel()
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setWordWrap(True)
        f2 = self.font()
        f2.setPointSize(16)
        f2.setBold(True)
        self._title_label.setFont(f2)
        card_layout.addWidget(self._title_label)

        self._text_label = QLabel()
        self._text_label.setAlignment(Qt.AlignCenter)
        self._text_label.setWordWrap(True)
        f3 = self.font()
        f3.setPointSize(12)
        self._text_label.setFont(f3)
        card_layout.addWidget(self._text_label)

        self._tip_label = QLabel()
        self._tip_label.setAlignment(Qt.AlignCenter)
        self._tip_label.setWordWrap(True)
        f4 = self.font()
        f4.setPointSize(10)
        self._tip_label.setFont(f4)
        card_layout.addWidget(self._tip_label)

        card_layout.addStretch()

        # dots
        self._dots = QHBoxLayout()
        self._dots.setAlignment(Qt.AlignCenter)
        card_layout.addLayout(self._dots)

        # buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._prev_btn = GlassButton("← Назад", variant="ghost")
        self._prev_btn.clicked.connect(self._prev_step)
        btn_row.addWidget(self._prev_btn)
        btn_row.addStretch()
        self._next_btn = GlassButton("Далее →")
        self._next_btn.clicked.connect(self._next_step)
        btn_row.addWidget(self._next_btn)
        self._finish_btn = GlassButton("Готово ✅")
        self._finish_btn.clicked.connect(self._finish)
        self._finish_btn.hide()
        btn_row.addWidget(self._finish_btn)
        card_layout.addLayout(btn_row)

        layout.addWidget(self._card, 0, Qt.AlignCenter)

    def _show_step(self, idx: int) -> None:
        step = _STEPS[idx]
        self._icon_label.setText(step["icon"])
        self._title_label.setText(step["title"])
        self._text_label.setText(step["text"])
        self._tip_label.setText(f"💡 {step['tip']}")

        self._prev_btn.setVisible(idx > 0)
        is_last = idx == len(_STEPS) - 1
        self._next_btn.setVisible(not is_last)
        self._finish_btn.setVisible(is_last)

        for i in range(len(_STEPS)):
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(
                f"background: {'#007AFF' if i == idx else '#C7C7CC'}; "
                f"border-radius: 4px; margin: 0 3px;"
            )
            while self._dots.count():
                w = self._dots.takeAt(0)
                if w and w.widget():
                    w.widget().deleteLater()
            for j in range(len(_STEPS)):
                d = QLabel()
                d.setFixedSize(8, 8)
                d.setStyleSheet(
                    f"background: {'#007AFF' if j == idx else '#C7C7CC'}; "
                    f"border-radius: 4px; margin: 0 3px;"
                )
                self._dots.addWidget(d)

    def _next_step(self) -> None:
        if self._step < len(_STEPS) - 1:
            self._step += 1
            self._show_step(self._step)

    def _prev_step(self) -> None:
        if self._step > 0:
            self._step -= 1
            self._show_step(self._step)

    def _finish(self) -> None:
        self.accept()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = ThemeEngine._current_theme == "dark"
        pal = palette(dark)
        r = 16
        path = QPainterPath()
        from PyQt5.QtCore import QRectF

        path.addRoundedRect(QRectF(self._card.geometry()), r, r)
        bg = QColor(30, 30, 35, 245) if dark else QColor(255, 255, 255, 250)
        p.fillPath(path, bg)
        p.setPen(QPen(QColor(pal.border), 0.5))
        p.drawPath(path)
        p.end()
