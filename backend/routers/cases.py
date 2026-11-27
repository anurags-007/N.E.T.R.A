from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user
from backend.utils.audit import record_audit_log
from backend.utils.rbac import apply_jurisdiction_filter, authorize_case_access, GLOBAL_ROLES

router = APIRouter(
    prefix="/cases",
    tags=["cases"]
)

@router.post("/", response_model=schemas.CaseResponse)
def create_case(
    case: schemas.CaseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # Authorization: Constables, Head Constables, Sub-Inspectors, and Officers can create cases
    if current_user.role not in [
        models.UserRole.CONSTABLE,
        models.UserRole.HEAD_CONSTABLE,
        models.UserRole.SUB_INSPECTOR, 
        models.UserRole.OFFICER
    ]:
        raise HTTPException(
            status_code=403, 
            detail="Only Constables, Head Constables, and Sub-Inspectors can create new cases."
        )

    # Fail closed if station-scoped creator has no assigned station or tries creating in another station
    if current_user.role not in GLOBAL_ROLES:
        if not current_user.station_name:
            raise HTTPException(status_code=403, detail="Jurisdiction not assigned (station).")
        if case.police_station != current_user.station_name:
            raise HTTPException(status_code=403, detail="Cannot create case outside your assigned Police Station.")

    # Check if FIR already exists
    db_case = db.query(models.Case).filter(models.Case.fir_number == case.fir_number).first()
    if db_case:
        raise HTTPException(status_code=400, detail="Case with this FIR number already exists")
    
    # Use police_station from form, fallback to user's profile
    new_case = models.Case(
        fir_number=case.fir_number,
        case_type=case.case_type,
        case_category=case.case_category,
        amount_involved=case.amount_involved,
        description=case.description,
        owner_id=current_user.id,
        # Accept from form
        police_station=case.police_station,
        sub_division=current_user.sub_division or "Central",
        district_name=current_user.district_name or "City",
        range_name=current_user.range_name or "Metro",
        zone_name=current_user.zone_name or "North"
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)
    record_audit_log(
        db,
        user_id=current_user.id,
        action="CREATE_CASE",
        details=f"Created case {new_case.fir_number} at {new_case.police_station}",
        commit=True,
    )
    return new_case

@router.get("/", response_model=List[schemas.CaseResponse])
def read_cases(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    query = apply_jurisdiction_filter(db.query(models.Case), current_user, models.Case)
    cases = query.order_by(models.Case.created_at.desc()).offset(skip).limit(limit).all()
    return cases

@router.get("/{case_id}", response_model=schemas.CaseResponse)
def read_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    return authorize_case_access(case_id, current_user, db)

@router.patch("/{case_id}/status", response_model=schemas.CaseResponse)
def update_case_status(
    case_id: int,
    status_update: schemas.CaseStatusUpdate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # RBAC: Constables cannot close cases
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE]:
        raise HTTPException(status_code=403, detail="Not authorized to update case status.")
        
    case = authorize_case_access(case_id, current_user, db)
    
    old_status = case.status
    case.status = status_update.status
    db.commit()
    db.refresh(case)
    record_audit_log(
        db,
        user_id=current_user.id,
        action="UPDATE_CASE_STATUS",
        details=f"Case {case.fir_number}: {old_status} -> {case.status}",
        commit=True,
    )
    return case
