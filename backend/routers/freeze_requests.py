from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user
from backend.nodal_contacts import get_bank_nodal_email

router = APIRouter(
    prefix="/freeze",
    tags=["freeze_requests"]
)

@router.post("/request/{case_id}", response_model=schemas.FreezeRequestResponse)
def create_freeze_request(
    case_id: int,
    request: schemas.FreezeRequestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Create urgent account freeze request (Section 102 CrPC)
    Golden Hour Response for Financial Fraud
    """
    # Verify case exists
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Verify financial entity
    financial_entity = db.query(models.FinancialEntity).filter(
        models.FinancialEntity.id == request.financial_entity_id,
        models.FinancialEntity.case_id == case_id
    ).first()
    if not financial_entity:
        raise HTTPException(status_code=400, detail="Financial entity not found")
    
    # Authorization: Only SI and above (freeze requests are time-critical)
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE]:
        raise HTTPException(
            status_code=403, 
            detail="Not authorized to create freeze requests. Contact your SHO."
        )
    
    # Create freeze request
    new_freeze = models.FreezeRequest(
        case_id=case_id,
        financial_entity_id=request.financial_entity_id,
        bank_name=request.bank_name,
        account_number=request.account_number,
        urgency_level=request.urgency_level,
        justification=request.justification,
        status="generated"
    )
    
    db.add(new_freeze)
    db.commit()
    db.refresh(new_freeze)
    
    # Log action (CRITICAL - Audit trail for legal proceedings)
    audit = models.AuditLog(
        user_id=current_user.id,
        action=f"🚨 URGENT: Account freeze request generated for case {case.fir_number}",
        details=f"Bank: {request.bank_name}, Account: ***{request.account_number[-4:]}, Urgency: {request.urgency_level}"
    )
    db.add(audit)
    db.commit()
    
    return new_freeze

@router.get("/requests/", response_model=List[schemas.FreezeRequestResponse])
def get_freeze_requests(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all freeze requests (filtered by user access)
    """
    # Get accessible case IDs (RBAC filtering)
    cases_query = db.query(models.Case)
    
    role = current_user.role
    if role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE, 
                models.UserRole.SUB_INSPECTOR, models.UserRole.INSPECTOR]:
        if current_user.station_name:
            cases_query = cases_query.filter(models.Case.police_station == current_user.station_name)
    elif role == models.UserRole.DY_SP:
        if current_user.sub_division:
            cases_query = cases_query.filter(models.Case.sub_division == current_user.sub_division)
    elif role == models.UserRole.SP:
        if current_user.district_name:
            cases_query = cases_query.filter(models.Case.district_name == current_user.district_name)
    elif role == models.UserRole.DIG:
        if current_user.range_name:
            cases_query = cases_query.filter(models.Case.range_name == current_user.range_name)
    elif role == models.UserRole.IGP:
        if current_user.zone_name:
            cases_query = cases_query.filter(models.Case.zone_name == current_user.zone_name)
    
    accessible_case_ids = [c.id for c in cases_query.all()]
    
    # Get freeze requests
    requests = db.query(models.FreezeRequest).filter(
        models.FreezeRequest.case_id.in_(accessible_case_ids)
    ).order_by(models.FreezeRequest.created_at.desc()).offset(skip).limit(limit).all()
    
    return requests

@router.get("/requests/{request_id}", response_model=schemas.FreezeRequestResponse)
def get_freeze_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get specific freeze request"""
    request = db.query(models.FreezeRequest).filter(models.FreezeRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Freeze request not found")
    return request

@router.patch("/requests/{request_id}/status")
def update_freeze_status(
    request_id: int,
    status: str,  # sent, confirmed, expired
    bank_reference: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Update freeze request status when bank responds
    """
    request = db.query(models.FreezeRequest).filter(models.FreezeRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Freeze request not found")
    
    request.status = status
    
    if status == "sent":
        request.freeze_initiated_at = func.now()
    elif status == "confirmed":
        request.freeze_confirmed_at = func.now()
        if bank_reference:
            request.bank_reference_number = bank_reference
    
    db.commit()
    db.refresh(request)
    
    # Log action
    audit = models.AuditLog(
        user_id=current_user.id,
        action=f"Updated freeze request #{request_id} status to: {status}",
        details=f"Bank Ref: {bank_reference}" if bank_reference else "No bank reference"
    )
    db.add(audit)
    db.commit()
    
    return {"status": "updated", "freeze_request": request}
