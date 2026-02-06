from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from datetime import datetime
import os
import hashlib
from cryptography.fernet import Fernet
import shutil

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user

from backend import config

router = APIRouter(
    prefix="/files",
    tags=["files"]
)

# Secure storage path
UPLOAD_DIR = "secure_uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

cipher_suite = Fernet(config.ENCRYPTION_KEY)

@router.post("/upload/{case_id}", response_model=schemas.EvidenceResponse)
async def upload_evidence(
    case_id: int,
    file: UploadFile = File(...),
    file_type: str = Form(...), # CDR_CSV, CAF_PDF, etc
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # RBAC Upload Permission
    allowed_uploaders = [
        models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE, 
        models.UserRole.SUB_INSPECTOR, models.UserRole.INSPECTOR, 
        models.UserRole.OFFICER
    ]
    if current_user.role not in allowed_uploaders:
        raise HTTPException(
            status_code=403, 
            detail="You do not have permission to upload evidence."
        )

    # Initial Status Logic
    status = "verified" # Default for SIs and SHOs
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE]:
        status = "pending" # Needs SHO approval

    # Validate Extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type. Allowed: {', '.join(config.ALLOWED_EXTENSIONS)}"
        )
    
    # Verify Case access (scope check)
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    # Optional: Check if user belongs to same station as case (or district)
    # This might already be covered by List Cases visibility, but strictly creating evidence 
    # should probably be same station for Constables.
    if current_user.station_name and case.police_station and current_user.station_name != case.police_station:
         raise HTTPException(status_code=403, detail="Evidence upload restricted to case's Police Station.")

    # Read file content
    content = await file.read()
    
    # FIX: Validate file size
    if len(content) > config.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413, 
            detail=f"File too large. Maximum size: {config.MAX_FILE_SIZE_MB}MB"
        )
    
    # Calculate SHA-256
    sha256_hash = hashlib.sha256(content).hexdigest()
    
    # Check if duplicate hash exists (deduplication or integrity check)
    # optional: if db.query(models.Evidence).filter(models.Evidence.file_hash == sha256_hash).first(): ...

    # Encrypt
    encrypted_content = cipher_suite.encrypt(content)
    
    # Save to disk
    # FIX: Use enhanced filename sanitization
    from backend.utils.validation import sanitize_filename
    cleaned_filename = sanitize_filename(file.filename)
    
    # Filename: {hash}_{original_name} to avoid collisions and obscure basic names
    safe_filename = f"{sha256_hash}_{cleaned_filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    
    with open(file_path, "wb") as f:
        f.write(encrypted_content)
        
    # Create DB Entry
    new_evidence = models.Evidence(
        case_id=case_id,
        file_type=file_type,
        file_path=file_path,
        file_hash=sha256_hash,
        original_filename=file.filename,
        uploaded_by_id=current_user.id,
        # RBAC fields
        uploaded_by_rank=current_user.rank,
        verification_status=status
    )
    db.add(new_evidence)
    
    # Audit Log
    log = models.AuditLog(
        user_id=current_user.id,
        action="UPLOAD_EVIDENCE",
        details=f"Uploaded {file.filename} (Hash: {sha256_hash}) to Case {case.fir_number}"
    )
    db.add(log)
    
    db.commit()
    db.refresh(new_evidence)
    
    return new_evidence

@router.get("/case/{case_id}", response_model=list[schemas.EvidenceResponse])
def get_case_evidence(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    evidence = db.query(models.Evidence).filter(models.Evidence.case_id == case_id).all()
    return evidence

# Optional: Download/Decrypt endpoint (Admin/SHO only?)
@router.get("/download/{evidence_id}")
def download_evidence(
    evidence_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    evidence = db.query(models.Evidence).filter(models.Evidence.id == evidence_id).first()
    if not evidence:
         raise HTTPException(status_code=404, detail="Evidence not found")

    # FIX: Verify user has access to the case
    case = db.query(models.Case).filter(models.Case.id == evidence.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Associated case not found")
    
    # Apply same RBAC logic as case viewing
    role = current_user.role
    has_access = False
    
    if role in [models.UserRole.DGP, models.UserRole.ADMIN]:
        has_access = True
    elif role == models.UserRole.IGP and current_user.zone_name == case.zone_name:
        has_access = True
    elif role == models.UserRole.DIG and current_user.range_name == case.range_name:
        has_access = True
    elif role == models.UserRole.SP and current_user.district_name == case.district_name:
        has_access = True
    elif role == models.UserRole.DY_SP and current_user.sub_division == case.sub_division:
        has_access = True
    elif role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE, 
                  models.UserRole.SUB_INSPECTOR, models.UserRole.INSPECTOR]:
        if current_user.station_name == case.police_station:
            has_access = True
    
    if not has_access:
        raise HTTPException(
            status_code=403, 
            detail="Access denied: You do not have permission to access this evidence"
        )

    # Decrypt
    with open(evidence.file_path, "rb") as f:
        encrypted_data = f.read()
    
    decrypted_data = cipher_suite.decrypt(encrypted_data)
    
    # Return as stream/file
    from fastapi.responses import Response
    return Response(content=decrypted_data, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename={evidence.original_filename}"
    })

@router.get("/view/{evidence_id}")
def view_evidence(
    evidence_id: int,
    token: str, # Pass token as query param for src tags
    db: Session = Depends(get_db)
):
    # Manual Auth since it's a media request (img src, video src)
    # We need to validate the token
    from backend.utils import security
    from jose import jwt, JWTError
    
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication")
        
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid user")

    evidence = db.query(models.Evidence).filter(models.Evidence.id == evidence_id).first()
    if not evidence:
         raise HTTPException(status_code=404, detail="Evidence not found")

    if not os.path.exists(evidence.file_path):
        raise HTTPException(status_code=404, detail="File not found on server")

    # Decrypt
    with open(evidence.file_path, "rb") as f:
        encrypted_data = f.read()
    
    try:
        decrypted_data = cipher_suite.decrypt(encrypted_data)
    except Exception:
        raise HTTPException(status_code=500, detail="Decryption failed")

    # Integrity Check
    current_hash = hashlib.sha256(decrypted_data).hexdigest()
    if current_hash != evidence.file_hash:
        # Audit Tampering
        log = models.AuditLog(
            user_id=user.id,
            action="INTEGRITY_FAILURE",
            details=f"Hash mismatch for Evidence #{evidence.id} ({evidence.original_filename})"
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=409, detail="Evidence Integrity Check Failed: File may have been tampered with.")

    # Determine MIME type
    import mimetypes
    mimetypes.init()
    media_type, _ = mimetypes.guess_type(evidence.original_filename)
    if not media_type:
        media_type = "application/octet-stream"

    # Audit Log - View
    log = models.AuditLog(
        user_id=user.id,
        action="VIEW_EVIDENCE",
        details=f"Viewed Evidence #{evidence.id} ({evidence.original_filename})"
    )
    db.add(log)
    db.commit()
    
    from fastapi.responses import Response
    return Response(content=decrypted_data, media_type=media_type, headers={"Content-Disposition": f"inline; filename=\"{evidence.original_filename}\""})
