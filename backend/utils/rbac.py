"""Centralized fail-closed Role-Based Access Control (RBAC) and jurisdiction helpers."""
from typing import Optional, Set
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend import models

GLOBAL_ROLES = {
    models.UserRole.DGP,
    models.UserRole.ADMIN,
}

# Maps each scoped role to (User attribute, Case attribute, human-readable label)
_ROLE_SCOPE = {
    models.UserRole.CONSTABLE: ("station_name", "police_station", "station"),
    models.UserRole.HEAD_CONSTABLE: ("station_name", "police_station", "station"),
    models.UserRole.SUB_INSPECTOR: ("station_name", "police_station", "station"),
    models.UserRole.INSPECTOR: ("station_name", "police_station", "station"),
    models.UserRole.OFFICER: ("station_name", "police_station", "station"),
    models.UserRole.DY_SP: ("sub_division", "sub_division", "sub-division"),
    models.UserRole.SP: ("district_name", "district_name", "district"),
    models.UserRole.DIG: ("range_name", "range_name", "range"),
    models.UserRole.IGP: ("zone_name", "zone_name", "zone"),
}


def _get_user_scope(current_user: models.User) -> tuple[str, str, str, str]:
    """Return (user_attr, case_attr, scope_value, label) or raise 403 fail-closed."""
    scope = _ROLE_SCOPE.get(current_user.role)
    if not scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: unrecognized role.",
        )

    user_attr, case_attr, label = scope
    scope_val = getattr(current_user, user_attr, None)
    if not scope_val or not str(scope_val).strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Jurisdiction not assigned ({label}). Contact an administrator.",
        )
    return user_attr, case_attr, str(scope_val).strip(), label


def apply_jurisdiction_filter(query, current_user: models.User, model=models.Case):
    """Filter a Case query to the current user's jurisdiction, failing closed if unassigned."""
    if current_user.role in GLOBAL_ROLES:
        return query

    _, case_attr, scope_val, _ = _get_user_scope(current_user)
    return query.filter(getattr(model, case_attr) == scope_val)


def get_accessible_case_ids(current_user: models.User, db: Session) -> Optional[Set[int]]:
    """Return accessible case IDs for scoped roles, or None for global roles."""
    if current_user.role in GLOBAL_ROLES:
        return None

    rows = apply_jurisdiction_filter(db.query(models.Case.id), current_user, models.Case).all()
    return {row[0] for row in rows}


def authorize_case_access(case_id: int, current_user: models.User, db: Session) -> models.Case:
    """Fetch a case and verify the user is authorized for its jurisdiction."""
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    if current_user.role in GLOBAL_ROLES:
        return case

    _, case_attr, scope_val, label = _get_user_scope(current_user)
    case_scope_val = getattr(case, case_attr, None)
    if not case_scope_val or case_scope_val != scope_val:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: case belongs to another {label} jurisdiction.",
        )
    return case
