import os, base64, mimetypes, re
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QObject, QEvent
from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QBrush, QPen
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog, QAbstractPrintDialog
from PyQt5.QtWidgets import QDialog, QWidget, QInputDialog, QTextBrowser
from widgets.glass_button import GlassButton
from widgets.glass_line_edit import GlassLineEdit
from widgets.glass_combo_box import GlassComboBox

from app_core.i18n import I18n
from services.database import DatabaseManager
from widgets.toast import ToastNotification


class PrintEngine:
    @staticmethod
    def image_to_base64(path: str) -> str:
        try:
            with open(path, "rb") as f:
                data = f.read()
                ext = os.path.splitext(path)[1].lower().replace(".", "")
                mime = mimetypes.guess_type(path)[0] or f"image/{ext}"
                return f"data:{mime};base64,{base64.b64encode(data).decode()}"
        except Exception:
            return ""

    @staticmethod
    def render_order(
        data: Dict[str, Any],
        photos: Optional[List[str]] = None,
        template_html: Optional[str] = None,
    ) -> str:
        db = DatabaseManager()
        if not template_html:
            templates = db.get_print_templates("order")
            template_html = templates[0]["html_content"] if templates else ""
        if not template_html:
            template_html = "<h1>Order</h1><p>{description}</p>"

        photos_html = ""
        if photos:
            photo_items = ""
            for p in photos:
                if os.path.isfile(p):
                    b64 = PrintEngine.image_to_base64(p)
                    photo_items += f'<img src="{b64}" alt="photo" />'
            if photo_items:
                photos_html = f'<div class="photos">{photo_items}</div>'

        now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        ctx = {
            "id": data.get("id", ""),
            "date": data.get("Дата", now_str),
            "company": data.get("Фирма", ""),
            "responsible": data.get("Ответственный", ""),
            "deadline": data.get("Срок устранения", ""),
            "description": data.get("Описание", ""),
            "recommended_action": data.get("Рекомендуемые меры", ""),
            "fine": data.get("Штраф", "0"),
            "photos_section": photos_html,
            "app_name": I18n._("app.name"),
            "generated_at": now_str,
            "record_number": data.get("id", str(data.get("id", ""))),
        }
        result = template_html
        for key, val in ctx.items():
            result = result.replace(f"{{{key}}}", str(val))
        return result

    @staticmethod
    def render_report(
        company_name: str = "",
        include_employees: bool = True,
        include_violations: bool = True,
        include_fines: bool = True,
        template_html: Optional[str] = None,
    ) -> str:
        db = DatabaseManager()
        if not template_html:
            templates = db.get_print_templates("report")
            template_html = templates[0]["html_content"] if templates else ""
        if not template_html:
            template_html = "<h1>Report</h1><p>{company_name}</p>"

        emp_count = 0
        viol_count = 0
        fines = 0.0
        overdue = 0
        rows_html = ""
        now = datetime.now()

        if company_name:
            companies_data = [{"name": company_name}]
        else:
            companies_data = db.get_companies()

        for company in companies_data:
            cname = company.get("name", "")
            c_emp = 0
            c_viol = 0
            c_fines = 0.0
            c_overdue = 0
            viol_rows = ""

            for emp in db.get_json_records("employees"):
                if emp.get("data_json", {}).get("Фирма") == cname:
                    c_emp += 1

            for viol in db.get_json_records("violations"):
                dj = viol.get("data_json", {})
                if dj.get("Фирма") == cname:
                    c_viol += 1
                    try:
                        f = float(
                            str(dj.get("Штраф", "0")).replace(" ", "").replace(",", ".")
                        )
                        c_fines += f
                    except Exception:
                        f = 0
                    deadline = dj.get("Срок устранения", "")
                    if deadline:
                        try:
                            p = deadline.split(".")
                            if len(p) == 3:
                                dl = datetime(int(p[2]), int(p[1]), int(p[0]))
                                if dl < now:
                                    c_overdue += 1
                        except Exception:
                            pass
                    if include_violations:
                        viol_rows += f"""<tr>
                            <td>{dj.get("Дата", "")}</td>
                            <td>{dj.get("Категория риска", "")}</td>
                            <td>{dj.get("Описание", "")[:50]}</td>
                            <td>{dj.get("Ответственный", "")}</td>
                            <td>{dj.get("Срок устранения", "")}</td>
                            <td>{dj.get("Штраф", "0")}</td>
                            <td>{dj.get("Статус", "")}</td>
                        </tr>"""

            emp_count += c_emp
            viol_count += c_viol
            fines += c_fines
            overdue += c_overdue

            if include_employees and include_violations:
                rows_html += f"""<tr>
                    <td>{cname}</td>
                    <td>{c_emp}</td>
                    <td>{c_viol}</td>
                    <td>{c_fines:,.0f}</td>
                    <td>{c_overdue}</td>
                </tr>"""

        all_viol_rows = ""
        if include_violations and not company_name:
            for viol in db.get_json_records("violations"):
                dj = viol.get("data_json", {})
                all_viol_rows += f"""<tr>
                    <td>{dj.get("Фирма", "")}</td>
                    <td>{dj.get("Дата", "")}</td>
                    <td>{dj.get("Категория риска", "")}</td>
                    <td>{dj.get("Описание", "")[:50]}</td>
                    <td>{dj.get("Штраф", "0")}</td>
                    <td>{dj.get("Статус", "")}</td>
                </tr>"""

        table_html = ""
        if rows_html:
            table_html = (
                """<table>
                <tr><th>Компания</th><th>Сотрудников</th><th>Нарушений</th>
                <th>Штрафы</th><th>Просрочено</th></tr>"""
                + rows_html
                + "</table>"
            )
        if all_viol_rows:
            table_html += (
                """<h2>Все нарушения</h2><table>
                <tr><th>Фирма</th><th>Дата</th><th>Категория</th>
                <th>Описание</th><th>Штраф</th><th>Статус</th></tr>"""
                + all_viol_rows
                + "</table>"
            )

        now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        ctx = {
            "company_name": company_name or I18n._("filter.all"),
            "date": now_str,
            "emp_count": str(emp_count),
            "viol_count": str(viol_count),
            "fines_total": f"{fines:,.0f}",
            "overdue_count": str(overdue),
            "table_html": table_html,
            "app_name": I18n._("app.name"),
            "generated_at": now_str,
        }
        result = template_html
        for key, val in ctx.items():
            result = result.replace(f"{{{key}}}", str(val))
        return result

    @staticmethod
    def select_template(parent: QWidget, template_type: str = "order") -> Optional[str]:
        db = DatabaseManager()
        templates = db.get_print_templates(template_type)
        if not templates:
            return None
        names = [t["name"] for t in templates]
        name, ok = QInputDialog.getItem(
            parent, I18n._("template.title"), I18n._("template.choose"), names, 0, False
        )
        if ok and name:
            for t in templates:
                if t["name"] == name:
                    return t.get("html_content", "")
        return None

    @staticmethod
    def render_with_template(
        parent: QWidget,
        template_type: str,
        records_data: List[Dict[str, Any]],
        columns: List[Dict[str, Any]],
        template_html: Optional[str] = None,
    ) -> str:
        html = (
            template_html
            if template_html is not None
            else PrintEngine.select_template(parent, template_type)
        )
        if html is None:
            parts = []
            for rec in records_data:
                dj = rec.get("data_json", {})
                lbl = (
                    I18n._("tab.employees")
                    if template_type == "order"
                    else I18n._("tab.violations")
                )
                lines = [f"<h1>{lbl} #{rec.get('id', '')}</h1><table>"]
                for col in columns:
                    name = col["name"]
                    val = dj.get(name, "")
                    lines.append(f"<tr><td><b>{name}</b></td><td>{val}</td></tr>")
                lines.append("</table><hr>")
                parts.append("".join(lines))
            return "<html><body>" + "".join(parts) + "</body></html>"
        repeat_start = "ПОВТОРЯЕМЫЙ БЛОК: 1-е, 2-е, 3-е и следующие предписания"
        repeat_end = "КОНЕЦ ПОВТОРЯЕМОГО БЛОКА"
        if repeat_start in html and repeat_end in html:
            before, rest = html.split(repeat_start, 1)
            block, after = rest.split(repeat_end, 1)
            rendered_parts = []
            for index, rec in enumerate(records_data, start=1):
                dj = rec.get("data_json", {})
                rendered = block
                for key, val in dj.items():
                    rendered = rendered.replace(f"{{{key}}}", str(val))
                rendered = rendered.replace("{id}", str(rec.get("id", "")))
                rendered = rendered.replace("{record_number}", str(rec.get("id", "")))
                rendered = rendered.replace("{violation_number}", str(index))
                rendered = rendered.replace("{violation_index}", str(index))
                rendered = rendered.replace("{page_number}", str(index))
                rendered_parts.append(rendered)
            result = before + "".join(rendered_parts) + after
            return "<html><body>" + result + "</body></html>"

        parts = []
        for index, rec in enumerate(records_data, start=1):
            dj = rec.get("data_json", {})
            rendered = html
            for key, val in dj.items():
                rendered = rendered.replace(f"{{{key}}}", str(val))
            rendered = rendered.replace("{id}", str(rec.get("id", "")))
            rendered = rendered.replace("{record_number}", str(rec.get("id", "")))
            rendered = rendered.replace("{violation_number}", str(index))
            rendered = rendered.replace("{page_number}", str(index))
            parts.append(rendered)
        result = "<html><body>" + "".join(parts) + "</body></html>"
        if len(parts) > 1 and "page-break-before" not in result:
            result = (
                "<html><body>"
                + parts[0]
                + "".join(
                    "<div style='page-break-before:always; margin:0; padding:0; height:1px;'></div>"
                    + p
                    for p in parts[1:]
                )
                + "</body></html>"
            )
        return result

    @staticmethod
    def print_document(html: str, parent: Optional[QWidget] = None) -> None:
        try:

            def _has_content(segment: str) -> bool:
                clean = segment
                for tag in [
                    "<p></p>",
                    "<p> </p>",
                    "<p>&nbsp;</p>",
                    "<br>",
                    "<br/>",
                    "<div></div>",
                    "<div> </div>",
                    "<div>&nbsp;</div>",
                    "<hr>",
                    "<hr/>",
                ]:
                    clean = clean.replace(tag, "")
                clean = re.sub(r"<[^>]+>", "", clean).strip()
                return bool(clean)

            parts = re.split(
                r"<(div|p)\s+[^>]*?page-break-before:always[^>]*?>.*?</\1>", html
            )
            merged = parts[0]
            for i in range(1, len(parts)):
                if _has_content(parts[i]):
                    merged += parts[i]
            if merged != html:
                html = merged

            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, parent)
            dialog.setWindowTitle(I18n._("common.print"))
            if dialog.exec_() != QDialog.Accepted:
                return
            browser = QTextBrowser()
            browser.setHtml(html)
            browser.print_(printer)
            ToastNotification.notify(I18n._("print.generated"), "success", 3000)
        except Exception:
            ToastNotification.notify(I18n._("error.generic"), "error", 5000)

    @staticmethod
    def export_to_pdf(
        html: str, file_path: str, parent: Optional[QWidget] = None
    ) -> bool:
        try:
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(file_path)
            browser = QTextBrowser()
            browser.setHtml(html)
            browser.print_(printer)
            return True
        except Exception:
            return False
