import uuid
import json
import asyncio
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from ..config import UPLOAD_DIR, PROCESSED_DIR
from ..utils.pdf_utils import unlock_pdf, protect_pdf, sign_pdf, redact_pdf
from ..utils.validation import validate_upload

router = APIRouter(prefix="/security", tags=["PDF Security"])

@router.post("/unlock")
async def handle_unlock(
    file: UploadFile = File(...),
    password: str = Form(...)
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"unlocked_{task_id}.pdf"
    try:
        await asyncio.to_thread(unlock_pdf, str(in_path), str(out_file), password=password)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to unlock PDF: {str(e)}")
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"unlocked_{task_id}.pdf",
        "file_name": f"unlocked_{file.filename or 'document.pdf'}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/protect")
async def handle_protect(
    file: UploadFile = File(...),
    password: str = Form(...)
):
    if not password or not password.strip():
        raise HTTPException(status_code=400, detail="Password is required to protect the PDF.")
        
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"protected_{task_id}.pdf"
    try:
        await asyncio.to_thread(protect_pdf, str(in_path), str(out_file), password=password.strip())
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"protected_{task_id}.pdf",
        "file_name": f"protected_{file.filename or 'document.pdf'}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/sign")
async def handle_sign(
    file: UploadFile = File(...),
    signatures: str = Form(...)
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    sig_list = []
    if signatures and signatures.strip():
        try:
            parsed = json.loads(signatures)
            if isinstance(parsed, list):
                sig_list = parsed
        except Exception:
            pass
            
    out_file = PROCESSED_DIR / f"signed_{task_id}.pdf"
    try:
        await asyncio.to_thread(sign_pdf, str(in_path), str(out_file), signatures=sig_list)
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"signed_{task_id}.pdf",
        "file_name": f"signed_{file.filename or 'document.pdf'}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/redact")
async def handle_redact(
    file: UploadFile = File(...),
    redactions: Optional[str] = Form("[]"),
    search_terms: Optional[str] = Form(None)
):
    """
    GENUINE PERMANENT REDACTION:
    Uses PyMuPDF apply_redactions() to permanently strip and erase text,
    font characters, vectors, and bitmap pixels from the PDF stream so that no tool
    can recover the redacted content.
    """
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    redactions_list = []
    if redactions:
        try:
            parsed = json.loads(redactions)
            if isinstance(parsed, list):
                redactions_list = parsed
        except Exception:
            pass
            
    terms_list = []
    if search_terms:
        try:
            parsed = json.loads(search_terms)
            if isinstance(parsed, list):
                terms_list = parsed
            elif isinstance(parsed, str):
                terms_list = [parsed]
        except Exception:
            terms_list = [s.strip() for s in search_terms.split(",") if s.strip()]
            
    out_file = PROCESSED_DIR / f"redacted_{task_id}.pdf"
    try:
        await asyncio.to_thread(
            redact_pdf,
            str(in_path),
            str(out_file),
            redactions=redactions_list,
            search_terms=terms_list
        )
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"redacted_{task_id}.pdf",
        "file_name": f"redacted_{file.filename or 'document.pdf'}",
        "size_bytes": out_file.stat().st_size,
        "message": "Sensitive content has been permanently destroyed and purged from the document."
    }
