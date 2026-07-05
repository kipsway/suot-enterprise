from typing import Optional
from PyQt5.QtWidgets import QApplication
from services.database import DatabaseManager


class ThemeEngine:
    _app: Optional[QApplication] = None
    _current_theme: str = "light"
    _current_accent: str = "#2196F3"

    _GLASS_BG = (
        "background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        "  stop:0 rgba(255,255,255,0.12), stop:0.5 rgba(255,255,255,0.06),"
        "  stop:1 rgba(255,255,255,0.03));"
        "border: 1px solid rgba(255,255,255,0.18);"
    )

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
        gb = ThemeEngine._GLASS_BG
        return f"""
        QMainWindow, QDialog {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #E8EDF2, stop:0.4 #F0F2F5, stop:1 #E5EAF0);
            color: {t};
            font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
        }}
        QWidget {{
            color: {t};
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
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.78),
                stop:1 rgba(255,255,255,0.62));
            border: 1px solid rgba(255,255,255,0.45);
            border-radius: 16px;
        }}
        QFrame[card_hover="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.88),
                stop:1 rgba(255,255,255,0.72));
            border: 1px solid {a}88;
        }}

        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}, stop:1 {a}CC);
            color: {at}; border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px; padding: 11px 26px; font-size: 13px;
            font-weight: 600; min-height: 18px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}, stop:1 {a}DD);
            border: 1px solid rgba(255,255,255,0.25);
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}88, stop:1 {a}AA);
            padding-top: 13px; padding-bottom: 9px;
        }}
        QPushButton:disabled {{
            background: rgba(200,200,205,0.5); color: rgba(199,199,204,0.8);
            border: 1px solid rgba(0,0,0,0.04);
        }}
        QPushButton[flat="true"] {{
            background: transparent; color: {at}; border: 1.5px solid {a}55;
            font-weight: 600;
        }}
        QPushButton[flat="true"]:hover {{
            background: {a}18; border: 1.5px solid {a};
        }}
        QPushButton[flat="true"]:pressed {{
            background: {a}28;
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
            background: {a}18; color: {at};
        }}
        QToolButton:checked {{
            background: {a}22; color: {at}; font-weight: 600;
        }}

        QLineEdit, QTextEdit, QPlainTextEdit {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.85),
                stop:1 rgba(255,255,255,0.72));
            color: {t};
            border: 1.5px solid rgba(0,0,0,0.08);
            border-radius: 10px; padding: 9px 14px; font-size: 13px;
            selection-background-color: {a}40;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1.5px solid {a};
            background: rgba(255,255,255,0.92);
        }}
        QLineEdit:disabled, QTextEdit:disabled {{
            background: rgba(240,240,245,0.5); color: #C7C7CC;
        }}

        QComboBox {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.85),
                stop:1 rgba(255,255,255,0.72));
            color: {t};
            border: 1.5px solid rgba(0,0,0,0.08); border-radius: 10px;
            padding: 8px 14px; font-size: 13px; min-height: 18px;
        }}
        QComboBox:hover, QComboBox:focus {{
            border: 1.5px solid {a};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: top right;
            width: 30px; border: none; border-left: 1px solid rgba(0,0,0,0.06);
            border-top-right-radius: 10px; border-bottom-right-radius: 10px;
        }}
        QComboBox QAbstractItemView {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.97),
                stop:1 rgba(255,255,255,0.92));
            color: {t};
            border: 1px solid rgba(0,0,0,0.08); border-radius: 10px;
            selection-background-color: {a}20;
            selection-color: {t}; outline: none; padding: 4px;
        }}

        QCheckBox, QRadioButton {{
            spacing: 8px; color: {t}; font-size: 13px;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 20px; height: 20px; border-radius: 5px;
            border: 1.5px solid #C7C7CC;
            background: rgba(255,255,255,0.85);
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background: {a}; border: 1.5px solid {a};
        }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border: 1.5px solid {a};
        }}
        QRadioButton::indicator {{ border-radius: 11px; }}

        QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.85),
                stop:1 rgba(255,255,255,0.72));
            color: {t};
            border: 1.5px solid rgba(0,0,0,0.08); border-radius: 10px;
            padding: 8px 14px; font-size: 13px; min-height: 18px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
            border: 1.5px solid {a};
        }}

        QTableWidget {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.75),
                stop:1 rgba(255,255,255,0.58));
            color: {t};
            border: 1px solid rgba(255,255,255,0.35); border-radius: 14px;
            gridline-color: rgba(0,0,0,0.04);
            selection-background-color: {a}; selection-color: #FFFFFF;
            font-size: 13px; alternate-background-color: rgba(250,250,253,0.5);
        }}
        QTableWidget::item {{
            padding: 10px 14px; border-bottom: 1px solid rgba(0,0,0,0.03);
            min-height: 24px; color: {t};
        }}
        QTableWidget::item:hover {{ background: {a}12; }}
        QTableWidget::item:selected {{ background: {a}; color: #FFFFFF; }}
        QTableWidget::item:selected:!active {{ background: {a}BB; color: #FFFFFF; }}
        QHeaderView::section {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(242,242,247,0.9),
                stop:1 rgba(232,232,237,0.8));
            color: {s}; font-weight: 600;
            font-size: 12px; padding: 11px 14px; border: none;
            border-bottom: 1px solid rgba(0,0,0,0.05);
            border-right: 1px solid rgba(0,0,0,0.03); min-height: 26px;
        }}
        QHeaderView::section:last {{ border-right: none; }}
        QHeaderView::section:hover {{ background: rgba(232,232,237,0.9); color: {t}; }}
        QHeaderView::section:active {{ background: {a}15; color: {t}; }}

        QTabWidget::pane {{ border: none; background: transparent; }}
        QTabBar::tab {{
            background: transparent; color: {s}; font-size: 13px;
            font-weight: 500; padding: 12px 24px; border: none;
            border-bottom: 2.5px solid transparent; min-height: 20px;
        }}
        QTabBar::tab:hover {{
            color: {t}; background: rgba(255,255,255,0.35);
            border-radius: 10px 10px 0 0;
        }}
        QTabBar::tab:selected {{
            color: {at}; border-bottom: 2.5px solid {a};
        }}

        QScrollBar:vertical {{
            background: transparent; width: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(199,199,204,0.7); border-radius: 3px; min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: rgba(174,174,178,0.8); }}
        QScrollBar:horizontal {{
            background: transparent; height: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:horizontal {{
            background: rgba(199,199,204,0.7); border-radius: 3px; min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: rgba(174,174,178,0.8); }}

        QMenu {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.96),
                stop:1 rgba(255,255,255,0.90));
            color: {t}; border: 1px solid rgba(0,0,0,0.06);
            border-radius: 14px; padding: 6px;
        }}
        QMenu::item {{
            padding: 9px 36px 9px 18px; border-radius: 6px; font-size: 13px;
        }}
        QMenu::item:selected {{ background: {a}15; color: {at}; }}
        QMenu::separator {{
            height: 1px; background: rgba(0,0,0,0.06); margin: 4px 12px;
        }}

        QMenuBar {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.85),
                stop:1 rgba(255,255,255,0.75));
            color: {t};
            border-bottom: 1px solid rgba(0,0,0,0.05); padding: 2px;
        }}
        QMenuBar::item {{ padding: 7px 14px; border-radius: 6px; }}
        QMenuBar::item:selected {{ background: {a}15; }}

        QToolBar {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.88),
                stop:1 rgba(255,255,255,0.78));
            border: none; border-bottom: 1px solid rgba(0,0,0,0.04);
            padding: 4px 8px; spacing: 2px;
        }}

        QStatusBar {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.88),
                stop:1 rgba(255,255,255,0.78));
            color: {s}; font-size: 12px;
            border-top: 1px solid rgba(0,0,0,0.04); padding: 3px 12px;
        }}

        QGroupBox {{
            font-weight: 600; font-size: 14px; color: {t};
            border: 1px solid rgba(0,0,0,0.06); border-radius: 14px;
            margin-top: 18px; padding: 18px 14px 14px 14px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 4px 12px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.8),
                stop:1 rgba(255,255,255,0.6));
            border-radius: 6px; left: 14px;
        }}

        QListWidget {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.82),
                stop:1 rgba(255,255,255,0.65));
            color: {t};
            border: 1px solid rgba(0,0,0,0.06); border-radius: 12px;
            padding: 4px; outline: none;
        }}
        QListWidget::item {{
            padding: 9px 14px; border-radius: 6px; margin: 2px 0;
        }}
        QListWidget::item:selected {{ background: {a}20; color: {t}; }}
        QListWidget::item:hover {{ background: {a}10; }}

        QScrollArea {{ border: none; background: transparent; }}
        QSplitter::handle {{ background: rgba(0,0,0,0.06); width: 1px; }}

        QToolTip {{
            background: rgba(0,0,0,0.82); color: #FFFFFF;
            font-size: 12px; border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px; padding: 8px 14px;
        }}

        QMessageBox {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.96),
                stop:1 rgba(255,255,255,0.90));
        }}
        QMessageBox QLabel {{ color: {t}; font-size: 13px; }}

        QProgressBar {{
            background: rgba(200,200,205,0.4); border: none;
            border-radius: 4px; height: 6px;
            text-align: center; font-size: 10px;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {a}, stop:1 {a}AA);
            border-radius: 4px;
        }}

        QTreeWidget {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.78),
                stop:1 rgba(255,255,255,0.60));
            color: {t};
            border: 1px solid rgba(0,0,0,0.06); border-radius: 12px;
            outline: none; alternate-background-color: rgba(250,250,253,0.4);
        }}
        QTreeWidget::item {{ padding: 7px 10px; border-radius: 5px; }}
        QTreeWidget::item:selected {{ background: {a}20; color: {t}; }}
        QTreeWidget::item:hover {{ background: {a}10; }}

        QTextBrowser {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.80),
                stop:1 rgba(255,255,255,0.62));
            color: {t};
            border: 1px solid rgba(0,0,0,0.06); border-radius: 12px;
            padding: 10px;
        }}

        QDialog {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #E8EDF2, stop:0.4 #F0F2F5, stop:1 #E5EAF0);
        }}
        """

    @staticmethod
    def _build_dark() -> str:
        a = ThemeEngine._current_accent
        at = ThemeEngine._contrast_accent(a)
        t = "#F5F5F7"
        s = "#8E8E93"
        return f"""
        QMainWindow, QDialog {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0D0D0D, stop:0.5 #1A1A1E, stop:1 #0F0F12);
            color: {t};
            font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
        }}
        QWidget {{
            color: {t};
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
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.08),
                stop:1 rgba(255,255,255,0.03));
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
        }}
        QFrame[card_hover="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.12),
                stop:1 rgba(255,255,255,0.06));
            border: 1px solid {a}88;
        }}

        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {a}, stop:1 {a}CC);
            color: {at}; border: 1px solid rgba(255,255,255,0.08);
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
            background: rgba(58,58,60,0.6); color: rgba(99,99,102,0.7);
            border: 1px solid rgba(255,255,255,0.03);
        }}
        QPushButton[flat="true"] {{
            background: transparent; color: {at}; border: 1.5px solid {a}55;
            font-weight: 600;
        }}
        QPushButton[flat="true"]:hover {{
            background: {a}22; border: 1.5px solid {a};
        }}
        QPushButton[flat="true"]:pressed {{
            background: {a}32;
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
        QToolButton:hover {{ background: {a}22; color: {at}; }}
        QToolButton:checked {{ background: {a}30; color: {at}; font-weight: 600; }}

        QLineEdit, QTextEdit, QPlainTextEdit {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.08),
                stop:1 rgba(255,255,255,0.04));
            color: {t};
            border: 1.5px solid rgba(255,255,255,0.06);
            border-radius: 10px; padding: 9px 14px; font-size: 13px;
            selection-background-color: {a}40;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1.5px solid {a};
            background: rgba(255,255,255,0.10);
        }}
        QLineEdit:disabled, QTextEdit:disabled {{
            background: rgba(28,28,30,0.5); color: #636366;
        }}

        QComboBox {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.08),
                stop:1 rgba(255,255,255,0.04));
            color: {t};
            border: 1.5px solid rgba(255,255,255,0.06); border-radius: 10px;
            padding: 8px 14px; font-size: 13px; min-height: 18px;
        }}
        QComboBox:hover, QComboBox:focus {{ border: 1.5px solid {a}; }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: top right;
            width: 30px; border: none; border-left: 1px solid rgba(255,255,255,0.06);
            border-top-right-radius: 10px; border-bottom-right-radius: 10px;
        }}
        QComboBox QAbstractItemView {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(28,28,30,0.97),
                stop:1 rgba(28,28,30,0.92));
            color: {t};
            border: 1px solid rgba(255,255,255,0.06); border-radius: 10px;
            selection-background-color: {a}30;
            selection-color: {t}; outline: none; padding: 4px;
        }}

        QCheckBox, QRadioButton {{
            spacing: 8px; color: {t}; font-size: 13px;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 20px; height: 20px; border-radius: 5px;
            border: 1.5px solid #636366;
            background: rgba(255,255,255,0.06);
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background: {a}; border: 1.5px solid {a};
        }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border: 1.5px solid {a};
        }}
        QRadioButton::indicator {{ border-radius: 11px; }}

        QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.08),
                stop:1 rgba(255,255,255,0.04));
            color: {t};
            border: 1.5px solid rgba(255,255,255,0.06); border-radius: 10px;
            padding: 8px 14px; font-size: 13px; min-height: 18px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{ border: 1.5px solid {a}; }}

        QTableWidget {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.06),
                stop:1 rgba(255,255,255,0.03));
            color: {t};
            border: 1px solid rgba(255,255,255,0.06); border-radius: 14px;
            gridline-color: rgba(255,255,255,0.03);
            selection-background-color: {a}; selection-color: #FFFFFF;
            font-size: 13px; alternate-background-color: rgba(255,255,255,0.02);
        }}
        QTableWidget::item {{
            padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,0.03);
            min-height: 24px; color: {t};
        }}
        QTableWidget::item:hover {{ background: {a}25; }}
        QTableWidget::item:selected {{ background: {a}; color: #FFFFFF; }}
        QTableWidget::item:selected:!active {{ background: {a}BB; color: #FFFFFF; }}
        QHeaderView::section {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.04),
                stop:1 rgba(255,255,255,0.02));
            color: {s}; font-weight: 600;
            font-size: 12px; padding: 11px 14px; border: none;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            border-right: 1px solid rgba(255,255,255,0.02); min-height: 26px;
        }}
        QHeaderView::section:last {{ border-right: none; }}
        QHeaderView::section:hover {{ background: rgba(255,255,255,0.06); color: {t}; }}
        QHeaderView::section:active {{ background: {a}20; color: {t}; }}

        QTabWidget::pane {{ border: none; background: transparent; }}
        QTabBar::tab {{
            background: transparent; color: {s}; font-size: 13px;
            font-weight: 500; padding: 12px 24px; border: none;
            border-bottom: 2.5px solid transparent; min-height: 20px;
        }}
        QTabBar::tab:hover {{
            color: {t}; background: rgba(255,255,255,0.06);
            border-radius: 10px 10px 0 0;
        }}
        QTabBar::tab:selected {{
            color: {at}; border-bottom: 2.5px solid {a};
        }}

        QScrollBar:vertical {{ background: transparent; width: 6px; border-radius: 3px; }}
        QScrollBar::handle:vertical {{ background: rgba(72,72,74,0.7); border-radius: 3px; min-height: 30px; }}
        QScrollBar::handle:vertical:hover {{ background: rgba(99,99,102,0.8); }}
        QScrollBar:horizontal {{ background: transparent; height: 6px; border-radius: 3px; }}
        QScrollBar::handle:horizontal {{ background: rgba(72,72,74,0.7); border-radius: 3px; min-width: 30px; }}
        QScrollBar::handle:horizontal:hover {{ background: rgba(99,99,102,0.8); }}

        QMenu {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(28,28,30,0.96),
                stop:1 rgba(28,28,30,0.90));
            color: {t}; border: 1px solid rgba(255,255,255,0.06);
            border-radius: 14px; padding: 6px;
        }}
        QMenu::item {{ padding: 9px 36px 9px 18px; border-radius: 6px; font-size: 13px; }}
        QMenu::item:selected {{ background: {a}28; color: {at}; }}
        QMenu::separator {{ height: 1px; background: rgba(255,255,255,0.06); margin: 4px 12px; }}

        QMenuBar {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(28,28,30,0.92),
                stop:1 rgba(28,28,30,0.85));
            color: {t}; border-bottom: 1px solid rgba(255,255,255,0.04); padding: 2px;
        }}
        QMenuBar::item {{ padding: 7px 14px; border-radius: 6px; }}
        QMenuBar::item:selected {{ background: {a}22; }}

        QToolBar {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(28,28,30,0.92),
                stop:1 rgba(28,28,30,0.85));
            border: none; border-bottom: 1px solid rgba(255,255,255,0.03);
            padding: 4px 8px; spacing: 2px;
        }}

        QStatusBar {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(28,28,30,0.92),
                stop:1 rgba(28,28,30,0.85));
            color: {s}; font-size: 12px;
            border-top: 1px solid rgba(255,255,255,0.03); padding: 3px 12px;
        }}

        QGroupBox {{
            font-weight: 600; font-size: 14px; color: {t};
            border: 1px solid rgba(255,255,255,0.06); border-radius: 14px;
            margin-top: 18px; padding: 18px 14px 14px 14px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 4px 12px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.10),
                stop:1 rgba(255,255,255,0.05));
            border-radius: 6px; left: 14px;
        }}

        QListWidget {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.06),
                stop:1 rgba(255,255,255,0.03));
            color: {t}; border: 1px solid rgba(255,255,255,0.06);
            border-radius: 12px; padding: 4px; outline: none;
        }}
        QListWidget::item {{ padding: 9px 14px; border-radius: 6px; margin: 2px 0; }}
        QListWidget::item:selected {{ background: {a}30; color: {t}; }}
        QListWidget::item:hover {{ background: {a}15; }}

        QScrollArea {{ border: none; background: transparent; }}
        QSplitter::handle {{ background: rgba(255,255,255,0.06); width: 1px; }}

        QToolTip {{
            background: rgba(0,0,0,0.88); color: {t};
            font-size: 12px; border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px; padding: 8px 14px;
        }}

        QMessageBox {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(28,28,30,0.96),
                stop:1 rgba(28,28,30,0.90));
        }}
        QMessageBox QLabel {{ color: {t}; font-size: 13px; }}

        QProgressBar {{
            background: rgba(255,255,255,0.06); border: none;
            border-radius: 4px; height: 6px;
            text-align: center; font-size: 10px;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {a}, stop:1 {a}AA);
            border-radius: 4px;
        }}

        QTreeWidget {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.06),
                stop:1 rgba(255,255,255,0.03));
            color: {t};
            border: 1px solid rgba(255,255,255,0.06); border-radius: 12px;
            outline: none; alternate-background-color: rgba(255,255,255,0.02);
        }}
        QTreeWidget::item {{ padding: 7px 10px; border-radius: 5px; }}
        QTreeWidget::item:selected {{ background: {a}30; color: {t}; }}
        QTreeWidget::item:hover {{ background: {a}15; }}

        QTextBrowser {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.06),
                stop:1 rgba(255,255,255,0.03));
            color: {t};
            border: 1px solid rgba(255,255,255,0.06); border-radius: 12px;
            padding: 10px;
        }}

        QDialog {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0D0D0D, stop:0.5 #1A1A1E, stop:1 #0F0F12);
        }}
        """
