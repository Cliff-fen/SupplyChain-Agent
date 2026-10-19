import pytest

from app.models import AnalysisRun, ReportExport
from app.services.reports import _repair_mojibake, render_markdown, render_pdf
from app.services.storage import export_asset_available


def test_render_markdown_contains_sql_rows_and_citations() -> None:
    run = AnalysisRun(
        id="run-1",
        tenant_id="tenant-1",
        conversation_id="conversation-1",
        data_source_id="source-1",
        question="生产达成率是多少？",
        sql="SELECT rate FROM production_orders",
        result={
            "insight": "达成率为 91.4%。",
            "rows": [{"factory": "成都", "rate": 91.4}],
            "citations": [{"document_name": "metrics.md", "location": {"start": 0, "end": 22}}],
        },
    )
    markdown, citations = render_markdown(run, "月度生产报告")
    assert markdown.startswith("# 月度生产报告")
    assert "SELECT rate" in markdown
    assert "| 成都 | 91.4 |" in markdown
    assert citations[0]["document_name"] == "metrics.md"


def test_render_pdf_creates_pdf(tmp_path) -> None:
    destination = tmp_path / "report.pdf"
    render_pdf(
        "# 月度报告\n\n## 数据结果\n\n| 工厂 | 达成率 |\n| --- | --- |\n| 上海工厂 | 91.4% |",
        str(destination),
    )
    assert destination.read_bytes().startswith(b"%PDF")


def test_report_export_repairs_legacy_chinese_mojibake(tmp_path) -> None:
    legacy_markdown = (
        "# 生产报告\n\n"
        "| factory | achievement_rate | at_risk_materials |\n"
        "| --- | --- | --- |\n"
        "| æé½å·¥å | 89.55 | 2 |"
    )
    destination = tmp_path / "legacy-report.pdf"

    assert "成都工厂" in _repair_mojibake(legacy_markdown)
    render_pdf(legacy_markdown, str(destination))
    assert destination.read_bytes().startswith(b"%PDF")


def test_completed_export_requires_an_available_local_asset(tmp_path) -> None:
    export = ReportExport(
        tenant_id="tenant-1",
        report_id="report-1",
        created_by="user-1",
        storage_backend="local",
        file_path=str(tmp_path / "missing.pdf"),
    )
    assert not export_asset_available(export.storage_backend, export.file_path, export.object_key)

    artifact = tmp_path / "ready.pdf"
    artifact.write_bytes(b"%PDF")
    export.file_path = str(artifact)
    assert export_asset_available(export.storage_backend, export.file_path, export.object_key)


@pytest.mark.parametrize("text", ["成都工厂", "达成率 89.55%", "café / naïve", "正常中文 🚀"])
def test_mojibake_repair_preserves_valid_unicode(text: str) -> None:
    assert _repair_mojibake(text) == text


def test_mojibake_repair_handles_mixed_scripts_and_invalid_bytes() -> None:
    damaged = "成都工厂 🚀".encode("utf-8").decode("latin-1")
    original = f"正常中文 | {damaged} | café | \xff"
    assert _repair_mojibake(original) == "正常中文 | 成都工厂 🚀 | café | \xff"


def test_completed_export_requires_an_object_key_for_s3() -> None:
    export = ReportExport(
        tenant_id="tenant-1",
        report_id="report-1",
        created_by="user-1",
        storage_backend="s3",
    )
    assert not export_asset_available(export.storage_backend, export.file_path, export.object_key)
