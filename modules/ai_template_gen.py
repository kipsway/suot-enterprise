import json, os
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLabel,
    QPushButton,
    QMessageBox,
    QApplication,
)
from app_core.i18n import I18n
from modules.ai import AIEngine


def generate_template_suggestion(description: str, engine: AIEngine) -> str:
    prompt = (
        "You are an HTML template generator for an Occupational Safety and Health (OSH) "
        "management system called 'SUOT Enterprise'. "
        "Generate a clean, professional HTML template with inline CSS based on this description:\n\n"
        f"{description}\n\n"
        "Return ONLY the raw HTML code without any markdown code fences, explanations, or formatting."
    )
    result = engine.send_request([], prompt)
    if result is None:
        return "<!-- Error: No response from AI. Configure API key first. -->"
    result = result.strip()
    if result.startswith("```"):
        lines = result.split("\n", 1)
        result = lines[1] if len(lines) > 1 else lines[0]
        if result.endswith("```"):
            result = result[:-3]
    return result.strip()


class AITemplateGenDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("AI Template Generator")
        self.setMinimumSize(700, 500)
        self.resize(800, 600)
        self._engine = AIEngine()
        self._generated_html = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        layout.addWidget(
            QLabel(I18n._("template.desc_prompt", "Describe the template:"))
        )
        self._desc_input = QTextEdit()
        self._desc_input.setPlaceholderText(
            "e.g. A report template with company letterhead, violation table, "
            "signature block and page numbers"
        )
        self._desc_input.setMaximumHeight(80)
        layout.addWidget(self._desc_input)

        btn_layout = QHBoxLayout()
        self._gen_btn = QPushButton("Generate")
        self._gen_btn.setMinimumHeight(36)
        self._gen_btn.clicked.connect(self._generate)
        btn_layout.addStretch()
        btn_layout.addWidget(self._gen_btn)
        layout.addLayout(btn_layout)

        layout.addWidget(QLabel(I18n._("common.preview", "Preview:")))
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        layout.addWidget(self._preview, 1)

        use_layout = QHBoxLayout()
        self._use_btn = QPushButton(I18n._("template.save", "Use Template"))
        self._use_btn.setMinimumHeight(36)
        self._use_btn.setEnabled(False)
        self._use_btn.clicked.connect(self._use_template)
        use_layout.addStretch()
        use_layout.addWidget(self._use_btn)
        layout.addLayout(use_layout)

    def _generate(self):
        desc = self._desc_input.toPlainText().strip()
        if not desc:
            QMessageBox.warning(
                self, I18n._("common.warning"), "Please enter a template description"
            )
            return
        self._gen_btn.setEnabled(False)
        self._gen_btn.setText(I18n._("common.processing", "Generating..."))
        QApplication.processEvents()
        try:
            html = generate_template_suggestion(desc, self._engine)
            self._generated_html = html
            self._preview.setPlainText(html)
            self._use_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(
                self, I18n._("common.error"), f"Generation failed: {e}"
            )
        finally:
            self._gen_btn.setText("Generate")
            self._gen_btn.setEnabled(True)

    def _use_template(self):
        if not self._generated_html.strip():
            return
        from services.database import DatabaseManager

        db = DatabaseManager()
        name = self._desc_input.toPlainText().strip()[:50]
        db.save_print_template(
            name=f"AI: {name}" if name else "AI Generated Template",
            template_type="order",
            html_content=self._generated_html,
            css_content="",
        )
        QMessageBox.information(
            self,
            I18n._("common.success"),
            I18n._("template.registered", "Template saved successfully"),
        )
        self.accept()
