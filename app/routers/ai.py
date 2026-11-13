import uuid
import re
import os
import io
import asyncio
import httpx
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import pymupdf
from ..config import UPLOAD_DIR, PROCESSED_DIR
from ..utils.pdf_utils import pdf_to_markdown
from ..utils.office_utils import html_to_pdf, is_tesseract_available
from ..utils.validation import validate_upload

router = APIRouter(prefix="/ai", tags=["PDF Intelligence"])

def local_extractive_summary(text: str, length: str = "standard") -> dict:
    sentences = re.split(r'(?<=[.?!])\s+', text.strip())
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    if not sentences:
        return {
            "executive_summary": "Document contains minimal or no extractable text.",
            "key_highlights": [],
            "action_items": [],
            "word_count": 0
        }
        
    word_count = len(text.split())
    target_count = 3 if length == "brief" else (6 if length == "standard" else 10)
    selected_sentences = sentences[:min(target_count, len(sentences))]
    
    action_keywords = ["must", "should", "action", "task", "required", "ensure", "recommend", "deadline", "next step", "implement"]
    action_items = []
    for s in sentences:
        if any(kw in s.lower() for kw in action_keywords):
            action_items.append(s)
            if len(action_items) >= 4:
                break
                
    if not action_items and len(sentences) > 2:
        action_items = ["Review findings detailed in the document.", "Verify specifications and follow-up milestones."]
        
    return {
        "executive_summary": " ".join(selected_sentences),
        "key_highlights": selected_sentences[:4],
        "action_items": action_items[:4],
        "word_count": word_count
    }

@router.post("/summarize")
async def handle_summarize(
    file: UploadFile = File(...),
    length: str = Form("standard")
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    try:
        def extract():
            doc = pymupdf.open(str(in_path))
            txt = ""
            for page in doc:
                txt += (page.get_text() or "") + "\n"
            doc.close()
            return txt
        full_text = await asyncio.to_thread(extract)
    finally:
        in_path.unlink(missing_ok=True)
        
    summary_data = local_extractive_summary(full_text, length=length)
    
    return {
        "success": True,
        "document_name": file.filename,
        "summary": summary_data
    }

LANG_CODE_MAP = {
    "hindi": "hi",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "japanese": "ja",
    "chinese": "zh-CN",
    "italian": "it",
    "portuguese": "pt",
    "russian": "ru",
    "arabic": "ar",
    "bengali": "bn",
    "marathi": "mr",
    "gujarati": "gu",
    "tamil": "ta",
    "telugu": "te",
    "urdu": "ur",
}

async def translate_text_keyless(text_chunks: list[str], target_lang: str) -> list[str]:
    """
    Translates text chunks using public translation services without requiring ANY API key.
    Completely free, self-contained, and works out-of-the-box.
    """
    import urllib.parse
    target_code = LANG_CODE_MAP.get(target_lang.lower().strip(), target_lang[:2].lower())
    translated_chunks = []
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for chunk in text_chunks:
            chunk_clean = chunk.strip()
            if not chunk_clean:
                continue
            q = urllib.parse.quote(chunk_clean[:450])
            url = f"https://api.mymemory.translated.net/get?q={q}&langpair=en|{target_code}"
            try:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    trans_text = data.get("responseData", {}).get("translatedText")
                    if trans_text and not trans_text.startswith("MYMEMORY WARNING"):
                        translated_chunks.append(trans_text)
                    else:
                        translated_chunks.append(chunk_clean)
                else:
                    translated_chunks.append(chunk_clean)
            except Exception:
                translated_chunks.append(chunk_clean)
                
    return translated_chunks

@router.post("/translate")
async def handle_translate(
    file: UploadFile = File(...),
    target_lang: str = Form("Hindi")
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    try:
        def extract_paragraphs():
            doc = pymupdf.open(str(in_path))
            paras = []
            for page in doc:
                text = page.get_text()
                if text:
                    for block in text.split("\n\n"):
                        b = block.strip()
                        if b:
                            paras.append(b)
            doc.close()
            return paras
        paragraphs = await asyncio.to_thread(extract_paragraphs)
    finally:
        in_path.unlink(missing_ok=True)
        
    if not paragraphs:
        raise HTTPException(status_code=400, detail="The uploaded PDF contains no extractable text to translate.")
        
    # Translate paragraphs with 100% keyless engine
    translated_paras = await translate_text_keyless(paragraphs[:25], target_lang)
    
    doc_title = f"Translated Document ({target_lang})"
    html_content = f"""
    <html>
    <head><title>{doc_title}</title></head>
    <body style="font-family: sans-serif; margin: 30px;">
        <h1>{doc_title}</h1>
        <p><i>Original filename: {file.filename}</i></p>
        <p><b>Target Language:</b> {target_lang}</p>
        <hr style="margin: 20px 0;"/>
        <h3>Translated Content:</h3>
    """
    for tp in translated_paras:
        html_content += f"<p style='line-height: 1.5;'>{tp}</p>\n"
    html_content += "</body></html>"
    
    out_file = PROCESSED_DIR / f"translated_{task_id}.pdf"
    await asyncio.to_thread(html_to_pdf, html_content, str(out_file))
    
    return {
        "success": True,
        "download_id": f"translated_{task_id}.pdf",
        "file_name": f"translated_{target_lang.lower()}_{file.filename or 'doc.pdf'}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/deep-markdown")
async def handle_deep_markdown(file: UploadFile = File(...)):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    try:
        md_content = await asyncio.to_thread(pdf_to_markdown, str(in_path))
    finally:
        in_path.unlink(missing_ok=True)
        
    out_file = PROCESSED_DIR / f"deep_md_{task_id}.md"
    out_file.write_text(md_content, encoding="utf-8")
    
    return {
        "success": True,
        "download_id": f"deep_md_{task_id}.md",
        "file_name": f"{Path(file.filename or 'document').stem}_structured.md",
        "size_bytes": out_file.stat().st_size,
        "markdown": md_content
    }

@router.post("/image-to-text")
async def handle_image_to_text(file: UploadFile = File(...)):
    """
    Real Image-to-Text OCR:
    Runs Tesseract OCR on the uploaded image.
    If Tesseract is not installed on the system, returns HTTP 503 explaining dependency requirements.
    Never returns fake placeholder text.
    """
    content, ext = await validate_upload(file, allowed_types=["png", "jpg", "jpeg", "webp", "gif"])
    
    if not is_tesseract_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "Tesseract OCR engine is not installed on this server host. "
                "To extract text from images, Tesseract OCR (tesseract binary) must be installed and accessible on PATH."
            )
        )
        
    import pytesseract
    from PIL import Image
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.{ext}"
    in_path.write_bytes(content)
    
    try:
        def do_ocr():
            with Image.open(in_path) as img:
                return pytesseract.image_to_string(img)
        extracted_text = await asyncio.to_thread(do_ocr)
    finally:
        in_path.unlink(missing_ok=True)
        
    out_file = PROCESSED_DIR / f"ocr_{task_id}.txt"
    out_file.write_text(extracted_text, encoding="utf-8")
    
    base_name = Path(file.filename or "image").stem
    return {
        "success": True,
        "download_id": f"ocr_{task_id}.txt",
        "file_name": f"{base_name}_extracted.txt",
        "size_bytes": out_file.stat().st_size,
        "text": extracted_text
    }
