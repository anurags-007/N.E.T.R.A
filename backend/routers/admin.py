from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user

router = APIRouter(
    prefix="/admin",
    tags=["admin"]
)

# Response Schema for Logs (Create locally since it's admin specific)
from pydantic import BaseModel

class AuditLogOut(BaseModel):
    id: int
    user: str
    action: str
    details: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True

@router.get("/logs", response_model=List[AuditLogOut])
def get_audit_logs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # Optional: Restrict to SHO/Admin
    # if current_user.role != models.UserRole.SHO: ...
    
    logs = db.query(models.AuditLog).order_by(models.AuditLog.timestamp.desc()).limit(100).all()
    
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
