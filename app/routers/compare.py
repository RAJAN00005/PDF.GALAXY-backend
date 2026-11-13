import uuid
import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException
from ..config import UPLOAD_DIR
from ..utils.pdf_utils import compare_pdfs
from ..utils.validation import validate_upload

router = APIRouter(prefix="/compare", tags=["Compare"])

@router.post("/compare")
async def handle_compare(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...)
):
    content1, _ = await validate_upload(file1, allowed_types=["pdf"])
    content2, _ = await validate_upload(file2, allowed_types=["pdf"])
    
    task_id = str(uuid.uuid4())
    path1 = UPLOAD_DIR / f"compare_1_{task_id}.pdf"
    path2 = UPLOAD_DIR / f"compare_2_{task_id}.pdf"
    
    path1.write_bytes(content1)
    path2.write_bytes(content2)
    
    try:
        comparison = await asyncio.to_thread(compare_pdfs, str(path1), str(path2))
    finally:
        path1.unlink(missing_ok=True)
        path2.unlink(missing_ok=True)
        
    return {
        "success": True,
        "doc1_name": file1.filename,
        "doc2_name": file2.filename,
        "comparison": comparison
    }
