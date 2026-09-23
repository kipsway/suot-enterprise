from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QHeaderView, QTableWidget

from app_core.design_tokens import palette
from app_core.theme_engine import ThemeEngine


def apply_glass_table(table: QTableWidget) -> None:
    dark = ThemeEngine._current_theme == "dark"
    pal = palette(dark)

    accent = QColor(pal.accent)
    bg_alt = QColor(pal.bg_secondary)
    border_c = QColor(pal.border)
    text_c = QColor(pal.text_primary)

    table.setAlternatingRowColors(True)
    table.setStyleSheet(f"""
    QTableWidget {{
        background: transparent;
        border: none;
        gridline-color: {border_c.name()};
        selection-background-color: {accent.name()}20;
        selection-color: {text_c.name()};
        alternate-background-color: {bg_alt.name()};
    }}
    QTableWidget::item {{
        padding: 4px 8px;
        border: none;
    }}
    QTableWidget::item:hover {{
        background: {accent.name()}10;
    }}
    QHeaderView::section {{
        background: {bg_alt.name()};
        color: {text_c.name()};
        padding: 6px 8px;
        border: none;
        border-bottom: 1px solid {border_c.name()};
        font-weight: 600;
        font-size: 12px;
    }}
    QHeaderView::section:hover {{
        background: {accent.name()}15;
    }}
    """)
