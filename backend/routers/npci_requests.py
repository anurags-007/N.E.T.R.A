from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user
from backend.nodal_contacts import get_upi_nodal_email

router = APIRouter(
    prefix="/npci",
    tags=["npci_requests"]
)

@router.post("/requests/{case_id}", response_model=schemas.NPCIRequestResponse)
def create_npci_request(
    case_id: int,
    request: schemas.NPCIRequestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Create an NPCI/UPI data request
    """
    # Verify case exists
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
    
    # Authorization: Only SI and above
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE]:
        raise HTTPException(status_code=403, detail="Not authorized to create NPCI requests")
    
    # Create NPCI request
    new_request = models.NPCIRequest(
        case_id=case_id,
        financial_entity_id=request.financial_entity_id,
        upi_id=request.upi_id,
        transaction_reference=request.transaction_reference,
        request_type=request.request_type,
        reason=request.reason,
        status=models.RequestStatus.PENDING
    )
    
    db.add(new_request)
    db.commit()
    db.refresh(new_request)
    
    # Log action
    audit = models.AuditLog(
        user_id=current_user.id,
        action=f"Created NPCI request for case {case.fir_number}",
        details=f"UPI ID: {request.upi_id}, Type: {request.request_type}"
    )
    db.add(audit)
    db.commit()
    
    return new_request

@router.get("/requests/", response_model=List[schemas.NPCIRequestResponse])
def get_npci_requests(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all NPCI requests (filtered by user access)
    """
    # Get accessible case IDs (apply RBAC)
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
    
    # Get NPCI requests for accessible cases
    requests = db.query(models.NPCIRequest).filter(
        models.NPCIRequest.case_id.in_(accessible_case_ids)
    ).order_by(models.NPCIRequest.created_at.desc()).offset(skip).limit(limit).all()
    
    return requests

@router.get("/requests/{request_id}", response_model=schemas.NPCIRequestResponse)
def get_npci_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get specific NPCI request"""
    request = db.query(models.NPCIRequest).filter(models.NPCIRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="NPCI request not found")
    return request

@router.patch("/requests/{request_id}/approve", response_model=schemas.NPCIRequestResponse)
def approve_npci_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Approve an NPCI request (SHO/SP+ only)
    """
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE, 
                             models.UserRole.SUB_INSPECTOR]:
        raise HTTPException(status_code=403, detail="Only SHO and above can approve NPCI requests")
    
    request = db.query(models.NPCIRequest).filter(models.NPCIRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="NPCI request not found")
    
    request.status = models.RequestStatus.APPROVED
    request.reviewer_id = current_user.id
    request.reviewed_at = func.now()
    
    db.commit()
    db.refresh(request)
    
    # Log action
    audit = models.AuditLog(
        user_id=current_user.id,
        action=f"Approved NPCI request #{request_id}",
        details=f"UPI ID: {request.upi_id}"
    )
    db.add(audit)
    db.commit()
    
    return request

@router.patch("/requests/{request_id}/reject", response_model=schemas.NPCIRequestResponse)
def reject_npci_request(
    request_id: int,
    reason: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Reject an NPCI request (SHO/SP+ only)
    """
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE, 
                             models.UserRole.SUB_INSPECTOR]:
        raise HTTPException(status_code=403, detail="Only SHO and above can reject NPCI requests")
    
    request = db.query(models.NPCIRequest).filter(models.NPCIRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="NPCI request not found")
    
    request.status = models.RequestStatus.REJECTED
    request.reviewer_id = current_user.id
    request.reviewed_at = func.now()
    request.rejection_reason = reason
    
    db.commit()
    db.refresh(request)
    
    return request

@router.get("/nodal/email")
def get_npci_nodal_contact():
    """Get NPCI nodal officer contact"""
    email = get_upi_nodal_email()
    return {"organization": "NPCI", "nodal_email": email}
