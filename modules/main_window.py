import json, os, sys, subprocess, webbrowser, shutil, tempfile, zipfile
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from PyQt5.QtCore import (Qt, QTimer, QPoint, QEvent, QSize, QUrl,
    QObject, QProcess, QPropertyAnimation, QEasingCurve)
from PyQt5.QtGui import (QColor, QFont, QIcon, QPixmap, QPalette,
    QDesktopServices, QCursor, QPainter,
    QLinearGradient, QBrush, QPen, QKeySequence)
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTabWidget, QScrollArea, QMessageBox, QInputDialog,
    QFileDialog, QDialog, QTreeWidget, QTreeWidgetItem, QSplitter,
    QToolButton, QMenu, QAction, QDialogButtonBox, QSystemTrayIcon,
    QSizePolicy, QGraphicsDropShadowEffect, QStackedWidget,
    QListWidget, QListWidgetItem, QCheckBox, QSpinBox, QSlider,
    QButtonGroup, QRadioButton, QGridLayout, QFormLayout, QTextEdit,
    QTextBrowser, QHeaderView, QAbstractItemView, QTableWidget,
    QTableWidgetItem, QGroupBox, QProgressBar, QStatusBar,
    QDockWidget, QMenuBar, QToolBar, QShortcut)

from app_core.config import RUNTIME_PATHS, AppConfig
from app_core.i18n import I18n
from app_core.theme_engine import ThemeEngine
from app_core.utils import ACCENT_COLORS, fade_in_widget
from services.database import DatabaseManager
from services.security import SecurityEngine
from services.workerpool import AsyncPool
from services.telegram_bot import TelegramBot
from widgets.toast import ToastNotification
from modules.login import LoginDialog
from modules.dashboard import DashboardTab
from modules.employees import EmployeeTableWidget, EmployeeEditDialog
from modules.violations import ViolationsTableWidget, ViolationEditDialog
from modules.violations_type import ViolationTypeDialog
from modules.companies import CompaniesTab
from modules.ledger import CustomLedgerTableWidget, CustomLedgerEditDialog
from modules.textbook import TextbookDialog, TextbookLineEdit
from modules.statistics import StatisticsTab
from modules.notes import NotesDialog
from modules.reminders import RemindersDialog, ReminderEngine, ExpiringRemindersTab, ReminderFloatingDialog
from modules.print_engine import PrintEngine
from modules.data_dialogs import ImportDialog, ExportDialog, GlobalSearchDialog, ReportDialog, QuickReportDialog
from modules.ai import AIChatDialog, AIChatInlineWidget, AIEngine
from modules.ai_insights import AIInsightsWidget
from modules.settings import SettingsDialog, UsersDialog, AuditTab, HotkeyManager
from modules.tools import FineKinneyCalculator, TextbookManagerDialog, PrintDialog
from modules.print_editor import PrintTemplateEditor


class MainWindow(QMainWindow):
    def __init__(self, user: Optional[Dict[str, Any]] = None) -> None:
        super().__init__()
        self.db = DatabaseManager()
        self._user = user or {}
        self._build_ui()
        self._setup_toolbar()
        self._load_settings()
        self._populate_dashboard()
        self._init_auto_save()
        self._hotkeys = HotkeyManager(self)
        self._telegram_bot = TelegramBot()
        self._telegram_bot.start()

    def _btn_text(self, key: str, fallback: str) -> str:
        custom = self.db.get_setting(key, "")
        return custom if custom else fallback

    def closeEvent(self, event: Any) -> None:
        try:
            self._auto_save_timer.stop()
        except Exception:
            pass
        try:
            self._tab_widget.blockSignals(True)
        except Exception:
            pass
        try:
            self._telegram_bot.stop()
        except Exception:
            pass
        event.accept()

    def _build_ui(self) -> None:
        self.setWindowTitle(I18n._("app.name"))
        self.setMinimumSize(1200, 750)
        self.resize(1400, 850)
        center = QApplication.primaryScreen().availableGeometry().center()
        self.move(center.x() - 700, center.y() - 425)

        self._tab_widget = QTabWidget()
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.setMovable(True)
        self._tab_widget.setTabsClosable(False)
        self._tab_widget.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self._tab_widget.tabBar().customContextMenuRequested.connect(
            self._on_tab_context_menu)
        self.setCentralWidget(self._tab_widget)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status_label = QLabel()
        self._status.addPermanentWidget(self._status_label)

    def _setup_toolbar(self) -> None:
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(14, 14))
        tb.setStyleSheet("QToolBar { spacing: 1px; padding: 2px 4px; }")
        self.addToolBar(tb)

        def tb_btn(icon: str, tip: str, slot) -> QToolButton:
            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            btn.setStyleSheet("QToolButton { padding: 4px 6px; font-size: 13px; min-width: 22px; }")
            tb.addWidget(btn)
            return btn

        self._theme_btn = tb_btn("☀" if ThemeEngine._current_theme == "light" else "☾",
               I18n._("settings.theme"), self._toggle_theme)
        self._lang_btn = tb_btn("RU" if I18n.current() == "ru" else "EN",
               I18n._("settings.language"), self._toggle_lang)
        tb.addSeparator()
        user_name = self._user.get("username", "?")
        role = self._user.get("role", "")
        ubtn = tb_btn(f"👤{user_name}", f"{I18n._('user.role')}: {role}", lambda: None)
        ubtn.setEnabled(False)
        tb_btn("🚪", I18n._("login.logout"), self._on_logout)
        tb_btn("⚙", I18n._("common.settings"), self._open_settings)
        tb_btn("👥", I18n._("user.title"), self._open_users)
        tb.addSeparator()
        tb_btn("📥", I18n._("import.title"), self._open_import_dialog)
        tb_btn("📜", I18n._("audit.export_title"), self._export_audit_log)
        tb_btn("📝", I18n._("template.title"), self._open_print_templates)
        tb.addSeparator()
        tb_btn("📖", I18n._("common.notes"), self._open_global_notes)
        tb_btn("📚", I18n._("knowledge.title"), self._open_knowledge)
        tb_btn("✏️", I18n._("textbook.title"), self._open_textbook)
        tb_btn("📊", I18n._("analytics.title"), self._open_analytics_menu)
        tb_btn("📋", I18n._("report.global_title"), self._generate_global_report)
        tb_btn("⚠️", I18n._("risk.title"), self._open_risk_calc)
        tb.addSeparator()
        tb_btn("🤖", I18n._("ai.title"), self._open_ai_chat)
        tb_btn("🩺", I18n._("ai.diagnostics"), self._open_ai_diagnostics)
        tb.addSeparator()
        tb_btn("💾", I18n._("common.backup"), self._open_backup_dialog)
        tb_btn("🖨", I18n._("print.any_table"), self._open_print_dialog)
        tb_btn("❓", I18n._("help.title"), self._open_help)
        tb_btn("ℹ️", I18n._("common.about"), self._show_about)
        self._global_search = QLineEdit()
        self._global_search.setPlaceholderText(I18n._("common.global_search"))
        self._global_search.setClearButtonEnabled(True)
        self._global_search.setMinimumWidth(120)
        self._global_search.setMaximumWidth(160)
        self._global_search.returnPressed.connect(self._on_global_search)
        tb.addWidget(self._global_search)

    def _load_settings(self) -> None:
        self._tabs_data: Dict[str, Tuple[int, QWidget]] = {}
        self._tab_widget.clear()
        self.dashboard_tab = DashboardTab()

        uid = self._user.get("id", 0)

        self._employees_tab = EmployeeTableWidget(user_id=uid)
        self._violations_tab = ViolationsTableWidget(user_id=uid)
        self._companies_tab = CompaniesTab()
        self._custom_ledger_tab = CustomLedgerTableWidget(user_id=uid)
        self._statistics_tab = StatisticsTab()
        self._audit_tab = AuditTab()

        self._ai_tab = AIChatInlineWidget()
        self._ai_insights_tab = AIInsightsWidget()

        self._reminders_tab = ExpiringRemindersTab()

        tab_defs = [
            ("tab.dashboard", self.dashboard_tab),
            ("tab.employees", self._employees_tab),
            ("tab.violations", self._violations_tab),
            ("tab.companies", self._companies_tab),
            ("tab.custom_ledger", self._custom_ledger_tab),
            ("tab.statistics", self._statistics_tab),
            ("tab.audit", self._audit_tab),
            ("tab.reminders", self._reminders_tab),
            ("tab.ai", self._ai_tab),
            ("tab.ai_insights", self._ai_insights_tab),
        ]
        for key, widget in tab_defs:
            label = self.db.get_setting(f"tab_{key.split('.')[1]}", I18n._(key))
            idx = self._tab_widget.addTab(widget, label)
            self._tabs_data[key] = (idx, widget)

        self._tab_widget.tabBar().installEventFilter(self)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)
        self._update_tab_badges()
        self._update_status()

        self._tab_widget.tabBar().setExpanding(True)
        self._tab_widget.tabBar().setUsesScrollButtons(True)
        try:
            self._tab_widget.tabBar().setElideMode(Qt.ElideRight)
        except Exception:
            pass

    def _show_startup_reminders(self) -> None:
        try:
            tab = getattr(self, "_reminders_tab", None)
            if tab and tab.has_expiring():
                dlg = ReminderFloatingDialog(self)
                dlg.setWindowOpacity(0.0)
                dlg.show()
                anim = QPropertyAnimation(dlg, b"windowOpacity")
                anim.setDuration(400)
                anim.setStartValue(0.0)
                anim.setEndValue(1.0)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.start()
        except Exception:
            pass

    def _populate_dashboard(self) -> None:
        self.dashboard_tab._refresh()

    def _init_auto_save(self) -> None:
        try:
            interval = int(self.db.get_setting("auto_save_interval", "60"))
        except Exception:
            interval = 60
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(lambda: self.db.create_backup())
        self._auto_save_timer.start(max(10, interval) * 1000)

        self._reminder_refresh_timer = QTimer(self)
        self._reminder_refresh_timer.timeout.connect(self._refresh_reminders)
        self._reminder_refresh_timer.start(120000)

    def _refresh_reminders(self) -> None:
        try:
            if hasattr(self, '_reminders_tab'):
                self._reminders_tab._load_data()
                self._update_tab_badges()
        except Exception:
            pass

    def _refresh_current_tab(self) -> None:
        idx = self._tab_widget.currentIndex()
        if not hasattr(self, '_tabs_data'):
            return
        for key, (i, widget) in self._tabs_data.items():
            if i == idx:
                name = key.split(".")[1]
                if name == "dashboard":
                    self.dashboard_tab._refresh()
                elif hasattr(self, f"_{name}_tab"):
                    t = getattr(self, f"_{name}_tab")
                    if hasattr(t, "_load_data"):
                        t._load_data()
                    elif hasattr(t, "_refresh"):
                        t._refresh()
                break

    def _update_tab_badges(self) -> None:
        if not hasattr(self, '_tabs_data'):
            return
        try:
            emp_count = len(self.db.get_json_records("employees"))
            viol_count = len(self.db.get_json_records("violations"))
            remind_count = self._reminders_tab.get_expiring_count() if hasattr(self, '_reminders_tab') else 0
        except Exception:
            return
        for key, (idx, widget) in self._tabs_data.items():
            label = self.db.get_setting(f"tab_{key.split('.')[1]}", I18n._(key))
            if key == "tab.employees" and emp_count:
                self._tab_widget.setTabText(idx, f"{label} ({emp_count})")
            elif key == "tab.violations" and viol_count:
                self._tab_widget.setTabText(idx, f"{label} ({viol_count})")
            elif key == "tab.reminders" and remind_count:
                self._tab_widget.setTabText(idx, f"{label} ({remind_count})")
            else:
                self._tab_widget.setTabText(idx, label)

    def _tab_name_by_index(self) -> Dict[int, str]:
        if not hasattr(self, '_tabs_data'):
            return {}
        return {idx: key.split(".")[1] for key, (idx, _) in self._tabs_data.items()}

    def open_reminder_target(self, item: Dict[str, Any]) -> None:
        table = str(item.get("_table", "")).strip()
        record_id = item.get("_record_id")
        if table == "employees" and hasattr(self, "_employees_tab"):
            self._tab_widget.setCurrentIndex(self._tabs_data["tab.employees"][0])
            self._employees_tab.focus_record(record_id)
        elif table == "violations" and hasattr(self, "_violations_tab"):
            self._tab_widget.setCurrentIndex(self._tabs_data["tab.violations"][0])
            self._violations_tab.focus_record(record_id)
        elif table == "custom_ledger" and hasattr(self, "_custom_ledger_tab"):
            self._tab_widget.setCurrentIndex(self._tabs_data["tab.custom_ledger"][0])
            self._custom_ledger_tab.focus_record(record_id)
        elif table == "reminders":
            RemindersDialog(self).exec_()

    def _open_global_search(self) -> None:
        GlobalSearchDialog(self).exec_()

    def _on_global_search(self) -> None:
        text = self._global_search.text().strip()
        if not text:
            return
        results = []
        db = DatabaseManager()
        text_lower = text.lower()
        seen = set()
        for table, label_key in [("employees", "tab.employees"),
                                  ("violations", "tab.violations"),
                                  ("custom_ledger", "tab.custom_ledger"),
                                  ("companies", "company.title")]:
            for rec in db.get_json_records(table):
                dj = rec.get("data_json", {})
                rid = rec.get("id", 0)
                for k, v in dj.items():
                    if text_lower in str(v).lower():
                        key = (table, rid)
                        if key not in seen:
                            seen.add(key)
                            results.append((table, label_key, rid, k, str(v)[:80]))
                            break
        for note in db.get_notes():
            if text_lower in note.get("text", "").lower():
                results.append(("notes", "common.notes", note.get("id", 0),
                                I18n._("common.notes"), note.get("text", "")[:80]))
        results.sort(key=lambda r: r[4])
        self._show_search_results(text, results)

    def _show_search_results(self, query: str, results: list) -> None:
        if not results:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{I18n._('common.search')}: {query}")
        dlg.setMinimumSize(500, 400)
        dlg.resize(600, 500)
        lay = QVBoxLayout(dlg)
        tree = QTreeWidget()
        tree.setHeaderLabels([I18n._("common.table"), I18n._("common.field"), I18n._("common.value")])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.itemDoubleClicked.connect(lambda item, _: self._navigate_to_record(item))
        for table, label_key, rid, field, value in results:
            QTreeWidgetItem(tree, [I18n._(label_key), field, value]).setData(
                0, Qt.UserRole, (table, rid))
        lay.addWidget(tree)
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)
        dlg.exec_()

    def _navigate_to_record(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        table, rid = data
        tab_key = {"employees": "tab.employees", "violations": "tab.violations",
                   "custom_ledger": "tab.custom_ledger", "notes": "tab.notes",
                   "companies": "tab.companies"}.get(table)
        if tab_key and tab_key in self._tabs_data:
            idx, widget = self._tabs_data[tab_key]
            self._tab_widget.setCurrentIndex(idx)
            if hasattr(widget, 'focus_record'):
                widget.focus_record(rid)
            elif hasattr(widget, 'focus_note'):
                widget.focus_note(rid)

    def _open_ai_chat(self) -> None:
        db = DatabaseManager()
        key = db.get_ai_setting("api_key", "")
        if not key:
            QMessageBox.information(self, I18n._("ai.title"),
                                    I18n._("ai.no_key"))
        dlg = AIChatDialog(self)
        dlg.exec_()
        self._refresh_current_tab()

    def _open_global_notes(self) -> None:
        NotesDialog(entity_type="global", entity_id=0,
                    entity_name=I18n._("tab.dashboard"), parent=self).exec_()

    def _open_import_dialog(self) -> None:
        dlg = ImportDialog("", self)
        if dlg.exec_() == QDialog.Accepted:
            for tab_name in ("employees", "violations", "custom_ledger"):
                widget = getattr(self, f"_{tab_name}_tab", None)
                if widget and hasattr(widget, "_load_data"):
                    widget._load_data()

    def _open_print_templates(self) -> None:
        dlg = PrintTemplateEditor(self)
        dlg.exec_()

    def _open_help(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(I18n._("help.title"))
        dlg.setMinimumSize(700, 600)
        dlg.resize(750, 650)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        a = ThemeEngine._current_accent
        at = ThemeEngine._contrast_accent(a)
        is_dark = ThemeEngine._current_theme == "dark"
        bg = "#1C1C1E" if is_dark else "#FFFFFF"
        text = "#F5F5F7" if is_dark else "#1C1C1E"
        sec_text = "#98989D" if is_dark else "#6C6C70"
        card_bg = "rgba(44,44,46,0.85)" if is_dark else "rgba(255,255,255,0.7)"
        card_border = "rgba(255,255,255,0.08)" if is_dark else "rgba(0,0,0,0.04)"
        div_border = "#3A3A3C" if is_dark else "#E5E5EA"
        browser.setHtml(f"""
        <style>
            body {{ font-family: -apple-system, 'Segoe UI', Arial, sans-serif; font-size: 13px; line-height: 1.7; color: {text}; margin: 0; padding: 0; }}
            h2 {{ font-size: 24px; font-weight: 700; color: {text}; margin: 0 0 4px 0; letter-spacing: -0.5px; }}
            .subtitle {{ color: {sec_text}; font-size: 13px; margin: 0 0 16px 0; }}
            h3 {{ font-size: 15px; font-weight: 600; color: {text}; margin: 20px 0 8px 0; padding: 0 0 6px 0; border-bottom: 1.5px solid {div_border}; }}
            .section {{ background: {card_bg}; border-radius: 10px; padding: 12px 16px; margin: 8px 0; border: 1px solid {card_border}; }}
            .section p {{ margin: 4px 0; color: {text}; }}
            table.shortcuts {{ border-collapse: collapse; width: 100%; }}
            table.shortcuts td {{ padding: 5px 10px; font-size: 13px; border-bottom: 1px solid {div_border}; }}
            table.shortcuts td:first-child {{ color: {at}; font-weight: 600; white-space: nowrap; width: 1%; }}
            table.shortcuts td:last-child {{ color: {text}; }}
            ul {{ margin: 4px 0; padding-left: 20px; }}
            li {{ margin: 3px 0; color: {text}; line-height: 1.6; }}
            .tag {{ display: inline-block; background: {a}22; color: {at}; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
        </style>
        <h2>{I18n._('app.name')}</h2>
        <p class="subtitle">{I18n._('help.version')} {AppConfig.APP_VERSION} &middot; {I18n._('app.copyright')}</p>

        <div class="section">
        <h3>{I18n._('help.shortcuts')}</h3>
        <table class="shortcuts">
        <tr><td><b>Ctrl+&uarr;/&darr;</b></td><td>{I18n._('help.nav_table')}</td></tr>
        <tr><td><b>Ctrl+F</b></td><td>{I18n._('help.search')}</td></tr>
        <tr><td><b>Ctrl+N</b></td><td>{I18n._('help.add_record')}</td></tr>
        <tr><td><b>Ctrl+E</b></td><td>{I18n._('help.export')}</td></tr>
        <tr><td><b>Ctrl+P</b></td><td>{I18n._('help.print')}</td></tr>
        <tr><td><b>Ctrl+S</b></td><td>{I18n._('help.save')} / backup</td></tr>
        <tr><td><b>Delete</b></td><td>{I18n._('help.delete')}</td></tr>
        <tr><td><b>Alt+1..9</b></td><td>{I18n._('help.tabs')}</td></tr>
        <tr><td><b>F5</b></td><td>{I18n._('common.refresh')}</td></tr>
        <tr><td><b>{I18n._('help.click_column')}</b></td><td>{I18n._('help.sort')}</td></tr>
        <tr><td><b>{I18n._('help.right_click_column')}</b></td><td>{I18n._('help.column_menu')}</td></tr>
        <tr><td><b>{I18n._('help.right_click_row')}</b></td><td>{I18n._('help.row_menu')}</td></tr>
        </table>
        </div>

        <div class="section">
        <h3>{I18n._('help.toolbar')}</h3>
        <p>{I18n._('help.toolbar_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.tabs')}</h3>
        <p>{I18n._('help.tabs_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.tables')}</h3>
        <p>{I18n._('help.tables_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.dashboard')}</h3>
        <p>{I18n._('help.dashboard_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('common.notes')}</h3>
        <p>{I18n._('help.notes_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.photos')}</h3>
        <p>{I18n._('help.photos_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('import.title')} / {I18n._('export.title')}</h3>
        <p><b>{I18n._('import.title')}:</b> {I18n._('help.import_desc')}</p>
        <p><b>{I18n._('export.title')}:</b> {I18n._('help.export_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.print_templates')}</h3>
        <p>{I18n._('help.print_templates_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('ai.title')}</h3>
        <p>{I18n._('help.ai_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('analytics.title')}</h3>
        <p>{I18n._('help.analytics_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('reminder.all')}</h3>
        <p>{I18n._('help.reminders_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.reports')} &amp; {I18n._('common.backup')}</h3>
        <p><b>{I18n._('help.reports')}:</b> {I18n._('help.reports_desc')}</p>
        <p><b>{I18n._('common.backup')}:</b> {I18n._('help.backup_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.security')}</h3>
        <p>{I18n._('help.security_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('common.settings')}</h3>
        <p>{I18n._('help.settings_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('textbook.title')}</h3>
        <p>{I18n._('help.textbook_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('risk.title')}</h3>
        <p>{I18n._('help.risk_calc_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.column_customization')}</h3>
        <p>{I18n._('help.column_customization_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.color_indicators')}</h3>
        <p>{I18n._('help.color_indicators_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.global_search')}</h3>
        <p>{I18n._('help.global_search_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.duplicate_merge')}</h3>
        <p>{I18n._('help.duplicate_merge_desc')}</p>
        </div>

        <div class="section">
        <h3>{I18n._('help.tips')}</h3>
        <pre style="font-family: -apple-system, 'Segoe UI', Arial, sans-serif; font-size: 13px; color: {text}; margin: 0; line-height: 1.7;">{I18n._('help.tips_list')}</pre>
        </div>
        """)
        layout.addWidget(browser)

        close_btn = QPushButton(I18n._("common.ok"))
        close_btn.clicked.connect(dlg.accept)
        close_btn.setFixedWidth(100)
        layout.addWidget(close_btn, 0, Qt.AlignCenter)
        fade_in_widget(dlg, 250)
        dlg.exec_()

    def _open_settings(self) -> None:
        SettingsDialog(self).exec_()

    def _open_users(self) -> None:
        UsersDialog(self).exec_()

    def _on_tab_changed(self, index: int) -> None:
        self._update_status()
        try:
            self._refresh_current_tab()
        except Exception:
            pass

    def _update_status(self) -> None:
        idx = self._tab_widget.currentIndex()
        if idx >= 0:
            tab_text = self._tab_widget.tabText(idx)
            user_name = self._user.get("username", "?")
            self._status_label.setText(
                f"👤 {user_name}  |  📋 {tab_text}")

    # -----------------------------------------------------------------------
    # Tab Renaming (double-click)
    # -----------------------------------------------------------------------

    def eventFilter(self, obj: QObject, event: Any) -> bool:
        if (obj == self._tab_widget.tabBar() and
                event.type() == event.MouseButtonDblClick):
            idx = self._tab_widget.tabBar().tabAt(event.pos())
            if idx >= 0:
                self._rename_tab(idx)
            return True
        return super().eventFilter(obj, event)

    def _rename_tab(self, index: int) -> None:
        old_name = self._tab_widget.tabText(index)
        new_name, ok = QInputDialog.getText(
            self, I18n._("common.rename"), "",
            text=old_name)
        if ok and new_name and new_name != old_name:
            self._tab_widget.setTabText(index, new_name)
            tab_key = self._get_tab_key(index)
            if tab_key:
                self.db.upsert_setting(f"tab_{tab_key}", new_name)
                self.db.log_event(f"Tab renamed: {old_name} -> {new_name}", "INFO")
                self._update_status()

    def _get_tab_key(self, index: int) -> Optional[str]:
        mapping = [
            "dashboard", "employees", "violations", "companies",
            "custom_ledger", "statistics", "audit", "reminders", "ai",
        ]
        return mapping[index] if 0 <= index < len(mapping) else None

    def _on_tab_context_menu(self, pos: QPoint) -> None:
        idx = self._tab_widget.tabBar().tabAt(pos)
        if idx < 0:
            return
        menu = QMenu(self)
        rename_action = menu.addAction(I18n._("column.rename"))
        action = menu.exec_(self._tab_widget.tabBar().mapToGlobal(pos))
        if action == rename_action:
            self._rename_tab(idx)

    # -----------------------------------------------------------------------
    # Theme / Language Toggle
    # -----------------------------------------------------------------------

    def _toggle_theme(self) -> None:
        new_theme = "dark" if ThemeEngine._current_theme == "light" else "light"
        self.db.upsert_setting("theme", new_theme)
        self._restart_app()

    def _restart_app(self) -> None:
        try:
            import subprocess, os
            script = getattr(sys, '_MEIPASS', __file__)
            exe = sys.executable if not getattr(sys, 'frozen', False) else script
            subprocess.Popen([exe, script] if not getattr(sys, 'frozen', False) else [script])
        except Exception:
            try:
                QProcess.startDetached(sys.executable, [__file__])
            except Exception:
                pass
        self.close()
        QApplication.quit()

    def _toggle_lang(self) -> None:
        new_lang = "en" if I18n.current() == "ru" else "ru"
        I18n.set_language(new_lang)
        self.db.upsert_setting("app_language", new_lang)
        default_text = "RU" if new_lang == "ru" else "EN"
        self._lang_btn.setText(default_text)
        self._retranslate_ui()
        ToastNotification.notify(
            I18n._("settings.saved"), "success", 3000)

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(I18n._("app.name"))
        for i in range(self._tab_widget.count()):
            key = self._get_tab_key(i)
            if key:
                saved = self.db.get_setting(f"tab_{key}", "")
                self._tab_widget.setTabText(
                    i, saved if saved else I18n._(f"tab.{key}"))
        def tooltip(key: str, fallback: str) -> str:
            return self.db.get_setting(f"tip_{key}", fallback)
        self._theme_btn.setToolTip(tooltip("theme", I18n._("settings.theme")))
        self._lang_btn.setToolTip(tooltip("lang", I18n._("settings.language")))
        self._update_status()

    # -----------------------------------------------------------------------
    # Block 4 ported utilities (from 9.5.py reference)
    # -----------------------------------------------------------------------

    def _open_textbook(self) -> None:
        TextbookManagerDialog(self).exec_()

    def _open_risk_calc(self) -> None:
        FineKinneyCalculator(self).exec_()

    def _open_print_dialog(self) -> None:
        dlg = PrintDialog(self)
        dlg.exec_()

    def _open_analytics_menu(self) -> None:
        menu = QMenu(self)
        cat_action = menu.addAction(I18n._("analytics.category"))
        contr_action = menu.addAction(I18n._("analytics.contractor"))
        action = menu.exec_(QCursor.pos())
        if action == cat_action:
            self._global_category_analytics()
        elif action == contr_action:
            self._global_contractor_analytics()

    def _open_backup_dialog(self) -> None:
        self._global_restore_from_backup()

    def _open_knowledge(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(I18n._("knowledge.title"))
        dlg.setMinimumSize(600, 420)
        lay = QVBoxLayout(dlg)
        editor = QTextEdit()
        kf = os.path.join(RUNTIME_PATHS.app_dir, AppConfig.DATA_DIR, "knowledge.txt")
        if os.path.exists(kf):
            try:
                with open(kf, "r", encoding="utf-8") as f:
                    editor.setText(f.read())
            except Exception:
                pass
        lay.addWidget(editor)
        save_btn = QPushButton(I18n._("knowledge.save"))
        def _save_knowledge():
            try:
                with open(kf, "w", encoding="utf-8") as f:
                    f.write(editor.toPlainText())
                dlg.accept()
            except Exception as ex:
                QMessageBox.critical(self, I18n._("common.error"), str(ex))
        save_btn.clicked.connect(_save_knowledge)
        lay.addWidget(save_btn)
        dlg.exec_()

    def _export_audit_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, I18n._("audit.export_title"),
            f"suot_audit_{datetime.now().strftime('%Y%m%d')}.log",
            "Log Files (*.log)")
        if not path:
            return
        try:
            rows = self.db.fetch_all(
                "SELECT timestamp, event FROM audit_log ORDER BY id ASC")
            lines = [f"[{r['timestamp']}] {r['event']}" for r in rows]
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            ToastNotification.notify(
                I18n._("audit.export_success"), "success", 3000)
        except Exception as ex:
            QMessageBox.critical(self, I18n._("common.error"), str(ex))

        except Exception as ex:
            QMessageBox.critical(self, I18n._("common.error"), str(ex))


    def _open_ai_diagnostics(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(I18n._("ai.diagnostics"))
        dlg.setMinimumSize(650, 500)
        lay = QVBoxLayout(dlg)
        
        heading = QLabel(I18n._("ai.diagnostics"))
        heading.setProperty("heading", True)
        lay.addWidget(heading)
        
        config_frame = QGroupBox(I18n._("ai.current_config"))
        config_lay = QFormLayout(config_frame)
        
        db = DatabaseManager()
        provider = db.get_ai_setting("provider", "openai")
        api_url = db.get_ai_setting("api_url", "")
        model = db.get_ai_setting("model", "")
        mode = db.get_ai_setting("mode", "chat")
        temperature = db.get_ai_setting("temperature", "0.7")
        
        config_lay.addRow(I18n._("ai.provider_label") + ":", QLabel(provider))
        config_lay.addRow(I18n._("ai.url_label") + ":", QLabel(api_url or "—"))
        config_lay.addRow(I18n._("ai.model_label") + ":", QLabel(model or "—"))
        config_lay.addRow(I18n._("ai.mode_label") + ":", QLabel(mode))
        config_lay.addRow(I18n._("ai.temp_label") + ":", QLabel(str(temperature)))
        
        lay.addWidget(config_frame)
        
        test_btn = QPushButton(I18n._("ai.test_connection"))
        test_btn.setProperty("success", True)
        result_label = QLabel()
        result_label.setWordWrap(True)
        
        def run_test():
            test_btn.setEnabled(False)
            test_btn.setText(I18n._("common.loading"))
            QApplication.processEvents()
            try:
                engine = AIEngine()
                test_result = engine.send_request([], "Test connection", "")
                if test_result and not test_result.startswith("Error:") and not test_result.startswith("HTTP Error"):
                    result_label.setText(f"<span style='color: #27AE60;'>{I18n._('ai.connection_ok')}</span>")
                    result_label.setToolTip(test_result[:500])
                else:
                    result_label.setText(f"<span style='color: #E74C3C;'>{I18n._('ai.connection_failed').format(error=test_result or 'Unknown')}</span>")
                    result_label.setToolTip(test_result or "")
            except Exception as ex:
                result_label.setText(f"<span style='color: #E74C3C;'>{I18n._('ai.connection_failed').format(error=str(ex))}</span>")
                result_label.setToolTip(str(ex))
            finally:
                test_btn.setEnabled(True)
                test_btn.setText(I18n._("ai.test_connection"))
        
        test_btn.clicked.connect(run_test)
        lay.addWidget(test_btn)
        lay.addWidget(result_label)
        
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)
        dlg.exec_()

    def _generate_global_report(self) -> None:
        html_path = os.path.abspath(
            os.path.join(AppConfig.DATA_DIR, "global_report.html"))
        word_path = os.path.abspath(
            os.path.join(AppConfig.DATA_DIR, "global_report.doc"))
        stats = self.db.get_statistics()
        status_col = "Статус"
        try:
            records = self.db.get_json_records("violations",
                                               user_id=self._user.get("id", 0))
        except Exception:
            records = []
        active = []
        for rec in records:
            dj = rec.get("data_json", {})
            if dj.get(status_col) in ("Активно", "Active", "Просрочено", "Expired"):
                active.append(dj)

        try:
            emp_records = self.db.get_json_records("employees",
                                                   user_id=self._user.get("id", 0))
        except Exception:
            emp_records = []
        active_emp = sum(1 for r in emp_records
                         if r.get("data_json", {}).get(status_col) in ("Активен", "Active"))

        li = "".join(
            f"<li><b>{v.get('Фирма', 'Контрагент')}:</b> "
            f"{v.get('Описание', 'Замечание по ТБ')}</li>"
            for v in active)
        now_str = datetime.now().strftime('%d.%m.%Y %H:%M')
        html = f"""<html><head><meta charset='utf-8'>
        <style>body{{font-family:Arial;margin:40px;background:#fafafa;}}
        .c{{background:#fff;padding:30px;border-radius:8px;
        box-shadow:0 2px 5px rgba(0,0,0,0.1);}}
        table{{width:100%;border-collapse:collapse;margin:16px 0;}}
        th,td{{border:1px solid #dee2e6;padding:8px 12px;text-align:left;}}
        th{{background:#f8f9fa;}}</style></head>
        <body><div class="c">
        <h2>{I18n._("report.global_title")}</h2>
        <p>{I18n._("common.date")}: {now_str}</p>
        <h3>📊 {I18n._("analytics.title")}</h3>
        <table>
        <tr><th>{I18n._("tab.employees")}</th><td>{stats['employees_total']}</td></tr>
        <tr><th>{I18n._("tab.violations")}</th><td>{stats['violations_total']}</td></tr>
        <tr><th>{I18n._("report.active_employees")}</th><td>{active_emp}</td></tr>
        <tr><th>{I18n._("report.active_violations")}</th><td>{len(active)}</td></tr>
        <tr><th>{I18n._("analytics.total_fines")}</th><td>{stats['fines_total']:,.0f} RUB</td></tr>
        </table>
        <h3>{I18n._("report.active_violations")} ({len(active)}):</h3>
        <ul>{li if li else f"<li>{I18n._('report.none_active')}</li>"}</ul>
        <hr><button onclick="window.print()">{I18n._("common.print")}</button>
        </div></body></html>"""
        try:
            os.makedirs(AppConfig.DATA_DIR, exist_ok=True)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            with open(word_path, "w", encoding="utf-8") as f:
                f.write(html)
            reply = QMessageBox.question(
                self, I18n._("report.global_title"),
                I18n._("report.open_html") + f"\n\n{I18n._('report.word_saved')}",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                webbrowser.open(f"file:///{html_path}")
            ToastNotification.notify(
                I18n._("report.generated_html"), "success", 3000)
        except Exception as ex:
            QMessageBox.critical(self, I18n._("common.error"), str(ex))

    def _global_restore_from_backup(self) -> None:
        bdir = RUNTIME_PATHS.backup_dir
        if not os.path.isdir(bdir):
            QMessageBox.information(self, I18n._("common.backup"),
                                    I18n._("backup.none"))
            return
        files = sorted(
            [f for f in os.listdir(bdir) if f.endswith(".zip")], reverse=True)
        if not files:
            QMessageBox.information(self, I18n._("common.backup"),
                                    I18n._("backup.none"))
            return
        display_names = [f.replace("suot_backup_", "").replace(".zip", "")
                         for f in files]
        chosen_display, ok = QInputDialog.getItem(
            self, I18n._("common.restore"), I18n._("backup.list"),
            display_names, 0, False)
        if ok and chosen_display:
            idx = display_names.index(chosen_display)
            chosen_file = files[idx]
            reply = QMessageBox.question(
                self, I18n._("common.confirm"),
                I18n._("backup.restore_confirm").format(
                    date=chosen_display.replace("_", " ")),
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                try:
                    zip_path = os.path.join(bdir, chosen_file)
                    self.db.conn.close()
                    import zipfile
                    tmp = os.path.join(tempfile.gettempdir(), "suot_restore_tmp.db")
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        zf.extractall(tempfile.gettempdir())
                    db_file_in_zip = "suot_platform.db"
                    extracted = os.path.join(tempfile.gettempdir(), db_file_in_zip)
                    if os.path.exists(extracted):
                        shutil.copy2(extracted, self.db.database_path)
                    self.db = DatabaseManager()
                    self.db.log_event(
                        f"System restored from backup: {chosen_display}", "INFO")
                    ToastNotification.notify(
                        I18n._("backup.restored"), "success", 3000)
                    self._restart_app()
                except Exception as ex:
                    QMessageBox.critical(
                        self, I18n._("common.error"), str(ex))
                except Exception as ex:
                    QMessageBox.critical(
                        self, I18n._("common.error"), str(ex))

    def _global_contractor_analytics(self) -> None:
        try:
            records = self.db.get_json_records("violations")
        except Exception:
            records = []
        org_col = "Фирма"
        status_col = "Статус"
        fine_col = "Штраф"
        stats: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            dj = rec.get("data_json", {})
            org = str(dj.get(org_col, I18n._("common.no_selection")))
            st = str(dj.get(status_col, "Активно"))
            fv = 0.0
            try:
                raw = str(dj.get(fine_col, "0"))
                cleaned = "".join(x for x in raw if x.isdigit() or x == ".")
                if cleaned:
                    fv = float(cleaned)
            except Exception:
                pass
            stats.setdefault(org, {"total": 0, "active": 0, "fines": 0.0})
            stats[org]["total"] += 1
            if st in ("Активно", "Active", "Просрочено", "Expired"):
                stats[org]["active"] += 1
            stats[org]["fines"] += fv
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(I18n._("analytics.contractor"))
        dlg.setMinimumSize(700, 450)
        lay = QVBoxLayout(dlg)
        t = QTableWidget()
        t.setColumnCount(4)
        t.setHorizontalHeaderLabels([
            I18n._("company.name"), I18n._("analytics.total"),
            I18n._("analytics.active"), I18n._("analytics.fines_sum")])
        t.setRowCount(len(stats))
        for r, (org, info) in enumerate(sorted(stats.items())):
            t.setItem(r, 0, QTableWidgetItem(org))
            t.setItem(r, 1, QTableWidgetItem(str(info["total"])))
            t.setItem(r, 2, QTableWidgetItem(str(info["active"])))
            t.setItem(r, 3, QTableWidgetItem(
                f"{info['fines']:,.2f} {I18n._('common.currency')}"))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.verticalHeader().setVisible(False)
        lay.addWidget(t)
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn, 0, Qt.AlignCenter)
        dlg.exec_()

    def _global_category_analytics(self) -> None:
        try:
            records = self.db.get_json_records("violations")
        except Exception:
            records = []
        cat_col = "Категория риска"
        fine_col = "Штраф"
        status_col = "Статус"
        stats: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            dj = rec.get("data_json", {})
            cat = str(dj.get(cat_col, I18n._("common.no_selection")))
            st = str(dj.get(status_col, "Активно"))
            fv = 0.0
            try:
                raw = str(dj.get(fine_col, "0"))
                cleaned = "".join(x for x in raw if x.isdigit() or x == ".")
                if cleaned:
                    fv = float(cleaned)
            except Exception:
                pass
            stats.setdefault(cat, {"total": 0, "resolved": 0, "fines": 0.0})
            stats[cat]["total"] += 1
            if st in ("Устранено", "Resolved"):
                stats[cat]["resolved"] += 1
            stats[cat]["fines"] += fv
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle(I18n._("analytics.category"))
        dlg.setMinimumSize(750, 450)
        lay = QVBoxLayout(dlg)
        t = QTableWidget()
        t.setColumnCount(5)
        t.setHorizontalHeaderLabels([
            I18n._("common.name"), I18n._("analytics.total"),
            I18n._("analytics.resolved"), I18n._("analytics.control_pct"),
            I18n._("analytics.fines_sum")])
        t.setRowCount(len(stats))
        for r, (cat, info) in enumerate(sorted(stats.items())):
            t.setItem(r, 0, QTableWidgetItem(cat))
            t.setItem(r, 1, QTableWidgetItem(str(info["total"])))
            t.setItem(r, 2, QTableWidgetItem(str(info["resolved"])))
            pct = (info["resolved"] / info["total"] * 100) if info["total"] > 0 else 100
            t.setItem(r, 3, QTableWidgetItem(f"{pct:.1f}%"))
            t.setItem(r, 4, QTableWidgetItem(
                f"{info['fines']:,.2f} {I18n._('common.currency')}"))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.verticalHeader().setVisible(False)
        lay.addWidget(t)
        close_btn = QPushButton(I18n._("common.close"))
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn, 0, Qt.AlignCenter)
        dlg.exec_()

    # -----------------------------------------------------------------------
    # Logout
    # -----------------------------------------------------------------------

    def _on_logout(self) -> None:
        reply = QMessageBox.question(
            self, I18n._("login.logout"),
            I18n._("login.logout") + "?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.session_manager.clear_remember_me()
            self.db.log_event(f"User logged out: {self._user.get('username','?')}",
                              "INFO")
            self.close()
            QApplication.quit()

    # -----------------------------------------------------------------------
    # About
    # -----------------------------------------------------------------------

    def _show_about(self) -> None:
        QMessageBox.about(self, I18n._("common.about"),
            f"<h3>{I18n._('app.name')}</h3>"
            f"<p>{I18n._('app.version')}: {AppConfig.APP_VERSION}</p>"
            f"<p>{I18n._('app.copyright')}</p>"
            f"<p>{I18n._('settings.light')}/{I18n._('settings.dark')} · {I18n._('settings.language')}: RU/EN</p>")

    # -----------------------------------------------------------------------
    # Accessors for sub-tab injection
    # -----------------------------------------------------------------------

    def get_tab_widget(self, index: int) -> QWidget:
        return self._tab_widget.widget(index)

    def replace_tab(self, index: int, widget: QWidget, label: str) -> None:
        self._tab_widget.removeTab(index)
        self._tab_widget.insertTab(index, widget, label)
