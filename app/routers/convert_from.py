import uuid
import asyncio
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from ..config import UPLOAD_DIR, PROCESSED_DIR
from ..utils.pdf_utils import pdf_to_images, pdf_to_pdfa, pdf_to_markdown
from ..utils.office_utils import pdf_to_docx, pdf_to_pptx, pdf_to_excel
from ..utils.validation import validate_upload

router = APIRouter(prefix="/convert-from", tags=["Convert FROM PDF"])

@router.post("/pdf-to-jpg")
async def handle_pdf_to_jpg(
    file: UploadFile = File(...),
    dpi: int = Form(150)
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_base = str(PROCESSED_DIR / f"images_{task_id}")
    try:
        final_output = await asyncio.to_thread(pdf_to_images, str(in_path), out_base, dpi=dpi)
    finally:
        in_path.unlink(missing_ok=True)
        
    out_file = Path(final_output)
    return {
        "success": True,
        "download_id": out_file.name,
        "file_name": f"{Path(file.filename or 'document').stem}_images{out_file.suffix}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/pdf-to-word")
async def handle_pdf_to_word(file: UploadFile = File(...)):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"document_{task_id}.docx"
    try:
        await asyncio.to_thread(pdf_to_docx, str(in_path), str(out_file))
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"document_{task_id}.docx",
        "file_name": f"{Path(file.filename or 'document').stem}.docx",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/pdf-to-powerpoint")
async def handle_pdf_to_powerpoint(file: UploadFile = File(...)):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"presentation_{task_id}.pptx"
    try:
        await asyncio.to_thread(pdf_to_pptx, str(in_path), str(out_file))
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"presentation_{task_id}.pptx",
        "file_name": f"{Path(file.filename or 'presentation').stem}.pptx",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/pdf-to-excel")
async def handle_pdf_to_excel(file: UploadFile = File(...)):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"data_{task_id}.xlsx"
    try:
        await asyncio.to_thread(pdf_to_excel, str(in_path), str(out_file))
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"data_{task_id}.xlsx",
        "file_name": f"{Path(file.filename or 'table_data').stem}.xlsx",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/pdf-to-pdfa")
async def handle_pdf_to_pdfa(file: UploadFile = File(...)):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"archival_{task_id}.pdf"
    try:
        await asyncio.to_thread(pdf_to_pdfa, str(in_path), str(out_file))
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"archival_{task_id}.pdf",
        "file_name": f"{Path(file.filename or 'document').stem}_PDF_A.pdf",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/pdf-to-markdown")
async def handle_pdf_to_markdown(file: UploadFile = File(...)):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    try:
        md_content = await asyncio.to_thread(pdf_to_markdown, str(in_path))
    finally:
        in_path.unlink(missing_ok=True)
        
    out_file = PROCESSED_DIR / f"markdown_{task_id}.md"
    out_file.write_text(md_content, encoding="utf-8")
    
    return {
        "success": True,
        "download_id": f"markdown_{task_id}.md",
        "file_name": f"{Path(file.filename or 'document').stem}.md",
        "size_bytes": out_file.stat().st_size,
        "markdown": md_content
    }
