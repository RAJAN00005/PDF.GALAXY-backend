import asyncio
import time
import secrets
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from .config import PROCESSED_DIR, RETENTION_SECONDS
from .cleaner import start_cleanup_loop
from .routers import organize, optimize, convert_to, convert_from, edit, security, compare, ai
from .utils.validation import validate_upload

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start auto-deletion cleanup background task
    cleanup_task = asyncio.create_task(start_cleanup_loop(interval_seconds=600))
    yield
    cleanup_task.cancel()

app = FastAPI(
    title="PDF Galaxy Processing Engine",
    description="High-performance, secure PDF & document processing microservice powering PDF Galaxy",
    version="2.0.0",
    lifespan=lifespan
)

# Production CORS policy with localhost and Netlify deployment origins
ALLOWED_ORIGINS = [
    "https://pdfgalaxy.netlify.app",
    "http://localhost:3000",
    "http://localhost:3005",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3005",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^https:\/\/[a-zA-Z0-9_-]+\.netlify\.app$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "HEAD", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length", "X-Request-ID"]
)

# Mount all routers under /api
app.include_router(organize.router, prefix="/api")
app.include_router(optimize.router, prefix="/api")
app.include_router(convert_to.router, prefix="/api")
app.include_router(convert_to.alias_router, prefix="/api") # /api/convert/jpg-to-png alias
app.include_router(convert_from.router, prefix="/api")
app.include_router(edit.router, prefix="/api")
app.include_router(security.router, prefix="/api")
app.include_router(compare.router, prefix="/api")
app.include_router(ai.router, prefix="/api")

@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health_check():
    return {
        "status": "online",
        "service": "PDF Galaxy Backend",
        "developer": "Developed by Rajan",
        "version": "2.0.0",
        "tools_supported": 38
    }

@app.api_route("/api/warmup", methods=["GET", "POST", "HEAD"])
async def warmup_engine():
    """
    Pre-warms in-memory libraries (PyMuPDF, ReportLab, PIL, pypdf)
    so cold starts have zero initialization latency.
    """
    try:
        import pymupdf
        import pypdf
        from PIL import Image
        from reportlab.pdfgen import canvas
        import io
        
        # Fast memory touch
        doc = pymupdf.open()
        p = doc.new_page(width=100, height=100)
        p.insert_text((10, 10), "warm")
        doc.close()
        
        return {
            "status": "warm",
            "ready": True,
            "engine": "PDF Galaxy Microservice Engine"
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e)}

@app.api_route("/", methods=["GET", "HEAD"])
async def root_health():
    return {
        "status": "ok",
        "service": "PDF Galaxy Backend API",
        "developer": "Developed by Rajan"
    }

@app.post("/api/qr/upload-media")
async def upload_qr_media(file: UploadFile = File(...)):
    """
    Secure QR Media asset upload:
    - Enforces 10 MB maximum upload size.
    - Validates image magic bytes (PNG, JPG, WebP, GIF, SVG).
    - Uses cryptographically secure random token (secrets.token_hex).
    - Prevents file collisions and path traversal.
    """
    content, ext = await validate_upload(
        file,
        allowed_types=["png", "jpg", "jpeg", "webp", "gif", "svg", "text"],
        max_size=10 * 1024 * 1024
    )
    
    token = secrets.token_hex(16)
    out_ext = ext if ext.startswith(".") else f".{ext}"
    if out_ext == ".text":
        out_ext = ".svg"
    unique_id = f"media_{token}{out_ext}"
    dest_path = PROCESSED_DIR / unique_id
    
    dest_path.write_bytes(content)
    
    return {
        "success": True,
        "file_id": unique_id,
        "file_name": file.filename,
        "size_bytes": len(content),
        "media_type": file.content_type or f"image/{ext}"
    }

@app.get("/api/download/{file_id}")
async def download_file(file_id: str):
    # Prevent path traversal and sanitize filename
    safe_name = Path(file_id).name
    file_path = (PROCESSED_DIR / safe_name).resolve()
    
    # Verify the resolved path is inside PROCESSED_DIR
    try:
        file_path.relative_to(PROCESSED_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid file access attempt.")
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Requested file has expired or does not exist.")
        
    # Enforce access-time TTL: if file age exceeds RETENTION_SECONDS, return 410 Gone immediately
    try:
        age_seconds = time.time() - file_path.stat().st_mtime
        if age_seconds > RETENTION_SECONDS:
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=410, detail="Requested file has expired and was automatically deleted.")
    except HTTPException:
        raise
    except Exception:
        pass
        
    media_type = "application/octet-stream"
    if safe_name.endswith(".pdf"):
        media_type = "application/pdf"
    elif safe_name.endswith(".zip"):
        media_type = "application/zip"
    elif safe_name.endswith(".docx"):
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif safe_name.endswith(".xlsx"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif safe_name.endswith(".pptx"):
        media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    elif safe_name.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif safe_name.endswith(".png"):
        media_type = "image/png"
    elif safe_name.endswith(".gif"):
        media_type = "image/gif"
    elif safe_name.endswith(".webp"):
        media_type = "image/webp"
    elif safe_name.endswith(".svg"):
        media_type = "image/svg+xml"
    elif safe_name.endswith(".md"):
        media_type = "text/markdown; charset=utf-8"
    elif safe_name.endswith(".txt"):
        media_type = "text/plain; charset=utf-8"
        
    headers = {
        "Cache-Control": "private, no-store, max-age=0, must-revalidate",
        "X-Content-Type-Options": "nosniff"
    }
    
    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type=media_type,
        headers=headers
    )

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
