import os
import io
import json
import zipfile
import difflib
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image
import pymupdf

def get_page_count(pdf_path: str) -> int:
    doc = pymupdf.open(pdf_path)
    count = len(doc)
    doc.close()
    return count

def merge_pdfs(input_paths: List[str], output_path: str) -> str:
    out_doc = pymupdf.open()
    for path in input_paths:
        ext = Path(path).suffix.lower()
        if ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif']:
            with Image.open(path) as img:
                img_rgb = img.convert('RGB')
                buf = io.BytesIO()
                img_rgb.save(buf, format='PDF')
                buf.seek(0)
                img_pdf = pymupdf.open(stream=buf.getvalue(), filetype='pdf')
                out_doc.insert_pdf(img_pdf)
                img_pdf.close()
        else:
            in_doc = pymupdf.open(path)
            out_doc.insert_pdf(in_doc)
            in_doc.close()
    out_doc.save(output_path, garbage=4, deflate=True, clean=True)
    out_doc.close()
    return output_path

def split_pdf(input_path: str, ranges: str, output_path: str) -> str:
    doc = pymupdf.open(input_path)
    total_pages = len(doc)
    
    if not ranges or ranges.strip().lower() == 'all':
        zip_path = output_path if output_path.endswith('.zip') else output_path + '.zip'
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i in range(total_pages):
                single_doc = pymupdf.open()
                single_doc.insert_pdf(doc, from_page=i, to_page=i)
                pdf_bytes = single_doc.tobytes(garbage=4, deflate=True)
                single_doc.close()
                zf.writestr(f'page_{i + 1}.pdf', pdf_bytes)
        doc.close()
        return zip_path
        
    selected_pages = []
    for part in ranges.split(','):
        part = part.strip()
        if '-' in part:
            s, e = part.split('-', 1)
            start = max(1, int(s.strip()))
            end = min(total_pages, int(e.strip()))
            selected_pages.extend(range(start - 1, end))
        elif part.isdigit():
            p = int(part)
            if 1 <= p <= total_pages:
                selected_pages.append(p - 1)
                
    out_doc = pymupdf.open()
    seen = set()
    for p in selected_pages:
        if p not in seen:
            seen.add(p)
            out_doc.insert_pdf(doc, from_page=p, to_page=p)
            
    out_doc.save(output_path, garbage=4, deflate=True, clean=True)
    out_doc.close()
    doc.close()
    return output_path

def remove_pages(input_path: str, pages_to_remove: List[int], output_path: str) -> str:
    doc = pymupdf.open(input_path)
    total = len(doc)
    remove_set = set(p - 1 for p in pages_to_remove)
    out_doc = pymupdf.open()
    for i in range(total):
        if i not in remove_set:
            out_doc.insert_pdf(doc, from_page=i, to_page=i)
    if len(out_doc) == 0:
        out_doc.close()
        doc.close()
        raise ValueError("Cannot remove all pages from PDF. At least one page must remain.")
    out_doc.save(output_path, garbage=4, deflate=True, clean=True)
    out_doc.close()
    doc.close()
    return output_path

def extract_pages(input_path: str, pages_to_extract: List[int], output_path: str) -> str:
    doc = pymupdf.open(input_path)
    total = len(doc)
    out_doc = pymupdf.open()
    for p in pages_to_extract:
        if 1 <= p <= total:
            out_doc.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
    if len(out_doc) == 0:
        out_doc.close()
        doc.close()
        raise ValueError("No valid pages selected for extraction.")
    out_doc.save(output_path, garbage=4, deflate=True, clean=True)
    out_doc.close()
    doc.close()
    return output_path

def organize_pdf(input_path: str, page_actions: List[Dict[str, Any]], output_path: str) -> str:
    """
    Organizes PDF pages using a complete page manifest.
    - Explicitly deleted pages are removed.
    - Reordered pages follow the exact order in page_actions.
    - Any existing pages NOT mentioned in page_actions are preserved at the end.
    - Rotations (90, 180, 270) are applied accurately.
    - If page_actions is empty, all pages are preserved in original order.
    - Prevents empty output files if all pages were deleted.
    """
    doc = pymupdf.open(input_path)
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("Input PDF contains 0 pages.")
        
    new_order = []
    has_explicit_pages = False
    
    if page_actions and isinstance(page_actions, list):
        specified_pages = set()
        for a in page_actions:
            if not isinstance(a, dict):
                continue
            try:
                p_num = int(a.get("page", 0))
            except (ValueError, TypeError):
                continue
            if 1 <= p_num <= total_pages:
                specified_pages.add(p_num)
                has_explicit_pages = True
                if a.get("delete") is True:
                    continue
                rot = int(a.get("rotation", 0)) % 360
                new_order.append((p_num, rot))
                
        # Preserve unspecified pages at the end
        if has_explicit_pages:
            for p in range(1, total_pages + 1):
                if p not in specified_pages:
                    new_order.append((p, 0))
                    
    if not has_explicit_pages:
        for p in range(1, total_pages + 1):
            new_order.append((p, 0))
            
    if not new_order:
        doc.close()
        raise ValueError("Organize action would result in an empty document (all pages deleted). At least one page must remain.")
        
    out_doc = pymupdf.open()
    for p_num, rot in new_order:
        out_doc.insert_pdf(doc, from_page=p_num - 1, to_page=p_num - 1)
        if rot != 0:
            last_page = out_doc[-1]
            last_page.set_rotation((last_page.rotation + rot) % 360)
            
    out_doc.save(output_path, garbage=4, deflate=True, clean=True)
    out_doc.close()
    doc.close()
    return output_path

def compress_pdf(input_path: str, output_path: str, level: str = 'recommended') -> Dict[str, Any]:
    original_size = os.path.getsize(input_path)
    doc = pymupdf.open(input_path)
    
    if level in ("recommended", "extreme"):
        max_dim = 1000 if level == "extreme" else 1600
        img_quality = 50 if level == "extreme" else 75
        
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            img_list = page.get_images(full=True)
            for img_info in img_list:
                xref = img_info[0]
                try:
                    base_img = doc.extract_image(xref)
                    if not base_img:
                        continue
                    image_bytes = base_img["image"]
                    with Image.open(io.BytesIO(image_bytes)) as pil_img:
                        w, h = pil_img.size
                        if w > max_dim or h > max_dim or pil_img.format != "JPEG":
                            scale = min(max_dim / max(w, 1), max_dim / max(h, 1), 1.0)
                            new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
                            resized = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                            if resized.mode in ("RGBA", "P"):
                                resized = resized.convert("RGB")
                            buf = io.BytesIO()
                            resized.save(buf, format="JPEG", quality=img_quality, optimize=True)
                            new_bytes = buf.getvalue()
                            if len(new_bytes) < len(image_bytes):
                                doc.update_stream(xref, new_bytes)
                except Exception:
                    continue
                    
    doc.save(
        output_path,
        garbage=4,
        deflate=True,
        clean=True
    )
    doc.close()
    
    compressed_size = os.path.getsize(output_path)
    if compressed_size >= original_size:
        shutil.copyfile(input_path, output_path)
        compressed_size = original_size
        
    saved_bytes = max(0, original_size - compressed_size)
    percent_saved = round((saved_bytes / original_size) * 100, 1) if original_size > 0 else 0
    return {
        'original_size': original_size,
        'compressed_size': compressed_size,
        'saved_bytes': saved_bytes,
        'percent_saved': percent_saved,
        'level': level
    }

def repair_pdf(input_path: str, output_path: str) -> bool:
    try:
        doc = pymupdf.open(input_path)
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
        return True
    except Exception as e:
        raise RuntimeError(f"Unable to repair corrupted PDF structure: {e}")

def rotate_pdf(input_path: str, output_path: str, angle: int = 90, pages: str = 'all') -> str:
    doc = pymupdf.open(input_path)
    total = len(doc)
    target_pages = set(range(total))
    if pages and pages.strip().lower() != 'all':
        target_pages = set(int(p) - 1 for p in pages.split(',') if p.strip().isdigit() and 1 <= int(p) <= total)
    for i in range(total):
        if i in target_pages:
            page = doc[i]
            page.set_rotation((page.rotation + angle) % 360)
    doc.save(output_path, garbage=4, deflate=True, clean=True)
    doc.close()
    return output_path

def add_page_numbers(
    input_path: str,
    output_path: str,
    position: str = 'bottom-center',
    format_str: str = 'Page {n} of {total}',
    start_num: int = 1,
    skip_first: bool = False
) -> str:
    doc = pymupdf.open(input_path)
    total = len(doc)
    
    for i in range(total):
        if i == 0 and skip_first:
            continue
            
        page = doc[i]
        curr_num = (i - (1 if skip_first else 0)) + start_num
        effective_total = total - 1 if skip_first else total
        label = format_str.replace('{n}', str(curr_num)).replace('{total}', str(effective_total))
        
        w = page.rect.width
        h = page.rect.height
        
        y = h - 25 if 'bottom' in position else 25
        if 'left' in position:
            x = 36
            align = pymupdf.TEXT_ALIGN_LEFT
        elif 'right' in position:
            x = w - 160
            align = pymupdf.TEXT_ALIGN_RIGHT
        else:
            x = (w - 160) / 2
            align = pymupdf.TEXT_ALIGN_CENTER
            
        rect = pymupdf.Rect(x, y - 10, x + 160, y + 10)
        page.insert_textbox(rect, label, fontsize=9, color=(0.3, 0.3, 0.3), align=align)
        
    doc.save(output_path, garbage=4, deflate=True, clean=True)
    doc.close()
    return output_path

def add_watermark(
    input_path: str,
    output_path: str,
    text: str = '',
    image_path: Optional[str] = None,
    opacity: float = 0.3,
    rotation: int = 45,
    font_size: int = 48,
    color: str = '#888888'
) -> str:
    doc = pymupdf.open(input_path)
    try:
        color_hex = color.lstrip('#')
        r, g, b = (0.5, 0.5, 0.5)
        if len(color_hex) == 6:
            r = int(color_hex[0:2], 16) / 255.0
            g = int(color_hex[2:4], 16) / 255.0
            b = int(color_hex[4:6], 16) / 255.0

        for page in doc:
            w = page.rect.width
            h = page.rect.height
            
            if image_path and os.path.exists(image_path):
                img_w = min(w * 0.6, 300)
                img_h = img_w * 0.5
                rect = pymupdf.Rect((w - img_w) / 2, (h - img_h) / 2, (w + img_w) / 2, (h + img_h) / 2)
                page.insert_image(rect, filename=image_path, overlay=True)
            elif text:
                approx_half_width = len(text) * font_size * 0.25
                origin = pymupdf.Point(max(20, (w / 2) - approx_half_width), h / 2)
                page.insert_text(
                    origin,
                    text,
                    fontsize=font_size,
                    color=(r, g, b),
                    morph=(origin, pymupdf.Matrix(rotation))
                )
                
        doc.save(output_path, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()
    return output_path

def crop_pdf(
    input_path: str,
    output_path: str,
    top: float = 0,
    right: float = 0,
    bottom: float = 0,
    left: float = 0
) -> str:
    doc = pymupdf.open(input_path)
    for page in doc:
        r = page.rect
        new_r = pymupdf.Rect(
            r.x0 + left,
            r.y0 + top,
            r.x1 - right,
            r.y1 - bottom
        )
        page.set_cropbox(new_r)
    doc.save(output_path, garbage=4, deflate=True, clean=True)
    doc.close()
    return output_path

def unlock_pdf(input_path: str, output_path: str, password: str = '') -> bool:
    doc = pymupdf.open(input_path)
    if not doc.is_encrypted:
        doc.save(output_path, encryption=pymupdf.PDF_ENCRYPT_NONE)
        doc.close()
        return True
    auth_res = doc.authenticate(password)
    if auth_res <= 0:
        doc.close()
        raise ValueError("Incorrect password. Could not decrypt PDF document.")
    doc.save(output_path, encryption=pymupdf.PDF_ENCRYPT_NONE)
    doc.close()
    return True

def protect_pdf(input_path: str, output_path: str, password: str, owner_password: Optional[str] = None) -> str:
    if not password:
        raise ValueError("User password is required to protect PDF.")
    doc = pymupdf.open(input_path)
    owner_pw = owner_password if owner_password else f"{password}_admin_{os.urandom(4).hex()}"
    doc.save(
        output_path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw=password,
        owner_pw=owner_pw,
        permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_ACCESSIBILITY
    )
    doc.close()
    return output_path

def sign_pdf(
    input_path: str,
    output_path: str,
    signatures: List[Dict[str, Any]]
) -> str:
    """
    Applies visual electronic signatures, endorsement text, and date stamps at specified coordinates.
    Note: Distinguishes visual electronic stamps from cryptographic PKI digital certificate signatures.
    """
    doc = pymupdf.open(input_path)
    total_pages = len(doc)
    
    sigs_by_page = {}
    for sig in signatures:
        if isinstance(sig, dict):
            p = int(sig.get('page', 1)) - 1
            sigs_by_page.setdefault(p, []).append(sig)
            
    for p_idx in range(total_pages):
        if p_idx in sigs_by_page:
            page = doc[p_idx]
            for sig in sigs_by_page[p_idx]:
                x = float(sig.get('x', 100))
                y_top = float(sig.get('y', 100))
                sig_w = float(sig.get('width', 150))
                sig_h = float(sig.get('height', 60))
                
                img_data = sig.get('image_data', '')
                if img_data:
                    if ',' in img_data:
                        img_data = img_data.split(',', 1)[1]
                    import base64
                    try:
                        raw_bytes = base64.b64decode(img_data)
                        rect = pymupdf.Rect(x, y_top, x + sig_w, y_top + sig_h)
                        page.insert_image(rect, stream=raw_bytes)
                    except Exception:
                        pass
                        
                label = f"{sig.get('name', '')} {sig.get('date', '')}".strip()
                if label:
                    page.insert_text((x, y_top + sig_h + 12), label, fontsize=9, color=(0.2, 0.2, 0.2))
                    
    doc.save(output_path, garbage=4, deflate=True, clean=True)
    doc.close()
    return output_path

def redact_pdf(input_path: str, output_path: str, redactions: List[Dict[str, Any]], search_terms: Optional[List[str]] = None) -> str:
    doc = pymupdf.open(input_path)
    total_pages = len(doc)
    
    if search_terms:
        for term in search_terms:
            t = str(term).strip()
            if not t:
                continue
            for page in doc:
                found_rects = page.search_for(t)
                for rect in found_rects:
                    page.add_redact_annot(rect, fill=(0, 0, 0))
    
    redacts_by_page = {}
    for r in redactions:
        p = int(r.get('page', 1)) - 1
        if 0 <= p < total_pages:
            redacts_by_page.setdefault(p, []).append(r)
            
    for page_idx, page in enumerate(doc):
        if page_idx in redacts_by_page:
            for r in redacts_by_page[page_idx]:
                rx = float(r.get('x', 0))
                ry = float(r.get('y', 0))
                rw = float(r.get('width', 100))
                rh = float(r.get('height', 20))
                rect = pymupdf.Rect(rx, ry, rx + rw, ry + rh)
                page.add_redact_annot(rect, fill=(0, 0, 0))
                
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)
        
    doc.save(
        output_path,
        garbage=4,
        deflate=True,
        clean=True
    )
    doc.close()
    return output_path

def compare_pdfs(file1_path: str, file2_path: str) -> Dict[str, Any]:
    doc1 = pymupdf.open(file1_path)
    doc2 = pymupdf.open(file2_path)
    
    total_pages = max(len(doc1), len(doc2))
    diff_results = []
    total_additions = 0
    total_deletions = 0
    
    for i in range(total_pages):
        text1 = doc1[i].get_text() if i < len(doc1) else ''
        text2 = doc2[i].get_text() if i < len(doc2) else ''
        
        lines1 = text1.splitlines()
        lines2 = text2.splitlines()
        
        diff = list(difflib.ndiff(lines1, lines2))
        additions = [line[2:] for line in diff if line.startswith('+ ')]
        deletions = [line[2:] for line in diff if line.startswith('- ')]
        
        total_additions += len(additions)
        total_deletions += len(deletions)
        
        diff_results.append({
            'page': i + 1,
            'has_changes': len(additions) > 0 or len(deletions) > 0,
            'additions_count': len(additions),
            'deletions_count': len(deletions),
            'additions_sample': additions[:5],
            'deletions_sample': deletions[:5],
            'text1_excerpt': text1[:300],
            'text2_excerpt': text2[:300]
        })
        
    res = {
        'total_pages_doc1': len(doc1),
        'total_pages_doc2': len(doc2),
        'total_additions': total_additions,
        'total_deletions': total_deletions,
        'pages_with_differences': sum(1 for p in diff_results if p['has_changes']),
        'page_details': diff_results
    }
    doc1.close()
    doc2.close()
    return res

def pdf_to_images(file_path: str, output_path: str, dpi: int = 150) -> str:
    doc = pymupdf.open(file_path)
    total = len(doc)
    
    if total == 1:
        page = doc[0]
        pix = page.get_pixmap(dpi=dpi)
        out_file = output_path if output_path.endswith('.jpg') else output_path + '.jpg'
        pix.save(out_file)
        doc.close()
        return out_file
    else:
        zip_file_path = output_path if output_path.endswith('.zip') else output_path + '.zip'
        with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i in range(total):
                page = doc[i]
                pix = page.get_pixmap(dpi=dpi)
                img_data = pix.tobytes("jpeg")
                zf.writestr(f'page_{i + 1}.jpg', img_data)
        doc.close()
        return zip_file_path

def images_to_pdf(image_paths: List[str], output_path: str, orientation: str = 'auto', margin: int = 0) -> str:
    images = []
    for p in image_paths:
        img = Image.open(p).convert('RGB')
        w, h = img.width, img.height
        if orientation == 'portrait' and w > h:
            img = img.rotate(90, expand=True)
        elif orientation == 'landscape' and h > w:
            img = img.rotate(90, expand=True)
        images.append(img)
        
    if images:
        images[0].save(
            output_path,
            'PDF',
            resolution=100.0,
            save_all=True,
            append_images=images[1:]
        )
    return output_path

def pdf_to_pdfa(input_path: str, output_path: str) -> str:
    doc = pymupdf.open(input_path)
    
    xmp_metadata = (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '  <rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">\n'
        '   <pdfaid:part>1</pdfaid:part>\n'
        '   <pdfaid:conformance>B</pdfaid:conformance>\n'
        '  </rdf:Description>\n'
        '  <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '   <dc:format>application/pdf</dc:format>\n'
        '   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">PDF/A-1b Archival Document</rdf:li></rdf:Alt></dc:title>\n'
        '  </rdf:Description>\n'
        ' </rdf:RDF>\n'
        '</x:xmpmeta>\n'
        '<?xpacket end="w"?>'
    )
    
    doc.set_xml_metadata(xmp_metadata)
    doc.save(
        output_path,
        garbage=4,
        deflate=True,
        clean=True
    )
    doc.close()
    return output_path

def pdf_to_markdown(input_path: str) -> str:
    doc = pymupdf.open(input_path)
    md_lines = []
    for i in range(len(doc)):
        md_lines.append(f"\n## Page {i + 1}\n")
        text = doc[i].get_text() or ''
        for line in text.splitlines():
            line_str = line.strip()
            if line_str:
                if len(line_str) < 60 and not line_str.endswith('.'):
                    md_lines.append(f"\n### {line_str}\n")
                else:
                    md_lines.append(line_str + "\n")
    doc.close()
    return "\n".join(md_lines)
