import io
import re
from typing import List, Tuple, Optional
from fastapi import UploadFile, HTTPException
from PIL import Image
import pymupdf
from ..config import MAX_UPLOAD_SIZE

# Magic byte signatures
SIGNATURES = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "gif": [b"GIF87a", b"GIF89a"],
    "webp": [b"RIFF"], # followed by WEBP
    "zip": [b"PK\x03\x04"],
    "docx": [b"PK\x03\x04"],
    "xlsx": [b"PK\x03\x04"],
    "pptx": [b"PK\x03\x04"],
}

async def read_bounded_file(file: UploadFile, max_size: int = MAX_UPLOAD_SIZE) -> bytes:
    """
    Reads an uploaded file in bounded chunks of 64 KB.
    Aborts immediately with HTTP 413 if the file exceeds max_size.
    Prevents memory exhaustion attacks.
    """
    chunk_size = 64 * 1024
    total_bytes = 0
    buffer = io.BytesIO()

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_size:
            max_mb = max_size // (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed upload size of {max_mb} MB."
            )
        buffer.write(chunk)

    data = buffer.getvalue()
    if len(data) == 0:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty (0 bytes)."
        )
    return data

def detect_file_type(data: bytes, filename: Optional[str] = None) -> str:
    """
    Detects file type based on magic bytes header and fallback filename extension.
    """
    header = data[:64]
    
    if header.startswith(b"%PDF-"):
        return "pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "gif"
    if header.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "webp"
    if header.startswith(b"PK\x03\x04"):
        # Could be docx, xlsx, pptx, or generic zip
        ext = (filename or "").lower().split(".")[-1]
        if ext in ("docx", "xlsx", "pptx", "zip"):
            return ext
        return "zip"
    
    # Text / HTML / Markdown check
    try:
        sample = data[:1024].decode("utf-8")
        if re.search(r"<!doctype html|<html|<head|<body", sample, re.IGNORECASE):
            return "html"
        return "text"
    except UnicodeDecodeError:
        pass

    return "unknown"

async def validate_upload(
    file: UploadFile,
    allowed_types: List[str],
    max_size: int = MAX_UPLOAD_SIZE,
    max_pages: int = 500,
    check_pdf_integrity: bool = True
) -> Tuple[bytes, str]:
    """
    Validates uploaded file size, magic bytes, structure and integrity.
    Returns (raw_bytes, detected_extension).
    """
    content = await read_bounded_file(file, max_size=max_size)
    detected = detect_file_type(content, file.filename)
    
    # Normalize allowed types (e.g. "jpeg" -> "jpg")
    norm_allowed = []
    for t in allowed_types:
        t_clean = t.lower().replace(".", "")
        if t_clean == "jpeg":
            norm_allowed.append("jpg")
        else:
            norm_allowed.append(t_clean)
            
    norm_detected = "jpg" if detected == "jpeg" else detected
    
    # Allow office docs that share zip signature
    office_group = {"docx", "xlsx", "pptx", "zip"}
    if norm_detected in office_group and any(ot in office_group for ot in norm_allowed):
        pass # Accept valid openxml / zip format
    elif norm_detected not in norm_allowed and "all" not in norm_allowed:
        allowed_str = ", ".join(norm_allowed).upper()
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{detected}'. Supported formats for this tool: {allowed_str}."
        )

    # In-depth PDF validation
    if norm_detected == "pdf" and check_pdf_integrity:
        try:
            doc = pymupdf.open(stream=content, filetype="pdf")
            page_count = len(doc)
            if page_count == 0:
                raise HTTPException(status_code=400, detail="Uploaded PDF contains 0 pages.")
            if page_count > max_pages:
                raise HTTPException(
                    status_code=400,
                    detail=f"PDF document exceeds maximum allowed page count ({max_pages} pages). Document contains {page_count} pages."
                )
            doc.close()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Uploaded PDF is corrupted or invalid: {str(e)}"
            )

    # In-depth image validation
    if norm_detected in ("jpg", "png", "gif", "webp"):
        try:
            with Image.open(io.BytesIO(content)) as img:
                w, h = img.size
                if w > 10000 or h > 10000:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Image dimensions ({w}x{h}) exceed maximum allowed 10000x10000 pixels."
                    )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Corrupted or unreadable image file: {str(e)}"
            )

    return content, norm_detected
