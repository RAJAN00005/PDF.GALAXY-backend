import uuid
import json
import base64
import io
import asyncio
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from ..config import UPLOAD_DIR, PROCESSED_DIR
from ..utils.pdf_utils import rotate_pdf, add_page_numbers, add_watermark, crop_pdf
from ..utils.validation import validate_upload

router = APIRouter(prefix="/edit", tags=["Edit PDF"])

@router.post("/rotate")
async def handle_rotate(
    file: UploadFile = File(...),
    angle: int = Form(90),
    pages: str = Form("all")
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"rotated_{task_id}.pdf"
    try:
        await asyncio.to_thread(rotate_pdf, str(in_path), str(out_file), angle=angle, pages=pages)
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"rotated_{task_id}.pdf",
        "file_name": f"rotated_{file.filename or 'document.pdf'}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/add-page-numbers")
async def handle_page_numbers(
    file: UploadFile = File(...),
    position: str = Form("bottom-center"),
    format_str: str = Form("Page {n} of {total}"),
    start_num: int = Form(1),
    skip_first: bool = Form(False)
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"numbered_{task_id}.pdf"
    try:
        await asyncio.to_thread(
            add_page_numbers,
            str(in_path),
            str(out_file),
            position=position,
            format_str=format_str,
            start_num=start_num,
            skip_first=skip_first
        )
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"numbered_{task_id}.pdf",
        "file_name": f"numbered_{file.filename or 'document.pdf'}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/add-watermark")
async def handle_watermark(
    file: UploadFile = File(...),
    text: str = Form("CONFIDENTIAL"),
    watermark_image: Optional[UploadFile] = File(None),
    font_size: int = Form(48),
    rotation: int = Form(45),
    color: str = Form("#888888")
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    img_path = None
    if watermark_image:
        img_content, img_ext = await validate_upload(watermark_image, allowed_types=["png", "jpg", "jpeg", "webp"])
        img_dest = UPLOAD_DIR / f"wm_img_{task_id}.{img_ext}"
        img_dest.write_bytes(img_content)
        img_path = str(img_dest)
        
    out_file = PROCESSED_DIR / f"watermarked_{task_id}.pdf"
    try:
        await asyncio.to_thread(
            add_watermark,
            str(in_path),
            str(out_file),
            text=text,
            image_path=img_path,
            font_size=font_size,
            rotation=rotation,
            color=color
        )
    finally:
        in_path.unlink(missing_ok=True)
        if img_path:
            Path(img_path).unlink(missing_ok=True)
            
    return {
        "success": True,
        "download_id": f"watermarked_{task_id}.pdf",
        "file_name": f"watermarked_{file.filename or 'document.pdf'}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/crop")
async def handle_crop(
    file: UploadFile = File(...),
    top: float = Form(0),
    right: float = Form(0),
    bottom: float = Form(0),
    left: float = Form(0)
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.pdf"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"cropped_{task_id}.pdf"
    try:
        await asyncio.to_thread(crop_pdf, str(in_path), str(out_file), top=top, right=right, bottom=bottom, left=left)
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"cropped_{task_id}.pdf",
        "file_name": f"cropped_{file.filename or 'document.pdf'}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/edit-canvas")
async def handle_edit_canvas(
    file: UploadFile = File(...),
    annotations: str = Form(...)
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    
    annots_list = []
    if annotations and annotations.strip():
        try:
            parsed = json.loads(annotations)
            if isinstance(parsed, list):
                annots_list = parsed
        except Exception:
            pass
            
    out_file = PROCESSED_DIR / f"edited_{task_id}.pdf"
    
    def process_canvas():
        reader = PdfReader(io.BytesIO(content))
        writer = PdfWriter()
        
        annots_by_page = {}
        for a in annots_list:
            p = int(a.get("page", 1)) - 1
            annots_by_page.setdefault(p, []).append(a)
            
        for i, page_obj in enumerate(reader.pages):
            page = writer.add_page(page_obj)
            if i in annots_by_page:
                w = float(page.mediabox.width)
                h = float(page.mediabox.height)
                packet = io.BytesIO()
                can = canvas.Canvas(packet, pagesize=(w, h))
                
                for item in annots_by_page[i]:
                    kind = item.get("type", "text")
                    if kind == "text":
                        text = item.get("text", "")
                        x = float(item.get("x", 50))
                        y_top = float(item.get("y", 50))
                        size = float(item.get("fontSize", 12))
                        can.setFont("Helvetica", size)
                        can.setFillColorRGB(0.1, 0.1, 0.1)
                        can.drawString(x, h - y_top, text)
                    elif kind == "rectangle":
                        x = float(item.get("x", 50))
                        y_top = float(item.get("y", 50))
                        rw = float(item.get("width", 100))
                        rh = float(item.get("height", 60))
                        can.setStrokeColorRGB(0.3, 0.3, 0.8)
                        can.setLineWidth(1.5)
                        can.rect(x, h - y_top - rh, rw, rh, fill=0, stroke=1)
                        
                can.save()
                packet.seek(0)
                overlay = PdfReader(packet).pages[0]
                page.merge_page(overlay)
            
        with open(str(out_file), "wb") as f:
            writer.write(f)

    await asyncio.to_thread(process_canvas)
        
    return {
        "success": True,
        "download_id": f"edited_{task_id}.pdf",
        "file_name": f"edited_{file.filename or 'document.pdf'}",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/pdf-forms")
async def handle_pdf_forms(
    file: UploadFile = File(...),
    field_data: Optional[str] = Form(None)
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    
    def process_forms():
        reader = PdfReader(io.BytesIO(content))
        fields_found = []
        fields = reader.get_fields()
        if fields:
            for name, obj in fields.items():
                fields_found.append({
                    "name": name,
                    "type": str(obj.get("/FT", "text")),
                    "value": str(obj.get("/V", ""))
                })
                
        if field_data:
            writer = PdfWriter()
            writer.append(reader)
            values = json.loads(field_data)
            for page in writer.pages:
                writer.update_page_form_field_values(page, values)
                
            out_file = PROCESSED_DIR / f"filled_form_{task_id}.pdf"
            with open(str(out_file), "wb") as f:
                writer.write(f)
            return fields_found, out_file
        return fields_found, None

    fields_found, out_file = await asyncio.to_thread(process_forms)
        
    if out_file:
        return {
            "success": True,
            "download_id": out_file.name,
            "file_name": f"filled_{file.filename or 'form.pdf'}",
            "fields": fields_found
        }
        
    return {
        "success": True,
        "fields": fields_found,
        "message": f"Found {len(fields_found)} form fields in document."
    }

@router.post("/editor/apply")
async def handle_editor_apply(
    file: UploadFile = File(...),
    changes: str = Form(...)
):
    content, _ = await validate_upload(file, allowed_types=["pdf"])
    task_id = str(uuid.uuid4())
    
    changes_list = []
    if changes and changes.strip():
        try:
            parsed = json.loads(changes)
            if isinstance(parsed, list):
                changes_list = parsed
        except Exception:
            pass
            
    out_file = PROCESSED_DIR / f"pdf_editor_{task_id}.pdf"
    
    def process_editor():
        reader = PdfReader(io.BytesIO(content))
        writer = PdfWriter()
        
        by_page = {}
        for item in changes_list:
            p = int(item.get("page", 1)) - 1
            by_page.setdefault(p, []).append(item)
            
        for i, page_obj in enumerate(reader.pages):
            page = writer.add_page(page_obj)
            if i in by_page:
                w = float(page.mediabox.width)
                h = float(page.mediabox.height)
                packet = io.BytesIO()
                can = canvas.Canvas(packet, pagesize=(w, h))
                
                for item in by_page[i]:
                    kind = item.get("type", "add_text")
                    x = float(item.get("x", 50))
                    y_top = float(item.get("y", 50))
                    y = h - y_top
                    
                    if kind in ("text_replacement", "whiteout"):
                        rw = float(item.get("width", 80))
                        rh = float(item.get("height", 20))
                        can.setFillColorRGB(1, 1, 1)
                        can.setStrokeColorRGB(1, 1, 1)
                        can.rect(x, y - rh, rw, rh, fill=1, stroke=0)
                        
                        if kind == "text_replacement":
                            txt = item.get("text", "")
                            fsize = float(item.get("fontSize", 12))
                            can.setFont("Helvetica", fsize)
                            can.setFillColorRGB(0.1, 0.1, 0.1)
                            can.drawString(x, y - fsize, txt)
                            
                    elif kind == "add_text":
                        txt = item.get("text", "")
                        fsize = float(item.get("fontSize", 14))
                        font_name = "Helvetica-Bold" if item.get("bold") else "Helvetica"
                        can.setFont(font_name, fsize)
                        can.setFillColorRGB(0.1, 0.1, 0.1)
                        can.drawString(x, y - fsize, txt)
                        
                    elif kind == "highlight":
                        rw = float(item.get("width", 100))
                        rh = float(item.get("height", 20))
                        can.setFillColorRGB(1, 1, 0, alpha=0.35)
                        can.rect(x, y - rh, rw, rh, fill=1, stroke=0)
                        
                    elif kind == "shape":
                        shape = item.get("shape", "rectangle")
                        rw = float(item.get("width", 100))
                        rh = float(item.get("height", 60))
                        can.setStrokeColorRGB(0.2, 0.4, 0.9)
                        can.setLineWidth(float(item.get("strokeWidth", 2)))
                        if shape == "circle":
                            can.ellipse(x, y - rh, x + rw, y, fill=0, stroke=1)
                        elif shape == "line":
                            can.line(x, y, x + rw, y - rh)
                        else:
                            can.rect(x, y - rh, rw, rh, fill=0, stroke=1)
                            
                    elif kind == "image" and item.get("imageData"):
                        img_data = item["imageData"]
                        if "," in img_data:
                            img_data = img_data.split(",", 1)[1]
                        img_bytes = io.BytesIO(base64.b64decode(img_data))
                        from reportlab.lib.utils import ImageReader
                        img_reader = ImageReader(img_bytes)
                        rw = float(item.get("width", 150))
                        rh = float(item.get("height", 100))
                        can.drawImage(img_reader, x, y - rh, width=rw, height=rh)
                        
                can.save()
                packet.seek(0)
                overlay = PdfReader(packet).pages[0]
                page.merge_page(overlay)
            
        with open(str(out_file), "wb") as f:
            writer.write(f)

    await asyncio.to_thread(process_editor)
        
    return {
        "success": True,
        "download_id": f"pdf_editor_{task_id}.pdf",
        "file_name": f"edited_{file.filename or 'document.pdf'}",
        "size_bytes": out_file.stat().st_size
    }
