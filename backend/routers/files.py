from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from datetime import datetime
import os
import hashlib
from cryptography.fernet import Fernet, MultiFernet
import shutil

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user
from backend.utils.audit import record_audit_log
from backend.utils.cdr_indexer import index_cdr_bytes
from backend.utils.pdf_gen import generate_bsa_63_manifest
from backend.utils.rbac import authorize_case_access
from backend.utils.validation import sanitize_filename, validate_file_magic_and_zip

from backend import config

router = APIRouter(
    prefix="/files",
    tags=["files"]
)

# Secure storage path
UPLOAD_DIR = "data/secure_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

cipher_suite = MultiFernet([Fernet(k) for k in config.ENCRYPTION_KEYS])

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

    # Validate Extension & reject path traversal sequences
    raw_filename = file.filename or ""
    if ".." in raw_filename or "/" in raw_filename or "\\" in raw_filename:
        raise HTTPException(status_code=400, detail="Invalid filename path")
    file_ext = os.path.splitext(raw_filename)[1].lower()
    if file_ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type. Allowed: {', '.join(config.ALLOWED_EXTENSIONS)}"
        )
    
    # Verify Case access (fail-closed jurisdiction check)
    case = authorize_case_access(case_id, current_user, db)

    # Read file content
    content = await file.read()
    
    # Validate file size
    if len(content) > config.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413, 
            detail=f"File too large. Maximum size: {config.MAX_FILE_SIZE_MB}MB"
        )

    # Validate magic bytes & anti-zip-bomb limits
    is_safe, safety_err = validate_file_magic_and_zip(content, file_ext)
    if not is_safe:
        raise HTTPException(status_code=400, detail=safety_err)
    
    # Calculate SHA-256, encrypt, and write in threadpool to avoid blocking event loop
    def _encrypt_and_store() -> tuple[str, str, str]:
        digest = hashlib.sha256(content).hexdigest()
        encrypted_content = cipher_suite.encrypt(content)
        cleaned = sanitize_filename(file.filename)
        safe_name = f"{digest}_{cleaned}"
        target_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(target_path, "wb") as f:
            f.write(encrypted_content)
        return digest, target_path, cleaned

    sha256_hash, file_path, cleaned_filename = await run_in_threadpool(_encrypt_and_store)
        
    # Create DB Entry
    new_evidence = models.Evidence(
        case_id=case_id,
        file_type=file_type,
        file_path=file_path,
        file_hash=sha256_hash,
        original_filename=cleaned_filename,
        uploaded_by_id=current_user.id,
        # RBAC fields
        uploaded_by_rank=current_user.rank,
        verification_status=status
    )
    db.add(new_evidence)
    
    # Hash-chained Audit Log
    record_audit_log(
        db,
        user_id=current_user.id,
        action="UPLOAD_EVIDENCE",
        details=f"Uploaded {cleaned_filename} (Hash: {sha256_hash}) to Case {case.fir_number}",
    )
    
    db.commit()
    db.refresh(new_evidence)

    # Index CDR MSISDN/IMEI rows for Universal Search if tabular CDR
    if file_ext in (".csv", ".xlsx", ".xls") or "CDR" in (file_type or "").upper():
        await run_in_threadpool(index_cdr_bytes, db, case_id, new_evidence.id, content, cleaned_filename)
    
    return new_evidence


@router.get("/case/{case_id}/bsa63-manifest")
def export_bsa63_manifest(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Export a Section 63(4)(c) BSA, 2023 electronic evidence hash manifest for a case."""
    case = authorize_case_access(case_id, current_user, db)
    evidence_rows = db.query(models.Evidence).filter(models.Evidence.case_id == case_id).all()
    records = [
        {
            "id": ev.id,
            "original_filename": ev.original_filename,
            "file_type": ev.file_type,
            "file_hash": ev.file_hash,
            "uploaded_at": ev.uploaded_at,
            "uploaded_by": ev.uploader.username if ev.uploader else "Unknown",
            "verification_status": ev.verification_status,
        }
        for ev in evidence_rows
    ]
    return generate_bsa_63_manifest(
        {"fir_number": case.fir_number, "police_station": case.police_station},
        records,
        generated_by=f"{current_user.username} ({(current_user.rank or current_user.role.value).upper()})",
    )

@router.get("/case/{case_id}", response_model=list[schemas.EvidenceResponse])
def get_case_evidence(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    authorize_case_access(case_id, current_user, db)
    evidence = db.query(models.Evidence).filter(models.Evidence.case_id == case_id).all()
    return evidence

# Download/Decrypt endpoint
@router.get("/download/{evidence_id}")
def download_evidence(
    evidence_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    evidence = db.query(models.Evidence).filter(models.Evidence.id == evidence_id).first()
    if not evidence:
         raise HTTPException(status_code=404, detail="Evidence not found")

    authorize_case_access(evidence.case_id, current_user, db)

    # Decrypt
    with open(evidence.file_path, "rb") as f:
        encrypted_data = f.read()
    
    decrypted_data = cipher_suite.decrypt(encrypted_data)
    
    # Return as stream/file
    from fastapi.responses import Response
    safe_dl_name = sanitize_filename(evidence.original_filename)
    return Response(content=decrypted_data, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{safe_dl_name}"'
    })

@router.get("/view/{evidence_id}")
def view_evidence(
    evidence_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    evidence = db.query(models.Evidence).filter(models.Evidence.id == evidence_id).first()
    if not evidence:
         raise HTTPException(status_code=404, detail="Evidence not found")

    authorize_case_access(evidence.case_id, current_user, db)
    user = current_user

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
        record_audit_log(
            db,
            user_id=user.id,
            action="INTEGRITY_FAILURE",
            details=f"Hash mismatch for Evidence #{evidence.id} ({evidence.original_filename})",
            commit=True,
        )
        raise HTTPException(status_code=409, detail="Evidence Integrity Check Failed: File may have been tampered with.")

    # Determine MIME type
    import mimetypes
    mimetypes.init()
    media_type, _ = mimetypes.guess_type(evidence.original_filename)
    if not media_type:
        media_type = "application/octet-stream"

    # Audit Log - View
    record_audit_log(
        db,
        user_id=user.id,
        action="VIEW_EVIDENCE",
        details=f"Viewed Evidence #{evidence.id} ({evidence.original_filename})",
        commit=True,
    )
    
    from fastapi.responses import Response
    safe_view_name = sanitize_filename(evidence.original_filename)
    return Response(content=decrypted_data, media_type=media_type, headers={"Content-Disposition": f'inline; filename="{safe_view_name}"'})
