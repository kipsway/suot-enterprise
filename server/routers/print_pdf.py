"""Печать II: PDF через Edge headless, пакетная печать, водяной знак."""

import io
import os
from datetime import datetime
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager
from app_core.utils import JsonUtils

router = APIRouter(prefix="/api/print", tags=["print-pdf"])

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
]


def _find_edge():
    for p in EDGE_PATHS:
        if os.path.isfile(p):
            return p
    return None


def _html_to_pdf(
    html, output_path, page_size="A4", orientation="portrait", margins="15mm"
):
    edge = _find_edge()
    if not edge:
        return False
    tmp_html = output_path.replace(".pdf", ".html")
    if orientation == "landscape":
        page_css = "@page { size: A4 landscape; margin: %s; }" % margins
    else:
        page_css = "@page { size: %s %s; margin: %s; }" % (
            page_size,
            page_size,
            margins,
        )
    full = (
        '<!DOCTYPE html>\n<html><head><meta charset="utf-8">\n'
        "<style>\n" + page_css + "\n"
        "body { font-family: 'Times New Roman', serif; "
        "font-size: 14pt; color: #111; margin: 0; }\n"
        "img { max-width: 100%; }\n"
        "table { border-collapse: collapse; width: 100%; }\n"
        "td, th { border: 1px solid #ccc; padding: 6px 10px; }\n"
        "</style></head><body>" + html + "</body></html>"
    )
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(full)
    try:
        flags = 0
        if hasattr(subprocess, "CREATE_NO_FLAG"):
            flags = subprocess.CREATE_NO_FLAG
        prof = output_path + ".edge-profile"
        proc = subprocess.Popen(
            [
                edge,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--user-data-dir=" + prof,
                "--no-first-run",
                "--disable-extensions",
                "--disable-background-networking",
                "--no-pdf-header-footer",
                "--print-to-pdf=" + output_path,
                tmp_html,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            if os.path.isfile(output_path) and os.path.getsize(output_path) > 500:
                break
            if proc.poll() is not None:
                break
            time.sleep(0.2)
        try:
            if proc.poll() is None:
                proc.kill()
                proc.wait(5)
        except Exception:
            pass
        return os.path.isfile(output_path) and os.path.getsize(output_path) > 500
    except Exception:
        return False
    finally:
        try:
            os.remove(tmp_html)
        except OSError:
            pass


def _add_watermark(html, text="", image_data=""):
    wm = ""
    if text:
        wm = (
            '<div style="position:fixed;top:50%;left:50%;'
            "transform:translate(-50%,-50%) rotate(-30deg);"
            "font-size:72pt;color:rgba(0,0,0,.06);"
            "white-space:nowrap;pointer-events:none;"
            'z-index:-1;user-select:none">' + text + "</div>"
        )
    elif image_data:
        wm = (
            '<div style="position:fixed;top:50%;left:50%;'
            "transform:translate(-50%,-50%);opacity:.06;"
            'pointer-events:none;z-index:-1">'
            '<img src="' + image_data + '" '
            'style="max-width:80%;max-height:80%"></div>'
        )
    if wm:
        return html + wm
    return html


class PdfIn(BaseModel):
    html_content: str
    page_size: str = "A4"
    orientation: str = "portrait"
    margins: str = "15mm"
    watermark_text: str = ""
    watermark_image: str = ""  # base64 data URL


class BatchPdfIn(BaseModel):
    template_html: str
    table: str
    record_ids: List[int] = []
    page_size: str = "A4"
    orientation: str = "portrait"
    margins: str = "15mm"
    watermark_text: str = ""
    merge: bool = True  # True → один PDF, False → ZIP отдельных PDF


def _render_record(html, data):
    import re

    data["today"] = datetime.now().strftime("%d.%m.%Y")
    data["username"] = "system"
    result = html
    for k, v in data.items():
        result = result.replace("{" + k + "}", str(v or ""))
    result = re.sub(r"\{[^}]+\}", "\u2014", result)
    return result


@router.post("/pdf")
def generate_pdf(body: PdfIn, db=Depends(get_db), user=Depends(get_current_user)):
    html = body.html_content
    if body.watermark_text:
        html = _add_watermark(html, text=body.watermark_text)
    elif body.watermark_image:
        html = _add_watermark(html, image_data=body.watermark_image)
    tmp = os.path.join(tempfile.gettempdir(), f"suot_pdf_{uuid.uuid4().hex[:8]}.pdf")
    ok = _html_to_pdf(html, tmp, body.page_size, body.orientation, body.margins)
    if not ok:
        raise HTTPException(
            500, "PDF не сгенерирован. Убедитесь что Microsoft Edge установлен."
        )
    data = open(tmp, "rb").read()
    os.remove(tmp)
    from fastapi.responses import Response

    return Response(
        data,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=document.pdf"},
    )


@router.post("/batch_pdf")
def batch_pdf(body: BatchPdfIn, db=Depends(get_db), user=Depends(get_current_user)):
    uid = int(user["id"])
    admin = is_admin(user)
    rows = []
    if body.record_ids:
        for rid in body.record_ids:
            # IDOR-фикс (аудит 7.2 п.2): печать по ids — только свои записи.
            if not db.user_can_access(body.table, rid, uid, admin):
                continue
            rec = db.get_json_record(body.table, rid)
            if rec:
                rows.append(rec)
    else:
        rows = db.query_json_records(
            body.table, None if admin else uid, is_admin=admin, page_size=500
        )[0]
    if not rows:
        raise HTTPException(404, "Нет записей для печати")
    tmpdir = tempfile.mkdtemp(prefix="suot_batch_")
    pdf_files = []
    for i, row in enumerate(rows):
        data = row.get("data_json") or {}
        html = _render_record(body.template_html, data)
        if body.watermark_text:
            html = _add_watermark(html, text=body.watermark_text)
        out = os.path.join(tmpdir, f"doc_{i:04d}.pdf")
        if _html_to_pdf(html, out, body.page_size, body.orientation, body.margins):
            pdf_files.append(out)
    if not pdf_files:
        raise HTTPException(500, "Ни один PDF не сгенерирован")
    if len(pdf_files) == 1 or not body.merge:
        if len(pdf_files) == 1 and body.merge:
            data = open(pdf_files[0], "rb").read()
            _cleanup(tmpdir)
            from fastapi.responses import Response

            return Response(
                data,
                media_type="application/pdf",
                headers={"Content-Disposition": "attachment; filename=batch.pdf"},
            )
        zbuf = io.BytesIO()
        import zipfile

        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
            for pf in pdf_files:
                zf.write(pf, os.path.basename(pf))
        _cleanup(tmpdir)
        from fastapi.responses import Response

        return Response(
            zbuf.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=batch_pdfs.zip"},
        )
    # merge: объединяем через pypdf или просто первый (fallback)
    merged = _merge_pdfs(pdf_files)
    _cleanup(tmpdir)
    from fastapi.responses import Response

    return Response(
        merged,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=batch_merged.pdf"},
    )


def _merge_pdfs(pdf_files):
    try:
        from pypdf import PdfWriter
    except ImportError:
        try:
            from PyPDF2 import PdfWriter
        except ImportError:
            return open(pdf_files[0], "rb").read()
    writer = PdfWriter()
    for pf in pdf_files:
        import io as _io
        from pypdf import PdfReader

        reader = PdfReader(_io.BytesIO(open(pf, "rb").read()))
        for page in reader.pages:
            writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _cleanup(tmpdir):
    import shutil

    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


@router.get("/edge_available")
def edge_available(user=Depends(get_current_user)):
    return {"available": _find_edge() is not None, "path": _find_edge() or ""}


# ── Часть 21: печать текущего вида таблицы ──


class ListPrintIn(BaseModel):
    title: str = ""
    columns: List[str]
    rows: List[List[str]]
    orientation: str = "landscape"
    watermark_text: str = ""


@router.post("/list-pdf")
def list_pdf(body: ListPrintIn, user=Depends(get_current_user)):
    if not body.columns or not body.rows:
        raise HTTPException(400, "Пустая таблица для печати")
    if len(body.columns) > 40 or len(body.rows) > 2000:
        raise HTTPException(400, "Слишком большой список")

    def esc(v: str) -> str:
        s = str(v if v is not None else "")
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    head = "".join(f"<th>{esc(c)}</th>" for c in body.columns)
    body_rows = []
    for r in body.rows[:2000]:
        tds = "".join(f"<td>{esc(v)}</td>" for v in r[: len(body.columns)])
        body_rows.append(f"<tr>{tds}</tr>")
    stamp = datetime.now().strftime("%d.%m.%Y %H:%M")
    title = esc(body.title or "Список")
    html = (
        '<h2 style="margin:0 0 4px">' + title + "</h2>"
        '<p style="font-size:10pt;color:#555;margin:0 0 12px">'
        + "ОхранаТруда Про · записей: "
        + str(len(body.rows))
        + " · "
        + stamp
        + "</p>"
        '<table style="width:100%;border-collapse:collapse;'
        'font-size:9.5pt">'
        '<thead><tr style="background:#eef0f4">'
        + head
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table>"
    )

    tmpdir = tempfile.mkdtemp(prefix="suot_listpdf_")
    out = os.path.join(tmpdir, uuid.uuid4().hex + ".pdf")
    html_full = _add_watermark(html, text=body.watermark_text or "")
    ok = _html_to_pdf(
        html_full, out, orientation=body.orientation or "landscape", margins="12mm"
    )
    if not ok:
        _cleanup(tmpdir)
        raise HTTPException(500, "Edge headless недоступен для PDF")
    data = open(out, "rb").read()
    _cleanup(tmpdir)
    from fastapi.responses import Response

    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=list.pdf"},
    )
