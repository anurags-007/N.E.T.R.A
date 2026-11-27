from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user
from backend.nodal_contacts import get_bank_nodal_email, get_all_banks
from backend.utils.audit import record_audit_log
from backend.utils.rbac import authorize_case_access, get_accessible_case_ids

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
    # Verify case exists and user has jurisdiction access
    case = authorize_case_access(case_id, current_user, db)
    
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
    record_audit_log(
        db,
        user_id=current_user.id,
        action=f"Created bank request for case {case.fir_number}",
        details=f"Bank: {request.bank_name}, Type: {request.request_type}",
        commit=True,
    )
    
    return new_request

@router.get("/requests/", response_model=List[schemas.BankRequestResponse])
def get_bank_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all bank requests (filtered by user access)
    """
    accessible_case_ids = get_accessible_case_ids(current_user, db)

    query = db.query(models.BankRequest)
    if accessible_case_ids is not None:
        if not accessible_case_ids:
            return []
        query = query.filter(models.BankRequest.case_id.in_(accessible_case_ids))

    requests = query.order_by(models.BankRequest.created_at.desc()).offset(skip).limit(limit).all()
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
    authorize_case_access(request.case_id, current_user, db)
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
                             models.UserRole.SUB_INSPECTOR, models.UserRole.OFFICER]:
        raise HTTPException(status_code=403, detail="Only SHO and above can approve bank requests")
    
    request = db.query(models.BankRequest).filter(models.BankRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Bank request not found")
    authorize_case_access(request.case_id, current_user, db)
    if request.status != models.RequestStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Cannot approve bank request in '{request.status.value}' state")
    
    request.status = models.RequestStatus.APPROVED
    request.reviewer_id = current_user.id
    request.reviewed_at = func.now()
    
    db.commit()
    db.refresh(request)
    
    # Log action
    record_audit_log(
        db,
        user_id=current_user.id,
        action=f"Approved bank request #{request_id}",
        details=f"Bank: {request.bank_name}",
        commit=True,
    )
    
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
                             models.UserRole.SUB_INSPECTOR, models.UserRole.OFFICER]:
        raise HTTPException(status_code=403, detail="Only SHO and above can reject bank requests")
    
    request = db.query(models.BankRequest).filter(models.BankRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Bank request not found")
    authorize_case_access(request.case_id, current_user, db)
    if request.status != models.RequestStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Cannot reject bank request in '{request.status.value}' state")
    
    request.status = models.RequestStatus.REJECTED
    request.reviewer_id = current_user.id
    request.reviewed_at = func.now()
    request.rejection_reason = reason
    
    db.commit()
    db.refresh(request)
    record_audit_log(
        db,
        user_id=current_user.id,
        action=f"Rejected bank request #{request_id}",
        details=f"Bank: {request.bank_name}, Reason: {reason[:200]}",
        commit=True,
    )
    
    return request

@router.get("/nodal/banks")
def get_supported_banks(current_user: models.User = Depends(get_current_active_user)):
    """Get list of all banks with nodal officer contacts"""
    return {"banks": get_all_banks()}

@router.get("/nodal/email/{bank_name}")
def get_bank_nodal_contact(bank_name: str, current_user: models.User = Depends(get_current_active_user)):
    """Get nodal officer email for a specific bank"""
    email = get_bank_nodal_email(bank_name)
    return {"bank": bank_name, "nodal_email": email}
