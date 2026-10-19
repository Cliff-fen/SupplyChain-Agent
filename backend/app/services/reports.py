import re

from app.models import AnalysisRun

# Valid UTF-8 byte sequences represented as Latin-1 characters. Match only the
# damaged sequences, so real Chinese and ordinary accented text are preserved.
_UTF8_AS_LATIN1 = re.compile(
    r"(?:[\xc2-\xdf][\x80-\xbf]"
    r"|\xe0[\xa0-\xbf][\x80-\xbf]"
    r"|[\xe1-\xec\xee-\xef][\x80-\xbf]{2}"
    r"|\xed[\x80-\x9f][\x80-\xbf]"
    r"|\xf0[\x90-\xbf][\x80-\xbf]{2}"
    r"|[\xf1-\xf3][\x80-\xbf]{3}"
    r"|\xf4[\x80-\x8f][\x80-\xbf]{2})+"
)


def _repair_mojibake(value: str) -> str:
    """Repair the common UTF-8-as-Latin-1 legacy representation for exports."""
    return _UTF8_AS_LATIN1.sub(
        lambda match: match.group().encode("latin-1").decode("utf-8"), value
    )


def render_pdf(markdown: str, destination: str) -> None:
    """Render a readable, dependency-light PDF from report markdown."""
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    # The TrueType WenQuanYi CJK face is embedded in the PDF. Browser PDF
    # viewers cannot reliably render unembedded CID fallback fonts.
    font_name = "SupplyMindCJK"
    font_path = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    pdfmetrics.registerFont(TTFont(font_name, font_path, subfontIndex=0))
    markdown = _repair_mojibake(markdown)
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font_name
    story = []
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 4 * mm))
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and lines[index + 1].strip().startswith("|"):
            rows: list[list[str]] = []
            header = [cell.strip() for cell in line.strip("|").split("|")]
            index += 2  # Skip the Markdown separator row.
            rows.append(header)
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            width = 174 * mm / max(len(header), 1)
            table = Table(
                [[Paragraph(escape(cell), styles["BodyText"]) for cell in row] for row in rows],
                colWidths=[width] * len(header),
                repeatRows=1,
                hAlign="LEFT",
            )
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f3ed")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#153d30")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b7d4c5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.extend([table, Spacer(1, 4 * mm)])
            continue
        if line.startswith("# "):
            story.append(Paragraph(escape(line[2:]), styles["Title"]))
        elif line.startswith("## "):
            story.append(Paragraph(escape(line[3:]), styles["Heading2"]))
        elif line.startswith("- "):
            story.append(Paragraph("&#8226; " + escape(line[2:]), styles["BodyText"]))
        else:
            story.append(Paragraph(escape(line.replace("**", "")), styles["BodyText"]))
        index += 1
    SimpleDocTemplate(
        destination,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    ).build(story)


def render_markdown(run: AnalysisRun, title: str | None = None) -> tuple[str, list]:
    result = run.result or {}
    insight = result.get("insight") or "分析任务已完成，暂无结构化洞察。"
    insights = result.get("insights") or {}
    rows = result.get("rows") or []
    citations = result.get("citations") or []
    heading = title or f"供应链分析报告 · {run.question[:80]}"
    lines = [f"# {heading}", "", f"**问题**：{run.question}", "", "## 结论", "", insight, ""]
    for label, key in (("事实", "facts"), ("风险", "risks"), ("建议", "recommendations")):
        values = insights.get(key) or []
        if values:
            lines.extend([f"## {label}", ""])
            lines.extend(f"- {value}" for value in values)
            lines.append("")
    if run.sql:
        lines.extend(["## 受限 SQL", "", "```sql", run.sql, "```", ""])
    if rows:
        lines.extend(["## 数据结果", ""])
        columns = list(rows[0].keys())
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join("---" for _ in columns) + " |")
        lines.extend(
            "| " + " | ".join(str(row.get(column, "")) for column in columns) + " |"
            for row in rows[:50]
        )
        lines.append("")
    if citations:
        lines.extend(["## 依据", ""])
        lines.extend(
            f"- {item.get('document_name', '文档')} · {item.get('location', {})}"
            for item in citations
        )
    return "\n".join(lines).strip() + "\n", citations
