"""Compatibility exports for the tenancy identity boundary."""

from app.modules.tenancy.dependencies import bearer, get_principal, require_role

__all__ = ["bearer", "get_principal", "require_role"]
