from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status, File, UploadFile
from starlette.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import os

from backend.database import get_db
from backend import config, models, schemas
from backend.routers.auth import get_current_active_user
from backend.utils.audit import record_audit_log
from backend.utils.pdf_gen import generate_request_pdf
from backend.utils.rbac import authorize_case_access, get_accessible_case_ids
from backend.utils.validation import read_upload_with_limit, sanitize_filename, validate_file_magic_and_zip

router = APIRouter(
    prefix="/requests",
    tags=["requests"]
)

REQUESTS_DIR = "data/generated_requests"
os.makedirs(REQUESTS_DIR, exist_ok=True)

@router.post("/", response_model=schemas.RequestResponse)
def create_request(
    request: schemas.RequestCreate,
    case_id: int, # Pass as query param or body? Let's assume body for now, but simplified in schema to just fields. Let's take case_id as query for clarity.
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # Verify Case & jurisdiction (fail-closed)
    case = authorize_case_access(case_id, current_user, db)
    
    # Create DB Entry
    new_request = models.TelecomRequest(
        case_id=case_id,
        mobile_number=request.mobile_number,
        request_type=request.request_type,
        reason=request.reason,
        status=models.RequestStatus.PENDING
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    # Generate PDF (Simplification: Auto-generate on create, even if pending approval. Or maybe AFTER approval? Plan said "System Automatically Generates... Is legally mandatory". Usually generated then signed. Let's gen it now.)
    # Generate PDF safely inside REQUESTS_DIR
    safe_mobile = sanitize_filename(request.mobile_number)
    file_name = f"REQ_{new_request.id}_{safe_mobile}.pdf"
    file_path = os.path.join(REQUESTS_DIR, file_name)
    if not os.path.abspath(file_path).startswith(os.path.abspath(REQUESTS_DIR) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    generate_request_pdf(
        request_data={"id": new_request.id, "mobile_number": request.mobile_number, "request_type": request.request_type, "reason": request.reason},
        case_data={"fir_number": case.fir_number, "police_station": case.police_station},
        officer_name=current_user.username, # Ideally full name
        output_path=file_path
    )
    
    new_request.request_file_path = file_path
    db.commit()

    return new_request

@router.post("/batch", response_model=List[schemas.RequestResponse])
def create_batch_request(
    batch: schemas.RequestBatchCreate,
    case_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Intelligently groups mobile numbers by TSP and generates consolidated notices.
    """
    # Verify Case & jurisdiction (fail-closed)
    case = authorize_case_access(case_id, current_user, db)
        
    created_requests = []
    
    # 1. Group Numbers by TSP (Mock Logic for Demo)
    tsp_groups = {} # Map: "Airtel" -> ["98xx", "99xx"]
    
    for mobile in batch.mobile_numbers:
        clean_mob = mobile.strip()
        if not clean_mob: continue
        
        # Simple Prefix Logic
        prefix = clean_mob[0:2]
        tsp = "Unknown TSP"
        if prefix in ['98', '99', '90', '95']: tsp = "Airtel"
        elif prefix in ['63', '70', '71', '72', '73', '74', '75', '76', '77', '78', '79']: tsp = "Jio"
        elif prefix in ['80', '81', '82', '83', '84', '85', '86', '87', '88', '89']: tsp = "Vodafone Idea"
        elif prefix in ['94']: tsp = "BSNL"
        
        if tsp not in tsp_groups:
            tsp_groups[tsp] = []
        tsp_groups[tsp].append(clean_mob)
        
    # 2. Create One Request per TSP containing ALL numbers
    for tsp, mobiles in tsp_groups.items():
        # Store numbers as comma-separated string in DB
        combined_mobiles = ", ".join(mobiles)
        
        new_request = models.TelecomRequest(
            case_id=case_id,
            mobile_number=combined_mobiles, # Storing BATCH string
            request_type=batch.request_type,
            reason=f"[{tsp} BATCH] {batch.reason}",
            status=models.RequestStatus.PENDING
        )
        db.add(new_request)
        db.commit()
        db.refresh(new_request)
        
        # 3. Generate Consolidated PDF
        file_name = f"REQ_{new_request.id}_BATCH_{tsp.replace(' ', '_')}.pdf"
        file_path = os.path.join(REQUESTS_DIR, file_name)
        
        generate_request_pdf(
            request_data={
                "id": new_request.id, 
                "mobile_number": combined_mobiles, 
                "request_type": batch.request_type, 
                "reason": batch.reason
            },
            case_data={"fir_number": case.fir_number, "police_station": case.police_station},
            officer_name=current_user.username,
            output_path=file_path
        )
        
        new_request.request_file_path = file_path
        db.commit()
        created_requests.append(new_request)
        
    return created_requests

@router.get("/", response_model=List[schemas.RequestResponse])
def read_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    case_id: int = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    query = db.query(models.TelecomRequest)
    if case_id is not None:
        authorize_case_access(case_id, current_user, db)
        query = query.filter(models.TelecomRequest.case_id == case_id)
    else:
        accessible_ids = get_accessible_case_ids(current_user, db)
        if accessible_ids is not None:
            if not accessible_ids:
                return []
            query = query.filter(models.TelecomRequest.case_id.in_(accessible_ids))
    
    requests = query.offset(skip).limit(limit).all()
    return requests

@router.post("/{request_id}/approve", response_model=schemas.RequestResponse)
def approve_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # FIX: Use INSPECTOR role (which has value 'sho'), not SHO
    # Also allow higher ranks to approve
    allowed_approvers = [
        models.UserRole.INSPECTOR,  # Station House Officer
        models.UserRole.DY_SP,      # Deputy SP
        models.UserRole.SP,         # Superintendent of Police
        models.UserRole.DIG,        # Deputy Inspector General
        models.UserRole.IGP,        # Inspector General
        models.UserRole.DGP,        # Director General
        models.UserRole.ADMIN       # System Admin
    ]
    
    if current_user.role not in allowed_approvers:
         raise HTTPException(
             status_code=403, 
             detail="Only Inspector (SHO) and above can approve requests"
         )

    req = db.query(models.TelecomRequest).filter(models.TelecomRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    authorize_case_access(req.case_id, current_user, db)
    if req.status != models.RequestStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Cannot approve request in '{req.status.value}' state")

    req.status = models.RequestStatus.APPROVED
    req.reviewer_id = current_user.id
    req.reviewed_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(req)
    record_audit_log(
        db,
        user_id=current_user.id,
        action=f"Approved telecom request #{request_id}",
        details=f"Mobile: {req.mobile_number}, Type: {req.request_type}",
        commit=True,
    )
    return req

@router.post("/{request_id}/reject", response_model=schemas.RequestResponse)
def reject_request(
    request_id: int,
    reason: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # FIX: Use INSPECTOR role (which has value 'sho'), not SHO
    allowed_approvers = [
        models.UserRole.INSPECTOR,  # Station House Officer
        models.UserRole.DY_SP, models.UserRole.SP,
        models.UserRole.DIG, models.UserRole.IGP, models.UserRole.DGP,
        models.UserRole.ADMIN
    ]
    
    if current_user.role not in allowed_approvers:
         raise HTTPException(
             status_code=403, 
             detail="Only Inspector (SHO) and above can reject requests"
         )

    req = db.query(models.TelecomRequest).filter(models.TelecomRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    authorize_case_access(req.case_id, current_user, db)
    if req.status != models.RequestStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Cannot reject request in '{req.status.value}' state")
    
    req.status = models.RequestStatus.REJECTED
    req.reviewer_id = current_user.id
    req.reviewed_at = datetime.now(timezone.utc)
    req.rejection_reason = reason
    
    db.commit()
    db.refresh(req)
    record_audit_log(
        db,
        user_id=current_user.id,
        action=f"Rejected telecom request #{request_id}",
        details=f"Reason: {reason[:200]}",
        commit=True,
    )
    return req

@router.get("/{request_id}/download")
def download_request_pdf(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    req = db.query(models.TelecomRequest).filter(models.TelecomRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    authorize_case_access(req.case_id, current_user, db)
    
    # Check if file exists (including fallback if DB holds legacy relative path)
    file_path = req.request_file_path
    if file_path and not os.path.exists(file_path):
        fallback_path = os.path.join(REQUESTS_DIR, os.path.basename(file_path))
        if os.path.exists(fallback_path):
            file_path = fallback_path

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Requisition PDF not found")
    
    return FileResponse(
        file_path,
        media_type='application/pdf',
        filename=os.path.basename(file_path)
    )

@router.post("/{request_id}/upload")
async def upload_request_file(
    request_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    req = db.query(models.TelecomRequest).filter(models.TelecomRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    authorize_case_access(req.case_id, current_user, db)
    
    # Save the file safely inside REQUESTS_DIR
    raw_name = file.filename or ""
    if ".." in raw_name or "/" in raw_name or "\\" in raw_name:
        raise HTTPException(status_code=400, detail="Invalid filename path")
    ext = os.path.splitext(raw_name)[1].lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(sorted(config.ALLOWED_EXTENSIONS))}",
        )

    content = await read_upload_with_limit(file, config.MAX_FILE_SIZE_BYTES)

    is_safe, safety_err = validate_file_magic_and_zip(content, ext)
    if not is_safe:
        raise HTTPException(status_code=400, detail=safety_err)

    safe_mobile = sanitize_filename(req.mobile_number)
    file_name = sanitize_filename(f"RESULT_{request_id}_{safe_mobile}{ext}")
    file_path = os.path.join(REQUESTS_DIR, file_name)
    if not os.path.abspath(file_path).startswith(os.path.abspath(REQUESTS_DIR) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid file path")

    def _write_result():
        with open(file_path, "wb") as buffer:
            buffer.write(content)

    await run_in_threadpool(_write_result)
    
    # Preserve original signed requisition PDF in request_file_path; store uploaded response separately
    req.result_file_path = file_path
    db.commit()
    
    return {"message": "File uploaded successfully", "result_file_path": file_path}

@router.post("/{request_id}/dispatch")
def mark_request_dispatched(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    req = db.query(models.TelecomRequest).filter(models.TelecomRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    authorize_case_access(req.case_id, current_user, db)
    
    # Only approved requests can be dispatched
    if req.status != models.RequestStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only approved requests can be marked as sent")
        
    req.status = models.RequestStatus.DISPATCHED
    db.commit()
    db.refresh(req)
    record_audit_log(
        db,
        user_id=current_user.id,
        action=f"Dispatched telecom request #{request_id}",
        details=f"Mobile: {req.mobile_number}",
        commit=True,
    )
    
    return req
