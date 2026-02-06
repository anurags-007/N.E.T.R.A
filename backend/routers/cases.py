from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user

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
    return new_case

@router.get("/", response_model=List[schemas.CaseResponse])
def read_cases(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    query = db.query(models.Case)
    
    # RBAC Filtering
    role = current_user.role
    
    # Level 1: Station Level (Constable, Head Constable, SI, SHO)
    if role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE, models.UserRole.SUB_INSPECTOR, models.UserRole.INSPECTOR]:
        if current_user.station_name:
            query = query.filter(models.Case.police_station == current_user.station_name)
    
    # Level 2: Sub-Division (CO / DySP)
    elif role == models.UserRole.DY_SP:
        if current_user.sub_division:
            query = query.filter(models.Case.sub_division == current_user.sub_division)
            
    # Level 2: District (SP)
    elif role == models.UserRole.SP:
        if current_user.district_name:
            query = query.filter(models.Case.district_name == current_user.district_name)

    # Level 3: Range (DIG)
    elif role == models.UserRole.DIG:
        if current_user.range_name:
            query = query.filter(models.Case.range_name == current_user.range_name)
            
    # Level 3: Zone (IGP)
    elif role == models.UserRole.IGP:
        if current_user.zone_name:
            query = query.filter(models.Case.zone_name == current_user.zone_name)
            
    # Level 3: State (DGP)
    elif role == models.UserRole.DGP:
        pass # See all
        
    # Legacy/Admin
    elif role in [models.UserRole.ADMIN, models.UserRole.OFFICER]:
        pass # Allow visibility for now
        
    cases = query.order_by(models.Case.created_at.desc()).offset(skip).limit(limit).all()
    return cases

@router.get("/{case_id}", response_model=schemas.CaseResponse)
def read_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
        
    # Check RBAC for viewing specific case
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE, models.UserRole.SUB_INSPECTOR, models.UserRole.INSPECTOR]:
        if case.police_station != current_user.station_name:
             raise HTTPException(status_code=403, detail="Access denied. Case belongs to another jurisdiction.")
             
    elif current_user.role == models.UserRole.DY_SP:
        if case.sub_division != current_user.sub_division:
             raise HTTPException(status_code=403, detail="Access denied. Case outside sub-division.")

    elif current_user.role == models.UserRole.SP:
        if case.district_name != current_user.district_name:
             raise HTTPException(status_code=403, detail="Access denied. Case outside district.")
             
    elif current_user.role == models.UserRole.DIG:
        if case.range_name != current_user.range_name:
             raise HTTPException(status_code=403, detail="Access denied. Case outside range.")
             
    elif current_user.role == models.UserRole.IGP:
        if case.zone_name != current_user.zone_name:
             raise HTTPException(status_code=403, detail="Access denied. Case outside zone.")
             
    return case

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
        
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    # Additional Check: Ownership or Superior
    # Simple check: If not owner and not SHO/SP+, block?
    # For now, trust the role check + station scope (if we enforced read scope, they can only access visible cases)
    
    case.status = status_update.status
    db.commit()
    db.refresh(case)
    return case
