import re
from typing import Tuple


def markdown_to_html(text: str) -> str:
    lines = text.split("\n")
    html_parts: list = []
    in_code_block = False
    code_buffer: list = []
    in_list = False
    in_ordered_list = False

    for line in lines:
        if line.strip().startswith("```"):
            if in_code_block:
                code = "\n".join(code_buffer)
                escaped = _escape_html(code)
                html_parts.append(
                    f"<pre style='background:rgba(0,0,0,0.08);border-radius:6px;padding:8px;margin:4px 0;font-size:12px;overflow-x:auto;'><code>{escaped}</code></pre>"
                )
                code_buffer = []
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_buffer.append(line)
            continue

        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            if in_ordered_list:
                html_parts.append("</ol>")
                in_ordered_list = False
            html_parts.append("<br>")
            continue

        if stripped.startswith("```"):
            continue

        if re.match(r"^#{1,6}\s", stripped):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            if in_ordered_list:
                html_parts.append("</ol>")
                in_ordered_list = False
            level = stripped.count("#", 0, stripped.index(" "))
            content = _inline(stripped[level + 1 :])
            html_parts.append(
                f"<h{level} style='margin:8px 0 4px;'>{content}</h{level}>"
            )
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            if in_ordered_list:
                html_parts.append("</ol>")
                in_ordered_list = False
            if not in_list:
                in_list = True
                html_parts.append("<ul style='margin:4px 0;padding-left:20px;'>")
            html_parts.append(f"<li>{_inline(stripped[2:])}</li>")
            continue

        if re.match(r"^\d+\.\s", stripped):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            if not in_ordered_list:
                in_ordered_list = True
                html_parts.append("<ol style='margin:4px 0;padding-left:20px;'>")
            content = _inline(re.sub(r"^\d+\.\s*", "", stripped))
            html_parts.append(f"<li>{content}</li>")
            continue

        if in_list:
            html_parts.append("</ul>")
            in_list = False
        if in_ordered_list:
            html_parts.append("</ol>")
            in_ordered_list = False

        html_parts.append(f"<p style='margin:4px 0;'>{_inline(stripped)}</p>")

    if in_code_block:
        code = "\n".join(code_buffer)
        escaped = _escape_html(code)
        html_parts.append(
            f"<pre style='background:rgba(0,0,0,0.08);border-radius:6px;padding:8px;margin:4px 0;font-size:12px;overflow-x:auto;'><code>{escaped}</code></pre>"
        )
    if in_list:
        html_parts.append("</ul>")
    if in_ordered_list:
        html_parts.append("</ol>")

    result = "".join(html_parts)
    result = result.replace("\n", " ")
    while "  " in result:
        result = result.replace("  ", " ")
    return result


def _inline(text: str) -> str:
    text = _escape_html(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(
        r"`(.+?)`",
        r"<code style='background:rgba(0,0,0,0.06);border-radius:3px;padding:1px 4px;font-size:12px;'>\1</code>",
        text,
    )
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(
        r"\[(.+?)\]\((.+?)\)", r'<a href="\2" style="color:#2196F3;">\1</a>', text
    )
    return text


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
