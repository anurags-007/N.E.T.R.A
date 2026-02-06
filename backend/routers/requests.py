from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user
from backend.utils.pdf_gen import generate_request_pdf

router = APIRouter(
    prefix="/requests",
    tags=["requests"]
)

REQUESTS_DIR = "generated_requests"
if not os.path.exists(REQUESTS_DIR):
    os.makedirs(REQUESTS_DIR)

@router.post("/", response_model=schemas.RequestResponse)
def create_request(
    request: schemas.RequestCreate,
    case_id: int, # Pass as query param or body? Let's assume body for now, but simplified in schema to just fields. Let's take case_id as query for clarity.
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # Verify Case
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
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
    # We need the ID for the filename
    file_name = f"REQ_{new_request.id}_{request.mobile_number}.pdf"
    file_path = os.path.join(REQUESTS_DIR, file_name)
    
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
    # Verify Case
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
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
    skip: int = 0,
    limit: int = 100,
    case_id: int = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    query = db.query(models.TelecomRequest)
    if case_id:
        query = query.filter(models.TelecomRequest.case_id == case_id)
    
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
    
    # MANUAL WORKFLOW REQUESTED
    # Validated with user: Disable auto-stamping. 
    # User will manually download, sign, and upload the file.
    # 
    # original_pdf_gen_logic_commented_out_for_manual_flow
    # if case and req.request_file_path:
    #     from backend.utils.pdf_gen import generate_approved_request_pdf
    #     try:
    #         generate_approved_request_pdf(...)
    #     except Exception as e:
    #         print(f"Warning: Could not regenerate approved PDF: {e}")
    
    req.status = models.RequestStatus.APPROVED
    req.reviewer_id = current_user.id
    req.reviewed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(req)
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
    
    req.status = models.RequestStatus.REJECTED
    req.reviewer_id = current_user.id
    req.reviewed_at = datetime.utcnow()
    req.rejection_reason = reason
    
    db.commit()
    db.refresh(req)
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
    
    # Check if file exists
    if not req.request_file_path or not os.path.exists(req.request_file_path):
         raise HTTPException(status_code=404, detail="Requisition PDF not found")
    
    return FileResponse(
        req.request_file_path,
        media_type='application/pdf',
        filename=os.path.basename(req.request_file_path)
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
    
    # Save the file
    ext = os.path.splitext(file.filename)[1]
    file_name = f"RESULT_{request_id}_{req.mobile_number}{ext}"
    file_path = os.path.join(REQUESTS_DIR, file_name)
    
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    
    # Update request file path to the new one (as it's the most recent state)
    req.request_file_path = file_path
    db.commit()
    
    return {"message": "File uploaded successfully", "file_path": file_path}

@router.post("/{request_id}/dispatch")
def mark_request_dispatched(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    req = db.query(models.TelecomRequest).filter(models.TelecomRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # Only approved requests can be dispatched
    if req.status != models.RequestStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only approved requests can be marked as sent")
        
    req.status = models.RequestStatus.DISPATCHED
    db.commit()
    db.refresh(req)
    
    return req
