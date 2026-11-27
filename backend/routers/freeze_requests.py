from typing import List, Literal
import os
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user
from backend.nodal_contacts import get_bank_nodal_email
from backend.utils.audit import record_audit_log
from backend.utils.pdf_gen import generate_freeze_order_pdf
from backend.utils.rbac import authorize_case_access, get_accessible_case_ids
from backend.utils.validation import sanitize_filename

FREEZE_PDF_DIR = "data/generated_requests"
os.makedirs(FREEZE_PDF_DIR, exist_ok=True)

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
    Create urgent account freeze request (Section 106 BNSS, 2023)
    Golden Hour Response for Financial Fraud
    """
    # Verify case exists and user has jurisdiction access
    case = authorize_case_access(case_id, current_user, db)
    
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

    os.makedirs(FREEZE_PDF_DIR, exist_ok=True)
    pdf_name = sanitize_filename(f"FREEZE_{new_freeze.id}_{request.account_number}.pdf")
    pdf_path = os.path.join(FREEZE_PDF_DIR, pdf_name)
    generate_freeze_order_pdf(
        freeze_data={
            "id": new_freeze.id,
            "bank_name": request.bank_name,
            "account_number": request.account_number,
            "urgency_level": request.urgency_level,
            "justification": request.justification,
        },
        case_data={"fir_number": case.fir_number, "police_station": case.police_station},
        officer_name=current_user.username,
        output_path=pdf_path,
    )
    new_freeze.request_file_path = pdf_path
    db.commit()
    db.refresh(new_freeze)
    
    # Log action (CRITICAL - Audit trail for legal proceedings)
    record_audit_log(
        db,
        user_id=current_user.id,
        action=f"🚨 URGENT: Account freeze request generated for case {case.fir_number}",
        details=f"Bank: {request.bank_name}, Account: ***{request.account_number[-4:]}, Urgency: {request.urgency_level}",
        commit=True,
    )
    
    return new_freeze

@router.get("/requests/", response_model=List[schemas.FreezeRequestResponse])
def get_freeze_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all freeze requests (filtered by user access)
    """
    accessible_case_ids = get_accessible_case_ids(current_user, db)

    query = db.query(models.FreezeRequest)
    if accessible_case_ids is not None:
        if not accessible_case_ids:
            return []
        query = query.filter(models.FreezeRequest.case_id.in_(accessible_case_ids))

    requests = query.order_by(models.FreezeRequest.created_at.desc()).offset(skip).limit(limit).all()
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
    authorize_case_access(request.case_id, current_user, db)
    return request


@router.get("/requests/{request_id}/download")
def download_freeze_order_pdf(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Download Section 106 BNSS freeze order PDF (jurisdiction-scoped)."""
    freeze_req = db.query(models.FreezeRequest).filter(models.FreezeRequest.id == request_id).first()
    if not freeze_req:
        raise HTTPException(status_code=404, detail="Freeze request not found")
    authorize_case_access(freeze_req.case_id, current_user, db)

    file_path = freeze_req.request_file_path
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Freeze order PDF not found")

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=os.path.basename(file_path),
    )

@router.patch("/requests/{request_id}/status")
def update_freeze_status(
    request_id: int,
    status: Literal["sent", "confirmed", "expired"],  # sent, confirmed, expired
    bank_reference: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Update freeze request status when bank responds (SHO and above only)
    """
    if current_user.role in [
        models.UserRole.CONSTABLE,
        models.UserRole.HEAD_CONSTABLE,
        models.UserRole.SUB_INSPECTOR,
        models.UserRole.OFFICER,
    ]:
        raise HTTPException(status_code=403, detail="Only SHO and above can update freeze request status.")

    request = db.query(models.FreezeRequest).filter(models.FreezeRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Freeze request not found")
    authorize_case_access(request.case_id, current_user, db)
    
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
    record_audit_log(
        db,
        user_id=current_user.id,
        action=f"Updated freeze request #{request_id} status to: {status}",
        details=f"Bank Ref: {bank_reference}" if bank_reference else "No bank reference",
        commit=True,
    )
    
    return {"status": "updated", "freeze_request": request}
