from typing import Optional
from PyQt5.QtWidgets import QApplication
from services.database import DatabaseManager


class ThemeEngine:
    _app: Optional[QApplication] = None
    _current_theme: str = "light"
    _current_accent: str = "#2196F3"

    @classmethod
    def init(cls, app: QApplication) -> None:
        cls._app = app

    @classmethod
    def apply(cls, theme: Optional[str] = None,
              accent: Optional[str] = None) -> None:
        db = DatabaseManager()
        cls._current_theme = theme or db.get_setting("theme", "light")
        cls._current_accent = accent or db.get_setting("accent_color", "#2196F3")
        if cls._app:
            css = cls._build_dark() if cls._current_theme == "dark" else cls._build_light()
            cls._app.setStyleSheet(css)

    @classmethod
    def theme(cls) -> str:
        return cls._current_theme

    @classmethod
    def accent(cls) -> str:
        return cls._current_accent

    @staticmethod
    def _contrast_accent(hex_color: str) -> str:
        h = hex_color.lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return "#FFFFFF" if lum < 0.5 else "#1C1C1E"

    @staticmethod
    def _build_light() -> str:
        a = ThemeEngine._current_accent
        at = ThemeEngine._contrast_accent(a)
        t = "#1C1C1E"
        s = "#6C6C70"
        return f"""
        QMainWindow, QDialog, QWidget {{
            background-color: #F5F5F7; color: {t};
            font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
        }}
        QLabel {{
            color: {t}; background: transparent; border: none;
        }}
        QLabel[heading="true"] {{
            font-size: 22px; font-weight: 700; color: {t};
            padding: 6px 0; letter-spacing: -0.3px;
        }}
        QLabel[card_value="true"] {{
            font-size: 34px; font-weight: 700; color: {at};
            letter-spacing: -0.5px;
        }}
        QLabel[card_label="true"] {{
            font-size: 12px; color: {s}; font-weight: 500;
            letter-spacing: 0.3px;
        }}
        QLabel[status_green="true"] {{ color: #34C759; font-weight: 600; }}
        QLabel[status_yellow="true"] {{ color: #FF9500; font-weight: 600; }}
        QLabel[status_red="true"] {{ color: #FF3B30; font-weight: 600; }}
        QLabel[status_grey="true"] {{ color: {s}; font-weight: 600; }}

        QFrame {{
            border: none; background: transparent;
        }}
        QFrame[card="true"] {{
            background: rgba(255,255,255,0.85);
            border-radius: 14px;
            border: 1px solid rgba(0,0,0,0.06);
        }}
        QFrame[card_hover="true"]:hover {{
            background: rgba(255,255,255,0.95);
            border: 1px solid {a}66;
        }}

        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}, stop:1 {a}BB);
            color: {at}; border: none;
            border-radius: 10px; padding: 11px 26px; font-size: 13px;
            font-weight: 600; min-height: 18px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}, stop:1 {a}DD);
            border: 1px solid rgba(255,255,255,0.15);
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}88, stop:1 {a}AA);
            padding-top: 13px; padding-bottom: 9px;
        }}
        QPushButton:disabled {{
            background: #E5E5EA; color: #C7C7CC;
        }}
        QPushButton[flat="true"] {{
            background: transparent; color: {at}; border: 1.5px solid {a}55;
            font-weight: 600;
        }}
        QPushButton[flat="true"]:hover {{
            background: {a}15; border: 1.5px solid {a};
        }}
        QPushButton[flat="true"]:pressed {{
            background: {a}25;
        }}
        QPushButton[small="true"] {{
            padding: 7px 16px; font-size: 12px; min-height: 14px;
            border-radius: 8px; font-weight: 600;
        }}

        QToolButton {{
            background: transparent; border: none; border-radius: 8px;
            padding: 6px 10px; color: {s}; font-size: 12px;
            font-weight: 500; min-height: 24px;
        }}
        QToolButton:hover {{
            background: {a}15; color: {at};
        }}
        QToolButton:checked {{
            background: {a}20; color: {at}; font-weight: 600;
        }}

        QLineEdit, QTextEdit, QPlainTextEdit {{
            background: rgba(255,255,255,0.9); color: {t};
            border: 1.5px solid #D2D2D7; border-radius: 10px;
            padding: 9px 14px; font-size: 13px;
            selection-background-color: {a}40;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1.5px solid {a};
            background: #FFFFFF;
        }}
        QLineEdit:disabled, QTextEdit:disabled {{
            background: #F0F0F5; color: #C7C7CC;
        }}

        QComboBox {{
            background: rgba(255,255,255,0.9); color: {t};
            border: 1.5px solid #D2D2D7; border-radius: 10px;
            padding: 8px 14px; font-size: 13px;
            min-height: 18px;
        }}
        QComboBox:hover, QComboBox:focus {{
            border: 1.5px solid {a};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: top right;
            width: 30px; border: none; border-left: 1px solid #E5E5EA;
            border-top-right-radius: 10px; border-bottom-right-radius: 10px;
        }}
        QComboBox QAbstractItemView {{
            background: rgba(255,255,255,0.98); color: {t};
            border: 1px solid #D2D2D7; border-radius: 10px;
            selection-background-color: {a}20;
            selection-color: {t}; outline: none;
            padding: 4px;
        }}

        QCheckBox, QRadioButton {{
            spacing: 8px; color: {t}; font-size: 13px;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 20px; height: 20px; border-radius: 5px;
            border: 1.5px solid #C7C7CC;
            background: rgba(255,255,255,0.9);
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background: {a}; border: 1.5px solid {a};
        }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border: 1.5px solid {a};
        }}
        QRadioButton::indicator {{ border-radius: 11px; }}

        QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {{
            background: rgba(255,255,255,0.9); color: {t};
            border: 1.5px solid #D2D2D7; border-radius: 10px;
            padding: 8px 14px; font-size: 13px; min-height: 18px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
            border: 1.5px solid {a};
        }}

        QTableWidget {{
            background: #FFFFFF; color: {t};
            border: 1px solid #E5E5EA; border-radius: 12px;
            gridline-color: #F0F0F5;
            selection-background-color: {a}; selection-color: #FFFFFF;
            font-size: 13px; alternate-background-color: #FAFAFD;
        }}
        QTableWidget::item {{
            padding: 10px 14px; border-bottom: 1px solid #F0F0F5;
            min-height: 24px; color: {t};
        }}
        QTableWidget::item:hover {{ background: {a}15; }}
        QTableWidget::item:selected {{ background: {a}; color: #FFFFFF; }}
        QTableWidget::item:selected:!active {{ background: {a}CC; color: #FFFFFF; }}
        QHeaderView::section {{
            background: #F2F2F7; color: {s}; font-weight: 600;
            font-size: 12px; padding: 11px 14px; border: none;
            border-bottom: 1.5px solid #E5E5EA;
            border-right: 1.5px solid #E5E5EA; min-height: 26px;
        }}
        QHeaderView::section:last {{ border-right: none; }}
        QHeaderView::section:hover {{ background: #E8E8ED; color: {t}; }}
        QHeaderView::section:active {{ background: {a}15; color: {t}; }}

        QTabWidget::pane {{ border: none; background: transparent; }}
        QTabBar::tab {{
            background: transparent; color: {s}; font-size: 13px;
            font-weight: 500; padding: 12px 24px; border: none;
            border-bottom: 2.5px solid transparent; min-height: 20px;
        }}
        QTabBar::tab:hover {{
            color: {t}; background: rgba(0,0,0,0.04);
            border-radius: 8px 8px 0 0;
        }}
        QTabBar::tab:selected {{
            color: {at}; border-bottom: 2.5px solid {a};
        }}

        QScrollBar:vertical {{
            background: transparent; width: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:vertical {{
            background: #C7C7CC; border-radius: 3px; min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: #AEAEB2; }}
        QScrollBar:horizontal {{
            background: transparent; height: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:horizontal {{
            background: #C7C7CC; border-radius: 3px; min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: #AEAEB2; }}

        QMenu {{
            background: rgba(255,255,255,0.97);
            color: {t}; border: 1px solid rgba(0,0,0,0.08);
            border-radius: 12px; padding: 6px;
        }}
        QMenu::item {{
            padding: 9px 36px 9px 18px; border-radius: 6px; font-size: 13px;
        }}
        QMenu::item:selected {{ background: {a}15; color: {at}; }}
        QMenu::separator {{
            height: 1px; background: #E5E5EA; margin: 4px 12px;
        }}

        QMenuBar {{
            background: rgba(255,255,255,0.9); color: {t};
            border-bottom: 1px solid #E5E5EA; padding: 2px;
        }}
        QMenuBar::item {{ padding: 7px 14px; border-radius: 6px; }}
        QMenuBar::item:selected {{ background: {a}15; }}

        QToolBar {{
            background: rgba(255,255,255,0.92);
            border: none; border-bottom: 1px solid #E5E5EA;
            padding: 4px 8px; spacing: 2px;
        }}

        QStatusBar {{
            background: rgba(255,255,255,0.92); color: {s};
            font-size: 12px;
            border-top: 1px solid #E5E5EA; padding: 3px 12px;
        }}

        QGroupBox {{
            font-weight: 600; font-size: 14px; color: {t};
            border: 1px solid #E5E5EA; border-radius: 12px;
            margin-top: 18px; padding: 18px 14px 14px 14px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 4px 12px; background: #F5F5F7;
            border-radius: 6px; left: 14px;
        }}

        QListWidget {{
            background: rgba(255,255,255,0.9); color: {t};
            border: 1px solid #E5E5EA; border-radius: 12px;
            padding: 4px; outline: none;
        }}
        QListWidget::item {{
            padding: 9px 14px; border-radius: 6px; margin: 2px 0;
        }}
        QListWidget::item:selected {{ background: {a}20; color: {t}; }}
        QListWidget::item:hover {{ background: {a}10; }}

        QScrollArea {{ border: none; background: transparent; }}
        QSplitter::handle {{ background: #E5E5EA; width: 1px; }}

        QToolTip {{
            background: rgba(0,0,0,0.85); color: #FFFFFF;
            font-size: 12px; border: none; border-radius: 8px;
            padding: 8px 14px;
        }}

        QMessageBox {{ background: rgba(255,255,255,0.97); }}
        QMessageBox QLabel {{ color: {t}; font-size: 13px; }}

        QProgressBar {{
            background: #E5E5EA; border: none; border-radius: 4px;
            height: 6px; text-align: center; font-size: 10px;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {a}, stop:1 {a}AA);
            border-radius: 4px;
        }}

        QTreeWidget {{
            background: #FFFFFF; color: {t};
            border: 1px solid #E5E5EA; border-radius: 10px;
            outline: none; alternate-background-color: #FAFAFD;
        }}
        QTreeWidget::item {{ padding: 7px 10px; border-radius: 5px; }}
        QTreeWidget::item:selected {{ background: {a}20; color: {t}; }}
        QTreeWidget::item:hover {{ background: {a}10; }}

        QTextBrowser {{
            background: #FFFFFF; color: {t};
            border: 1px solid #E5E5EA; border-radius: 10px;
            padding: 10px;
        }}

        QDialog {{ background: rgba(245,245,247,0.98); }}
        """

    @staticmethod
    def _build_dark() -> str:
        a = ThemeEngine._current_accent
        at = ThemeEngine._contrast_accent(a)
        t = "#F5F5F7"
        s = "#8E8E93"
        return f"""
        QMainWindow, QDialog, QWidget {{
            background-color: #000000; color: {t};
            font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
        }}
        QLabel {{
            color: {t}; background: transparent; border: none;
        }}
        QLabel[heading="true"] {{
            font-size: 22px; font-weight: 700; color: #FFFFFF;
            padding: 6px 0; letter-spacing: -0.3px;
        }}
        QLabel[card_value="true"] {{
            font-size: 34px; font-weight: 700; color: {at};
            letter-spacing: -0.5px;
        }}
        QLabel[card_label="true"] {{
            font-size: 12px; color: {s}; font-weight: 500;
            letter-spacing: 0.3px;
        }}
        QLabel[status_green="true"] {{ color: #30D158; font-weight: 600; }}
        QLabel[status_yellow="true"] {{ color: #FF9F0A; font-weight: 600; }}
        QLabel[status_red="true"] {{ color: #FF453A; font-weight: 600; }}
        QLabel[status_grey="true"] {{ color: {s}; font-weight: 600; }}

        QFrame {{ border: none; background: transparent; }}
        QFrame[card="true"] {{
            background: rgba(28,28,30,0.85);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
        }}
        QFrame[card_hover="true"]:hover {{
            background: rgba(44,44,46,0.9);
            border: 1px solid {a}88;
        }}

        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}, stop:1 {a}BB);
            color: {at}; border: none;
            border-radius: 10px; padding: 11px 26px; font-size: 13px;
            font-weight: 600; min-height: 18px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}, stop:1 {a}DD);
            border: 1px solid rgba(255,255,255,0.15);
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}88, stop:1 {a}AA);
            padding-top: 13px; padding-bottom: 9px;
        }}
        QPushButton:disabled {{
            background: #3A3A3C; color: #636366;
        }}
        QPushButton[flat="true"] {{
            background: transparent; color: {at}; border: 1.5px solid {a}55;
            font-weight: 600;
        }}
        QPushButton[flat="true"]:hover {{
            background: {a}22; border: 1.5px solid {a};
        }}
        QPushButton[flat="true"]:pressed {{
            background: {a}30;
        }}
        QPushButton[small="true"] {{
            padding: 7px 16px; font-size: 12px; min-height: 14px;
            border-radius: 8px; font-weight: 600;
        }}

        QToolButton {{
            background: transparent; border: none; border-radius: 8px;
            padding: 6px 10px; color: {s}; font-size: 12px;
            font-weight: 500;
        }}
        QToolButton:hover {{ background: {a}22; color: {at}; }}
        QToolButton:checked {{ background: {a}30; color: {at}; font-weight: 600; }}

        QLineEdit, QTextEdit, QPlainTextEdit {{
            background: rgba(28,28,30,0.9); color: {t};
            border: 1.5px solid #3A3A3C; border-radius: 10px;
            padding: 9px 14px; font-size: 13px;
            selection-background-color: {a}40;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1.5px solid {a};
            background: rgba(44,44,46,0.95);
        }}
        QLineEdit:disabled, QTextEdit:disabled {{
            background: #1C1C1E; color: #636366;
        }}

        QComboBox {{
            background: rgba(28,28,30,0.9); color: {t};
            border: 1.5px solid #3A3A3C; border-radius: 10px;
            padding: 8px 14px; font-size: 13px; min-height: 18px;
        }}
        QComboBox:hover, QComboBox:focus {{ border: 1.5px solid {a}; }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: top right;
            width: 30px; border: none; border-left: 1px solid #3A3A3C;
            border-top-right-radius: 10px; border-bottom-right-radius: 10px;
        }}
        QComboBox QAbstractItemView {{
            background: rgba(28,28,30,0.98); color: {t};
            border: 1px solid #3A3A3C; border-radius: 10px;
            selection-background-color: {a}30;
            selection-color: {t}; outline: none; padding: 4px;
        }}

        QCheckBox, QRadioButton {{
            spacing: 8px; color: {t}; font-size: 13px;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 20px; height: 20px; border-radius: 5px;
            border: 1.5px solid #636366;
            background: rgba(28,28,30,0.9);
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background: {a}; border: 1.5px solid {a};
        }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border: 1.5px solid {a};
        }}
        QRadioButton::indicator {{ border-radius: 11px; }}

        QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {{
            background: rgba(28,28,30,0.9); color: {t};
            border: 1.5px solid #3A3A3C; border-radius: 10px;
            padding: 8px 14px; font-size: 13px; min-height: 18px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{ border: 1.5px solid {a}; }}
        QSpinBox::up-button, QDoubleSpinBox::up-button,
        QDateEdit::up-button, QTimeEdit::up-button {{
            subcontrol-origin: border; subcontrol-position: top right;
            width: 26px; border-left: 1px solid #3A3A3C;
            border-top-right-radius: 10px;
        }}
        QSpinBox::down-button, QDoubleSpinBox::down-button,
        QDateEdit::down-button, QTimeEdit::down-button {{
            subcontrol-origin: border; subcontrol-position: bottom right;
            width: 26px; border-left: 1px solid #3A3A3C;
            border-bottom-right-radius: 10px;
        }}

        QTableWidget {{
            background: #1C1C1E; color: {t};
            border: 1px solid #2C2C2E; border-radius: 12px;
            gridline-color: #2C2C2E;
            selection-background-color: {a}; selection-color: #FFFFFF;
            font-size: 13px; alternate-background-color: #222224;
        }}
        QTableWidget::item {{ padding: 10px 14px; border-bottom: 1px solid #2C2C2E; min-height: 24px; color: {t}; }}
        QTableWidget::item:hover {{ background: {a}25; }}
        QTableWidget::item:selected {{ background: {a}; color: #FFFFFF; }}
        QTableWidget::item:selected:!active {{ background: {a}CC; color: #FFFFFF; }}
        QHeaderView::section {{
            background: #1C1C1E; color: {s}; font-weight: 600;
            font-size: 12px; padding: 11px 14px; border: none;
            border-bottom: 1.5px solid #2C2C2E;
            border-right: 1.5px solid #2C2C2E; min-height: 26px;
        }}
        QHeaderView::section:last {{ border-right: none; }}
        QHeaderView::section:hover {{ background: #2C2C2E; color: {t}; }}
        QHeaderView::section:active {{ background: {a}20; color: {t}; }}

        QTabWidget::pane {{ border: none; background: transparent; }}
        QTabBar::tab {{
            background: transparent; color: {s}; font-size: 13px;
            font-weight: 500; padding: 12px 24px; border: none;
            border-bottom: 2.5px solid transparent; min-height: 20px;
        }}
        QTabBar::tab:hover {{ color: {t}; background: rgba(255,255,255,0.06); border-radius: 8px 8px 0 0; }}
        QTabBar::tab:selected {{ color: {at}; border-bottom: 2.5px solid {a}; }}

        QScrollBar:vertical {{ background: transparent; width: 6px; border-radius: 3px; }}
        QScrollBar::handle:vertical {{ background: #48484A; border-radius: 3px; min-height: 30px; }}
        QScrollBar::handle:vertical:hover {{ background: #636366; }}
        QScrollBar:horizontal {{ background: transparent; height: 6px; border-radius: 3px; }}
        QScrollBar::handle:horizontal {{ background: #48484A; border-radius: 3px; min-width: 30px; }}
        QScrollBar::handle:horizontal:hover {{ background: #636366; }}

        QMenu {{
            background: rgba(28,28,30,0.97);
            color: {t}; border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px; padding: 6px;
        }}
        QMenu::item {{ padding: 9px 36px 9px 18px; border-radius: 6px; font-size: 13px; }}
        QMenu::item:selected {{ background: {a}28; color: {at}; }}
        QMenu::separator {{ height: 1px; background: #3A3A3C; margin: 4px 12px; }}

        QMenuBar {{ background: rgba(28,28,30,0.95); color: {t}; border-bottom: 1px solid #2C2C2E; padding: 2px; }}
        QMenuBar::item {{ padding: 7px 14px; border-radius: 6px; }}
        QMenuBar::item:selected {{ background: {a}22; }}

        QToolBar {{ background: rgba(28,28,30,0.95); border: none; border-bottom: 1px solid #2C2C2E; padding: 4px 8px; spacing: 2px; }}
        QStatusBar {{ background: rgba(28,28,30,0.95); color: {s}; font-size: 12px; border-top: 1px solid #2C2C2E; padding: 3px 12px; }}

        QGroupBox {{
            font-weight: 600; font-size: 14px; color: {t};
            border: 1px solid #2C2C2E; border-radius: 12px;
            margin-top: 18px; padding: 18px 14px 14px 14px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 4px 12px; background: #000000;
            border-radius: 6px; left: 14px;
        }}

        QListWidget {{ background: rgba(28,28,30,0.9); color: {t}; border: 1px solid #2C2C2E; border-radius: 12px; padding: 4px; outline: none; }}
        QListWidget::item {{ padding: 9px 14px; border-radius: 6px; margin: 2px 0; }}
        QListWidget::item:selected {{ background: {a}30; color: {t}; }}
        QListWidget::item:hover {{ background: {a}15; }}

        QScrollArea {{ border: none; background: transparent; }}
        QSplitter::handle {{ background: #2C2C2E; width: 1px; }}

        QToolTip {{ background: rgba(0,0,0,0.9); color: {t}; font-size: 12px; border: 1px solid #3A3A3C; border-radius: 8px; padding: 8px 14px; }}
        QMessageBox {{ background: rgba(28,28,30,0.97); }}
        QMessageBox QLabel {{ color: {t}; font-size: 13px; }}

        QProgressBar {{ background: #2C2C2E; border: none; border-radius: 4px; height: 6px; text-align: center; font-size: 10px; }}
        QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {a}, stop:1 {a}AA); border-radius: 4px; }}

        QTreeWidget {{ background: #1C1C1E; color: {t}; border: 1px solid #2C2C2E; border-radius: 10px; outline: none; alternate-background-color: #222224; }}
        QTreeWidget::item {{ padding: 7px 10px; border-radius: 5px; }}
        QTreeWidget::item:selected {{ background: {a}30; color: {t}; }}
        QTreeWidget::item:hover {{ background: {a}15; }}

        QTextBrowser {{ background: #1C1C1E; color: {t}; border: 1px solid #2C2C2E; border-radius: 10px; padding: 10px; }}
        QDialog {{ background: rgba(0,0,0,0.98); }}
        """
