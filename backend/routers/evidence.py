from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import os
import uuid
import shutil

from backend.utils.evidence_analysis import process_file

router = APIRouter(prefix="/evidence", tags=["evidence"])

UPLOAD_DIR = "secure_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_evidence(file: UploadFile = File(...), case_id: str = Form(None), description: str = Form(None)):
    """Accept an uploaded evidence file, save a copy, and run the analyzer.

    The original uploaded stream is preserved by saving a separate copy to `secure_uploads`.
    The analyzer will only read the saved copy and will not modify the original data.
    """
    filename = file.filename or "uploaded_evidence"
    uid = uuid.uuid4().hex
    dest_name = f"{uid}_{filename}"
    dest_path = os.path.join(UPLOAD_DIR, dest_name)
    try:
        with open(dest_path, "wb") as out_f:
            shutil.copyfileobj(file.file, out_f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")

    # Run analysis (safely handles missing optional dependencies)
    result = process_file(dest_path)

    # Attach basic metadata about storage location (relative path)
    result.setdefault("Notes", "")
    result["Notes"] = (result.get("Notes") + " ").strip()
    result["Stored Copy Path"] = dest_path

    return JSONResponse(content=result)
