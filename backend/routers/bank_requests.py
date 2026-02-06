from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user
from backend.nodal_contacts import get_bank_nodal_email, get_all_banks

router = APIRouter(
    prefix="/bank",
    tags=["bank_requests"]
)

@router.post("/requests/{case_id}", response_model=schemas.BankRequestResponse)
def create_bank_request(
    case_id: int,
    request: schemas.BankRequestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Create a bank data request for KYC or account statements
    """
    # Verify case exists and user has access
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Verify financial entity exists
    financial_entity = db.query(models.FinancialEntity).filter(
        models.FinancialEntity.id == request.financial_entity_id,
        models.FinancialEntity.case_id == case_id
    ).first()
    if not financial_entity:
        raise HTTPException(status_code=400, detail="Financial entity not found for this case")
    
    # Authorization: Only SI and above can create requests
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE]:
        raise HTTPException(status_code=403, detail="Not authorized to create bank requests")
    
    # Create bank request
    new_request = models.BankRequest(
        case_id=case_id,
        financial_entity_id=request.financial_entity_id,
        bank_name=request.bank_name,
        account_number=request.account_number,
        request_type=request.request_type,
        reason=request.reason,
        period_from=request.period_from,
        period_to=request.period_to,
        status=models.RequestStatus.PENDING
    )
    
    db.add(new_request)
    db.commit()
    db.refresh(new_request)
    
    # Log action
    audit = models.AuditLog(
        user_id=current_user.id,
        action=f"Created bank request for case {case.fir_number}",
        details=f"Bank: {request.bank_name}, Type: {request.request_type}"
    )
    db.add(audit)
    db.commit()
    
    return new_request

@router.get("/requests/", response_model=List[schemas.BankRequestResponse])
def get_bank_requests(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all bank requests (filtered by user access)
    """
    # Get all case IDs the user can access
    cases_query = db.query(models.Case)
    
    # Apply RBAC filtering (similar to cases.py)
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
    
    # Get bank requests for accessible cases
    requests = db.query(models.BankRequest).filter(
        models.BankRequest.case_id.in_(accessible_case_ids)
    ).order_by(models.BankRequest.created_at.desc()).offset(skip).limit(limit).all()
    
    return requests

@router.get("/requests/{request_id}", response_model=schemas.BankRequestResponse)
def get_bank_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get specific bank request"""
    request = db.query(models.BankRequest).filter(models.BankRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Bank request not found")
    return request

@router.patch("/requests/{request_id}/approve", response_model=schemas.BankRequestResponse)
def approve_bank_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Approve a bank request (SHO/SP+ only)
    """
    # Authorization: Only SHO and above
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE, 
                             models.UserRole.SUB_INSPECTOR]:
        raise HTTPException(status_code=403, detail="Only SHO and above can approve bank requests")
    
    request = db.query(models.BankRequest).filter(models.BankRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Bank request not found")
    
    request.status = models.RequestStatus.APPROVED
    request.reviewer_id = current_user.id
    request.reviewed_at = func.now()
    
    db.commit()
    db.refresh(request)
    
    # Log action
    audit = models.AuditLog(
        user_id=current_user.id,
        action=f"Approved bank request #{request_id}",
        details=f"Bank: {request.bank_name}"
    )
    db.add(audit)
    db.commit()
    
    return request

@router.patch("/requests/{request_id}/reject", response_model=schemas.BankRequestResponse)
def reject_bank_request(
    request_id: int,
    reason: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Reject a bank request (SHO/SP+ only)
    """
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE, 
                             models.UserRole.SUB_INSPECTOR]:
        raise HTTPException(status_code=403, detail="Only SHO and above can reject bank requests")
    
    request = db.query(models.BankRequest).filter(models.BankRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Bank request not found")
    
    request.status = models.RequestStatus.REJECTED
    request.reviewer_id = current_user.id
    request.reviewed_at = func.now()
    request.rejection_reason = reason
    
    db.commit()
    db.refresh(request)
    
    return request

@router.get("/nodal/banks")
def get_supported_banks():
    """Get list of all banks with nodal officer contacts"""
    return {"banks": get_all_banks()}

@router.get("/nodal/email/{bank_name}")
def get_bank_nodal_contact(bank_name: str):
    """Get nodal officer email for a specific bank"""
    email = get_bank_nodal_email(bank_name)
    return {"bank": bank_name, "nodal_email": email}
