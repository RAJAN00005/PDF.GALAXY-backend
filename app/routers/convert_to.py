import uuid
import asyncio
import httpx
import ipaddress
import socket
from urllib.parse import urlparse, urljoin
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from ..config import UPLOAD_DIR, PROCESSED_DIR
from ..utils.pdf_utils import images_to_pdf
from ..utils.office_utils import docx_to_pdf, pptx_to_pdf, excel_to_pdf, html_to_pdf
from ..utils.validation import validate_upload

BLOCKED_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
    "169.254.169.254", # AWS/Azure/GCP link-local metadata
    "fd00::",
}

def validate_safe_url_target(url_str: str) -> str:
    parsed = urlparse(url_str.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL scheme. Only public http:// and https:// URLs are permitted."
        )
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid or missing URL hostname.")
    
    clean_host = hostname.lower().strip()
    if (
        clean_host in BLOCKED_HOSTNAMES
        or clean_host.endswith(".local")
        or clean_host.endswith(".internal")
        or clean_host.endswith(".localhost")
    ):
        raise HTTPException(
            status_code=400,
            detail="Access to internal/private network addresses or metadata services is blocked for security."
        )
    
    try:
        addr_infos = socket.getaddrinfo(clean_host, None)
        for _, _, _, _, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Access to private, loopback, or cloud metadata IP addresses is strictly blocked."
                )
    except socket.gaierror:
        raise HTTPException(status_code=400, detail=f"Could not resolve host '{clean_host}' via DNS.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"URL security validation failed: {str(e)}")
        
    return url_str.strip()

async def fetch_webpage_safely(start_url: str, max_redirects: int = 3, max_bytes: int = 5 * 1024 * 1024) -> str:
    """
    Fetches HTML content with strict SSRF defense:
    - Validates scheme and resolved IP before initial connection.
    - Manually handles redirects and re-validates destination IP on each hop.
    - Limits response size to max_bytes (5 MB).
    - Rejects non-HTML content types.
    """
    curr_url = validate_safe_url_target(start_url)
    redirect_count = 0
    
    timeout = httpx.Timeout(10.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        while True:
            headers = {"User-Agent": "PDFGalaxyWebToPDF/1.0 (+https://pdfgalaxy.netlify.app)"}
            try:
                res = await client.get(curr_url, headers=headers)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Unable to connect to web destination: {str(e)}")
                
            if res.is_redirect:
                redirect_count += 1
                if redirect_count > max_redirects:
                    raise HTTPException(status_code=400, detail="Too many redirects encountered while fetching webpage.")
                loc = res.headers.get("location")
                if not loc:
                    raise HTTPException(status_code=400, detail="Redirect response missing Location header.")
                next_url = urljoin(curr_url, loc)
                curr_url = validate_safe_url_target(next_url)
                continue
                
            if res.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Web server returned HTTP {res.status_code}.")
                
            content_type = res.headers.get("content-type", "").lower()
            if content_type and not any(t in content_type for t in ("text/html", "application/xhtml+xml", "text/plain")):
                raise HTTPException(
                    status_code=400,
                    detail=f"Incompatible Content-Type '{content_type}'. Only HTML or plain-text web pages can be converted to PDF."
                )
                
            # Stream body bounded to max_bytes
            body_bytes = bytearray()
            async for chunk in res.aiter_bytes():
                body_bytes.extend(chunk)
                if len(body_bytes) > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="Webpage content exceeds maximum allowed size of 5 MB."
                    )
                    
            encoding = res.encoding or "utf-8"
            try:
                return body_bytes.decode(encoding, errors="replace")
            except Exception:
                return body_bytes.decode("utf-8", errors="replace")

router = APIRouter(prefix="/convert-to", tags=["Convert TO PDF"])

# Secondary router for /convert prefix aliases (e.g. /convert/jpg-to-png)
alias_router = APIRouter(prefix="/convert", tags=["Convert Aliases"])

@router.post("/jpg-to-pdf")
async def handle_jpg_to_pdf(
    files: List[UploadFile] = File(...),
    orientation: str = Form("auto"),
    margin: int = Form(0)
):
    if not files:
        raise HTTPException(status_code=400, detail="No images provided.")
        
    task_id = str(uuid.uuid4())
    image_paths = []
    
    for idx, f in enumerate(files):
        content, ext = await validate_upload(f, allowed_types=["jpg", "png", "webp", "gif"])
        p = UPLOAD_DIR / f"img_{task_id}_{idx}.{ext}"
        p.write_bytes(content)
        image_paths.append(str(p))
        
    out_file = PROCESSED_DIR / f"images_{task_id}.pdf"
    await asyncio.to_thread(images_to_pdf, image_paths, str(out_file), orientation=orientation, margin=margin)
    
    # Clean up uploaded input files
    for p in image_paths:
        try:
            Path(p).unlink(missing_ok=True)
        except Exception:
            pass
            
    return {
        "success": True,
        "download_id": f"images_{task_id}.pdf",
        "file_name": "converted_images.pdf",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/word-to-pdf")
async def handle_word_to_pdf(file: UploadFile = File(...)):
    content, _ = await validate_upload(file, allowed_types=["docx"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"word_{task_id}.docx"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"doc_{task_id}.pdf"
    try:
        await asyncio.to_thread(docx_to_pdf, str(in_path), str(out_file))
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"doc_{task_id}.pdf",
        "file_name": f"{Path(file.filename or 'document').stem}.pdf",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/powerpoint-to-pdf")
async def handle_pptx_to_pdf(file: UploadFile = File(...)):
    content, _ = await validate_upload(file, allowed_types=["pptx"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"ppt_{task_id}.pptx"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"presentation_{task_id}.pdf"
    try:
        await asyncio.to_thread(pptx_to_pdf, str(in_path), str(out_file))
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"presentation_{task_id}.pdf",
        "file_name": f"{Path(file.filename or 'presentation').stem}.pdf",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/excel-to-pdf")
async def handle_excel_to_pdf(file: UploadFile = File(...)):
    content, _ = await validate_upload(file, allowed_types=["xlsx"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"excel_{task_id}.xlsx"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"spreadsheet_{task_id}.pdf"
    try:
        await asyncio.to_thread(excel_to_pdf, str(in_path), str(out_file))
    finally:
        in_path.unlink(missing_ok=True)
        
    return {
        "success": True,
        "download_id": f"spreadsheet_{task_id}.pdf",
        "file_name": f"{Path(file.filename or 'spreadsheet').stem}.pdf",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/html-to-pdf")
async def handle_html_to_pdf(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None)
):
    task_id = str(uuid.uuid4())
    html_content = ""
    
    if url and url.strip():
        html_content = await fetch_webpage_safely(url.strip())
    elif file:
        content, _ = await validate_upload(file, allowed_types=["html", "text"], max_size=5 * 1024 * 1024)
        html_content = content.decode("utf-8", errors="replace")
    else:
        raise HTTPException(status_code=400, detail="Please supply an HTML file or a valid website URL.")
        
    out_file = PROCESSED_DIR / f"web_{task_id}.pdf"
    await asyncio.to_thread(html_to_pdf, html_content, str(out_file))
    
    return {
        "success": True,
        "download_id": f"web_{task_id}.pdf",
        "file_name": "converted_webpage.pdf",
        "size_bytes": out_file.stat().st_size
    }

async def process_jpg_to_png(file: UploadFile) -> dict:
    from PIL import Image
    content, ext = await validate_upload(file, allowed_types=["jpg", "jpeg", "webp", "png", "bmp"])
    task_id = str(uuid.uuid4())
    in_path = UPLOAD_DIR / f"input_{task_id}.{ext}"
    in_path.write_bytes(content)
    
    out_file = PROCESSED_DIR / f"converted_{task_id}.png"
    try:
        def convert_img():
            with Image.open(in_path) as img:
                img.save(out_file, format="PNG")
        await asyncio.to_thread(convert_img)
    finally:
        in_path.unlink(missing_ok=True)
        
    base_name = Path(file.filename or "image").stem
    return {
        "success": True,
        "download_id": f"converted_{task_id}.png",
        "file_name": f"{base_name}.png",
        "size_bytes": out_file.stat().st_size
    }

@router.post("/jpg-to-png")
async def handle_jpg_to_png(file: UploadFile = File(...)):
    return await process_jpg_to_png(file)

@alias_router.post("/jpg-to-png")
async def handle_convert_jpg_to_png_alias(file: UploadFile = File(...)):
    return await process_jpg_to_png(file)
