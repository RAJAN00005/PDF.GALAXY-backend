import uuid
import json
import asyncio
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from ..config import UPLOAD_DIR, PROCESSED_DIR
from ..utils.pdf_utils import merge_pdfs, split_pdf, remove_pages, extract_pages, organize_pdf
from ..utils.validation import validate_upload

router = APIRouter(prefix="/organize", tags=["Organize"])

@router.post("/merge")
async def handle_merge(files: List[UploadFile] = File(...)):
    if not files or len(files) < 2:
        raise HTTPException(status_code=400, detail="At least 2 files are required to merge.")
    
    saved_paths = []
    task_id = str(uuid.uuid4())
    
    try:
        for idx, f in enumerate(files):
            content, ext = await validate_upload(f, allowed_types=["pdf", "jpg", "png", "webp", "jpeg", "bmp"])
            dest = UPLOAD_DIR / f"{task_id}_{idx}.{ext}"
            dest.write_bytes(content)
            saved_paths.append(str(dest))
            
        out_file = PROCESSED_DIR / f"merged_{task_id}.pdf"
        await asyncio.to_thread(merge_pdfs, saved_paths, str(out_file))
    finally:
        for p in saved_paths:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
                
    return {
        "success": True,
        "download_id": f"merged_{task_id}.pdf",
        "file_name": "merged_document.pdf",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/split")
async def handle_split(
    file: UploadFile = File(...),
    ranges: str = Form("all")
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    is_all = ranges.strip().lower() == "all"
    out_ext = ".zip" if is_all else ".pdf"
    out_file = PROCESSED_DIR / f"split_{task_id}{out_ext}"
    
    try:
        await asyncio.to_thread(split_pdf, str(in_path), ranges, str(out_file))
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"split_{task_id}{out_ext}",
        "file_name": f"split_result{out_ext}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/remove-pages")
async def handle_remove_pages(
    file: UploadFile = File(...),
    pages: str = Form(...)
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    pages_list = [int(p.strip()) for p in pages.split(",") if p.strip().isdigit()]
    if not pages_list:
        in_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Please specify valid page numbers to remove.")
        
    out_file = PROCESSED_DIR / f"removed_{task_id}.pdf"
    try:
        await asyncio.to_thread(remove_pages, str(in_path), pages_list, str(out_file))
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"removed_{task_id}.pdf",
        "file_name": "cleaned_document.pdf",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/extract-pages")
async def handle_extract_pages(
    file: UploadFile = File(...),
    pages: str = Form(...)
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    pages_list = [int(p.strip()) for p in pages.split(",") if p.strip().isdigit()]
    if not pages_list:
        in_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Please specify valid page numbers to extract.")
        
    out_file = PROCESSED_DIR / f"extracted_{task_id}.pdf"
    try:
        await asyncio.to_thread(extract_pages, str(in_path), pages_list, str(out_file))
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"extracted_{task_id}.pdf",
        "file_name": "extracted_pages.pdf",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/organize")
async def handle_organize(
    file: UploadFile = File(...),
    actions: str = Form("[]")
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    actions_list = []
    if actions and actions.strip():
        try:
            parsed = json.loads(actions)
            if isinstance(parsed, list):
                actions_list = parsed
        except Exception:
            pass
            
    out_file = PROCESSED_DIR / f"organized_{task_id}.pdf"
    try:
        await asyncio.to_thread(organize_pdf, str(in_path), actions_list, str(out_file))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"organized_{task_id}.pdf",
        "file_name": "organized_document.pdf",
        "size_bytes": out_file.stat().st_size
    }
