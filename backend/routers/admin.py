from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user
from backend.utils.audit import verify_audit_chain

router = APIRouter(
    prefix="/admin",
    tags=["admin"]
)

# Response Schema for Logs (Create locally since it's admin specific)
from pydantic import BaseModel, ConfigDict

class AuditLogOut(BaseModel):
    id: int
    user: str
    action: str
    details: Optional[str]
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

@router.get("/logs", response_model=List[AuditLogOut])
def get_audit_logs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    allowed_roles = {
        models.UserRole.ADMIN,
        models.UserRole.INSPECTOR,  # SHO
        models.UserRole.SP,
        models.UserRole.DGP,
    }
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only SHO, SP, DGP, or Admin can view audit logs."
        )

    query = db.query(models.AuditLog).join(models.User, models.AuditLog.user_id == models.User.id)

    if current_user.role == models.UserRole.INSPECTOR:
        if not current_user.station_name:
            raise HTTPException(status_code=403, detail="Jurisdiction not assigned (station).")
        query = query.filter(models.User.station_name == current_user.station_name)
    elif current_user.role == models.UserRole.SP:
        if not current_user.district_name:
            raise HTTPException(status_code=403, detail="Jurisdiction not assigned (district).")
        query = query.filter(models.User.district_name == current_user.district_name)

    logs = query.order_by(models.AuditLog.timestamp.desc()).limit(100).all()
    
    # Transform for simpler frontend consumption
    results = []
    for log in logs:
        results.append({
            "id": log.id,
            "user": log.user.username if log.user else "Unknown",
            "action": log.action,
            "details": log.details,
            "timestamp": log.timestamp
        })
    return results


@router.get("/logs/verify")
def verify_logs_chain(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    if current_user.role not in {models.UserRole.ADMIN, models.UserRole.DGP}:
        raise HTTPException(status_code=403, detail="Only Admin or DGP can verify full audit chain.")
    return verify_audit_chain(db)
