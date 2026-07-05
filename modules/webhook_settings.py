from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLabel, QLineEdit, QPushButton, QCheckBox,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QMessageBox, QDialog,
                             QDialogButtonBox, QComboBox, QWidget)

from app_core.i18n import I18n
from services.webhook_service import (get_all_targets, save_target,
                                       delete_target, test_webhook,
                                       WEBHOOK_EVENTS)
from widgets.toast import ToastNotification


class WebhookEditDialog(QDialog):
    def __init__(self, target: Optional[Dict[str, Any]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._target = target or {}
        self.setWindowTitle(I18n._("webhook.edit") if target else I18n._("webhook.add"))
        self.setMinimumSize(500, 350)
        self.resize(560, 380)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        heading = QLabel(self.windowTitle())
        heading.setProperty("heading", True)
        layout.addWidget(heading)
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)
        self._name_edit = QLineEdit(self._target.get("name", ""))
        self._name_edit.setMinimumHeight(36)
        form.addRow(I18n._("common.name") + ":", self._name_edit)
        self._url_edit = QLineEdit(self._target.get("url", ""))
        self._url_edit.setMinimumHeight(36)
        self._url_edit.setPlaceholderText("https://hooks.example.com/endpoint")
        form.addRow("URL:", self._url_edit)
        self._events_combo = QComboBox()
        self._events_combo.setMinimumHeight(36)
        self._events_combo.addItem(I18n._("webhook.all_events"), "*")
        for ev in WEBHOOK_EVENTS:
            self._events_combo.addItem(ev, ev)
        current_events = self._target.get("events", "*")
        idx = self._events_combo.findData(current_events)
        if idx < 0:
            self._events_combo.setEditText(current_events)
        else:
            self._events_combo.setCurrentIndex(idx)
        self._events_combo.setEditable(True)
        form.addRow(I18n._("webhook.events") + ":", self._events_combo)
        self._enabled_cb = QCheckBox(I18n._("webhook.enabled"))
        self._enabled_cb.setChecked(int(self._target.get("enabled", 1)) == 1)
        form.addRow("", self._enabled_cb)
        layout.addLayout(form)
        layout.addStretch()
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> Dict[str, Any]:
        return {
            "name": self._name_edit.text().strip(),
            "url": self._url_edit.text().strip(),
            "events": self._events_combo.currentText().strip() or "*",
            "enabled": self._enabled_cb.isChecked(),
        }


class WebhookSettingsWidget(QFrame):
    def __init__(self, parent: Optional[QFrame] = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self._build_ui()
        self._load_targets()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        heading = QLabel(I18n._("webhook.title"))
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        desc = QLabel(I18n._("webhook.desc"))
        desc.setStyleSheet("font-size: 12px; color: #888;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        toolbar = QHBoxLayout()
        self._add_btn = QPushButton(I18n._("webhook.add"))
        self._add_btn.clicked.connect(self._add_target)
        toolbar.addWidget(self._add_btn)
        self._edit_btn = QPushButton(I18n._("common.edit"))
        self._edit_btn.clicked.connect(self._edit_target)
        toolbar.addWidget(self._edit_btn)
        self._delete_btn = QPushButton(I18n._("common.delete"))
        self._delete_btn.clicked.connect(self._delete_target)
        toolbar.addWidget(self._delete_btn)
        self._test_btn = QPushButton(I18n._("webhook.test"))
        self._test_btn.setProperty("flat", True)
        self._test_btn.clicked.connect(self._test_target)
        toolbar.addWidget(self._test_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(self._table)

    def _load_targets(self) -> None:
        self._targets = get_all_targets()
        cols = ["ID", I18n._("common.name"), "URL", I18n._("webhook.events"),
                I18n._("webhook.enabled"), I18n._("webhook.last_status")]
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.setRowCount(len(self._targets))
        for row, t in enumerate(self._targets):
            self._table.setItem(row, 0, QTableWidgetItem(str(t.get("id", ""))))
            self._table.setItem(row, 1, QTableWidgetItem(str(t.get("name", ""))))
            self._table.setItem(row, 2, QTableWidgetItem(str(t.get("url", ""))))
            self._table.setItem(row, 3, QTableWidgetItem(str(t.get("events", ""))))
            self._table.setItem(row, 4, QTableWidgetItem(
                "✔" if int(t.get("enabled", 1)) else "✘"))
            self._table.setItem(row, 5, QTableWidgetItem(str(t.get("last_status", ""))[:50]))
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.setColumnWidth(0, 40)
        self._table.setColumnWidth(1, 150)
        self._table.setColumnWidth(2, 200)
        self._table.setColumnWidth(3, 120)
        self._table.setColumnWidth(4, 60)

    def _get_selected(self) -> Optional[Dict[str, Any]]:
        row = self._table.currentRow()
        if 0 <= row < len(self._targets):
            return self._targets[row]
        return None

    def _add_target(self) -> None:
        dlg = WebhookEditDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if data["name"] and data["url"]:
                save_target(0, data["name"], data["url"],
                            data["events"], data["enabled"])
                self._load_targets()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _edit_target(self) -> None:
        t = self._get_selected()
        if not t:
            return
        dlg = WebhookEditDialog(t, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if data["name"] and data["url"]:
                save_target(t["id"], data["name"], data["url"],
                            data["events"], data["enabled"])
                self._load_targets()
                ToastNotification.notify(I18n._("common.success"), "success", 3000)

    def _delete_target(self) -> None:
        t = self._get_selected()
        if not t:
            return
        if QMessageBox.question(self, I18n._("common.confirm"),
                                 I18n._("webhook.delete_confirm"),
                                 QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            delete_target(t["id"])
            self._load_targets()
            ToastNotification.notify(I18n._("toast.delete_success"), "success", 3000)

    def _test_target(self) -> None:
        t = self._get_selected()
        if not t:
            return
        err = test_webhook(str(t["url"]))
        if err:
            QMessageBox.warning(self, I18n._("common.error"),
                                f"{I18n._('webhook.test_fail')}: {err}")
        else:
            ToastNotification.notify(I18n._("webhook.test_ok"), "success", 3000)
