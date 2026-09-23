from datetime import datetime
from typing import Any, Dict, Optional

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from modules.ai import AIEngine
from services.database import DatabaseManager
from services.predictive import PredictiveModel


class AIReportDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI-отчёт")
        self.setMinimumSize(700, 500)
        self._engine = AIEngine()
        self._model = PredictiveModel()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("🤖 Генератор отчётов на базе AI")
        f = self.font()
        f.setPointSize(16)
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)

        row = QHBoxLayout()
        row.addWidget(QLabel("Тип отчёта:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(
            [
                "Общая сводка по охране труда",
                "Анализ нарушений",
                "Прогноз рисков",
                "Отчёт по обучению",
                "СИЗ-контроль",
                "Произвольный запрос",
            ]
        )
        self._type_combo.setMinimumWidth(200)
        row.addWidget(self._type_combo)
        row.addStretch()
        layout.addLayout(row)

        self._custom_query = QTextEdit()
        self._custom_query.setPlaceholderText("Опишите, что хотите получить...")
        self._custom_query.setMaximumHeight(60)
        self._custom_query.hide()
        self._type_combo.currentTextChanged.connect(
            lambda t: self._custom_query.setVisible(t == "Произвольный запрос")
        )
        layout.addWidget(self._custom_query)

        self._generate_btn = QPushButton("🚀 Сгенерировать отчёт")
        self._generate_btn.setFixedHeight(36)
        self._generate_btn.clicked.connect(self._generate)
        layout.addWidget(self._generate_btn)

        self._progress = QProgressBar()
        self._progress.hide()
        layout.addWidget(self._progress)

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        layout.addWidget(self._output, 1)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("📋 Копировать")
        copy_btn.clicked.connect(
            lambda: self._output.selectAll() or self._output.copy()
        )
        btn_row.addWidget(copy_btn)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.close)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _gather_data(self, report_type: str) -> str:
        db = DatabaseManager()
        parts = [f"Отчёт сгенерирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"]

        tables = {
            "incidents": (
                "Происшествия",
                ["date", "description", "severity", "status"],
            ),
            "violations": ("Нарушения", ["date", "description", "fine", "status"]),
            "employees": ("Сотрудники", ["full_name", "position", "department"]),
            "training": ("Обучение", ["name", "end_date", "status"]),
            "ppe": ("СИЗ", ["item_name", "issue_date", "status"]),
            "permits": (
                "Наряды-допуски",
                ["description", "start_date", "end_date", "status"],
            ),
        }

        for table, (label, fields) in tables.items():
            records = db.get_json_records(table)
            parts.append(f"\n=== {label}: {len(records)} записей ===")
            for rec in records[:5]:
                dj = rec.get("data_json", {})
                parts.append(
                    "  - "
                    + ", ".join(f"{f}: {dj.get(f, '—')}" for f in fields if f in dj)
                )

        if report_type == "Прогноз рисков":
            pm = PredictiveModel()
            risk = pm.risk_score()
            parts.append(f"\n=== ПРОГНОЗ РИСКОВ ===")
            parts.append(f"Общий риск: {risk['total_risk']} (уровень: {risk['level']})")
            for b in risk.get("breakdown", []):
                parts.append(
                    f"  {b['table']}: {b['count']} зап., вклад: {b['contribution']}"
                )
            for table in ["violations", "incidents", "training", "ppe"]:
                fc = pm.forecast(table)
                if "error" not in fc:
                    parts.append(f"\n--- {table} ---")
                    for fv in fc.get("forecast", []):
                        parts.append(f"  {fv['month']}: {fv['predicted']} (прогноз)")

        return "\n".join(parts)

    def _generate(self) -> None:
        rtype = self._type_combo.currentText()
        if rtype == "Произвольный запрос":
            prompt = self._custom_query.toPlainText().strip()
            if not prompt:
                self._output.setText("Введите запрос.")
                return
        else:
            prompt = f"Сгенерируй подробный отчёт на тему: {rtype}. Используй следующие данные:\n"

        data = self._gather_data(rtype)
        full_prompt = prompt + "\n\n" + data

        self._generate_btn.setEnabled(False)
        self._progress.show()
        self._output.setText("Генерация...")

        try:
            self._engine.provider = self._engine.db.get_ai_setting("provider", "openai")
            enc_key = self._engine.db.get_ai_setting("api_key", "")
            self._engine.api_key = self._engine.db.decrypt_value(enc_key)
            self._engine.model = self._engine.db.get_ai_setting(
                "model", "gpt-3.5-turbo"
            )
            response = self._engine.send_request([], full_prompt, "")
            self._output.setText(response)
        except Exception as e:
            self._output.setText(f"Ошибка: {e}\n\n(Проверьте API-ключ в настройках AI)")
        finally:
            self._generate_btn.setEnabled(True)
            self._progress.hide()
