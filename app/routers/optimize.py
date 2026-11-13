import uuid
import io
import asyncio
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from PIL import Image
from ..config import UPLOAD_DIR, PROCESSED_DIR
from ..utils.pdf_utils import compress_pdf, repair_pdf
from ..utils.office_utils import ocr_pdf
from ..utils.validation import validate_upload

router = APIRouter(prefix="/optimize", tags=["Optimize"])

@router.post("/compress")
async def handle_compress(
    file: UploadFile = File(...),
    level: str = Form("recommended")
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"compressed_{task_id}.pdf"
    try:
        stats = await asyncio.to_thread(compress_pdf, str(in_path), str(out_file), level=level)
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"compressed_{task_id}.pdf",
        "file_name": f"compressed_{file.filename or 'document.pdf'}",
        "stats": stats
    }

@router.post("/repair")
async def handle_repair(file: UploadFile = File(...)):
    # Do not enforce strict PDF structure integrity during repair upload since the file may be broken
    content, _ = await validate_upload(file, allowed_types=["pdf"], check_pdf_integrity=False)
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"repaired_{task_id}.pdf"
    try:
        success = await asyncio.to_thread(repair_pdf, str(in_path), str(out_file))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF could not be repaired: {str(e)}")
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": success,
        "download_id": f"repaired_{task_id}.pdf",
        "file_name": f"repaired_{file.filename or 'document.pdf'}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/ocr")
async def handle_ocr(
    file: UploadFile = File(...),
    language: str = Form("eng")
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"ocr_{task_id}.pdf"
    try:
        await asyncio.to_thread(ocr_pdf, str(in_path), str(out_file), language=language)
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR processing error: {str(e)}")
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"ocr_{task_id}.pdf",
        "file_name": f"searchable_{file.filename or 'document.pdf'}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/compress-image")
async def handle_compress_image(
    file: UploadFile = File(...),
    target_size: float = Form(200),
    unit: str = Form("KB"),
    quality: int = Form(80)
):
    content, ext = await validate_upload(file, allowed_types=["jpg", "jpeg", "png", "webp", "bmp"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.{ext}"
    in_path.write_bytes(content)
    
    target_bytes = int(target_size * (1024 * 1024 if unit.upper() == "MB" else 1024))
    out_file = PROCESSED_DIR / f"compressed_{task_id}.{ext}"
    
    def process_compression():
        with Image.open(in_path) as img:
            curr_mode = img.mode
            curr_format = "JPEG" if ext in ("jpg", "jpeg") else (img.format or "PNG")
            
            if curr_mode in ("RGBA", "P") and ext in ("jpg", "jpeg"):
                img = img.convert("RGB")
                
            curr_quality = max(5, min(95, quality))
            orig_size = in_path.stat().st_size
            best_buf = io.BytesIO()
            img.save(best_buf, format=curr_format, quality=curr_quality, optimize=True)
            
            while best_buf.tell() > target_bytes and curr_quality > 15:
                curr_quality -= 10
                best_buf = io.BytesIO()
                img.save(best_buf, format=curr_format, quality=curr_quality, optimize=True)
                
            if best_buf.tell() > target_bytes:
                w, h = img.size
                while best_buf.tell() > target_bytes and w > 150 and h > 150:
                    w = int(w * 0.85)
                    h = int(h * 0.85)
                    resized = img.resize((w, h), Image.Resampling.LANCZOS)
                    best_buf = io.BytesIO()
                    resized.save(best_buf, format=curr_format, quality=curr_quality, optimize=True)
                    
            out_file.write_bytes(best_buf.getvalue())
            comp_size = out_file.stat().st_size
            percent_saved = max(0, round(((orig_size - comp_size) / orig_size) * 100)) if orig_size > 0 else 0
            return orig_size, comp_size, percent_saved

    try:
        orig_size, comp_size, percent_saved = await asyncio.to_thread(process_compression)
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"compressed_{task_id}.{ext}",
        "file_name": f"compressed_{file.filename or 'image.jpg'}",
        "stats": {
            "original_size": orig_size,
            "compressed_size": comp_size,
            "saved_bytes": max(0, orig_size - comp_size),
            "percent_saved": percent_saved
        }
    }
