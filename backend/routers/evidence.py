from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
import os
import uuid
from cryptography.fernet import Fernet, MultiFernet

from backend import config, models
from backend.database import get_db
from backend.routers.auth import get_current_active_user
from backend.utils.evidence_analysis import process_file
from backend.utils.rbac import authorize_case_access
from backend.utils.validation import sanitize_filename

router = APIRouter(prefix="/evidence", tags=["evidence"])

UPLOAD_DIR = "data/secure_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
cipher_suite = MultiFernet([Fernet(k) for k in config.ENCRYPTION_KEYS])


@router.post("/upload")
async def upload_evidence(
    case_id: int = Form(...),
    file: UploadFile = File(...),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Authenticated, jurisdiction-scoped fallback evidence analyzer endpoint."""
    authorize_case_access(case_id, current_user, db)

    raw_name = file.filename or "uploaded_evidence"
    ext = os.path.splitext(raw_name)[1].lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(sorted(config.ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > config.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {config.MAX_FILE_SIZE_MB}MB",
        )

    safe_name = sanitize_filename(raw_name)
    uid = uuid.uuid4().hex
    dest_path = os.path.join(UPLOAD_DIR, f"{uid}_{safe_name}")
    if not os.path.abspath(dest_path).startswith(os.path.abspath(UPLOAD_DIR) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid filename path")

    # Analyze and store encrypted copy in threadpool
    def _process_and_encrypt() -> dict:
        temp_path = os.path.join(UPLOAD_DIR, f".tmp_{uid}_{safe_name}")
        try:
            with open(temp_path, "wb") as tmp_f:
                tmp_f.write(content)
            parsed = process_file(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        encrypted = cipher_suite.encrypt(content)
        with open(dest_path, "wb") as out_f:
            out_f.write(encrypted)
        return parsed

    result = await run_in_threadpool(_process_and_encrypt)

    result.setdefault("Notes", "")
    result["Notes"] = (result.get("Notes") + " ").strip()
    result["Stored Copy Path"] = dest_path
    return JSONResponse(content=result)
