from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Report
from app.modules.reports.repository import get_for_tenant
from app.services.reports import render_markdown, render_pdf


async def get_tenant_report(session: AsyncSession, report_id: str, tenant_id: str) -> Report:
    report = await get_for_tenant(session, report_id, tenant_id)
    if not report:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


__all__ = ["get_tenant_report", "render_markdown", "render_pdf"]
