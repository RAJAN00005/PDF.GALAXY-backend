import os
import io
from pathlib import Path
from docx import Document
from pptx import Presentation
from pptx.util import Inches as PptxInches, Pt as PptxPt
import openpyxl
from openpyxl.styles import Font, PatternFill
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import pymupdf
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

def docx_to_pdf(docx_path: str, pdf_output_path: str) -> str:
    doc = Document(docx_path)
    pdf_doc = SimpleDocTemplate(
        pdf_output_path,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54
    )
    styles = getSampleStyleSheet()
    story = []
    
    title_style = styles["Title"]
    h1_style = styles["Heading1"]
    h2_style = styles["Heading2"]
    normal_style = styles["Normal"]
    normal_style.fontSize = 10
    normal_style.leading = 14
    
    for element in doc.element.body:
        tag = element.tag.split("}")[-1]
        if tag == "p":
            p = next((p for p in doc.paragraphs if p._p == element), None)
            if not p or not p.text.strip():
                story.append(Spacer(1, 6))
                continue
                
            style_name = p.style.name.lower()
            if "title" in style_name:
                curr_style = title_style
            elif "heading 1" in style_name:
                curr_style = h1_style
            elif "heading 2" in style_name:
                curr_style = h2_style
            else:
                curr_style = normal_style
                
            formatted_text = ""
            for run in p.runs:
                text = run.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                if run.bold and run.italic:
                    text = f"<b><i>{text}</i></b>"
                elif run.bold:
                    text = f"<b>{text}</b>"
                elif run.italic:
                    text = f"<i>{text}</i>"
                formatted_text += text
                
            if formatted_text:
                story.append(Paragraph(formatted_text, curr_style))
                story.append(Spacer(1, 4))
                
        elif tag == "tbl":
            table_obj = next((t for t in doc.tables if t._tbl == element), None)
            if table_obj:
                table_data = []
                for row in table_obj.rows:
                    row_data = [Paragraph(cell.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), normal_style) for cell in row.cells]
                    table_data.append(row_data)
                    
                if table_data:
                    t = Table(table_data)
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                    ]))
                    story.append(t)
                    story.append(Spacer(1, 10))
                    
    pdf_doc.build(story)
    return pdf_output_path

def pdf_to_docx(pdf_path: str, docx_output_path: str) -> str:
    doc = Document()
    pdf_doc = pymupdf.open(pdf_path)
    for page_idx in range(len(pdf_doc)):
        page = pdf_doc[page_idx]
        if page_idx > 0:
            doc.add_page_break()
            
        tabs = page.find_tables()
        text = page.get_text()
        
        if tabs and len(tabs.tables) > 0:
            for tab in tabs:
                table_data = tab.extract()
                if not table_data or not table_data[0]:
                    continue
                rows_count = len(table_data)
                cols_count = len(table_data[0])
                docx_table = doc.add_table(rows=rows_count, cols=cols_count)
                docx_table.style = 'Table Grid'
                for r_i, row in enumerate(table_data):
                    for c_i, cell_val in enumerate(row):
                        docx_table.cell(r_i, c_i).text = str(cell_val or "").strip()
                doc.add_paragraph()
        
        if text:
            for line in text.splitlines():
                line_str = line.strip()
                if not line_str:
                    continue
                if len(line_str) < 50 and not line_str.endswith("."):
                    doc.add_heading(line_str, level=2)
                else:
                    doc.add_paragraph(line_str)
                    
    pdf_doc.close()
    doc.save(docx_output_path)
    return docx_output_path

def pptx_to_pdf(pptx_path: str, pdf_output_path: str) -> str:
    prs = Presentation(pptx_path)
    pdf = SimpleDocTemplate(
        pdf_output_path,
        pagesize=landscape(letter),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    title_style.textColor = colors.HexColor("#4F46E5")
    body_style = styles["Normal"]
    body_style.fontSize = 12
    body_style.leading = 16
    
    story = []
    for slide_idx, slide in enumerate(prs.slides):
        if slide_idx > 0:
            story.append(PageBreak())
            
        slide_title = ""
        slide_contents = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text.strip()
                if not text:
                    continue
                if not slide_title and shape == slide.shapes[0]:
                    slide_title = text
                else:
                    for p in shape.text_frame.paragraphs:
                        if p.text.strip():
                            slide_contents.append(p.text.strip())
                            
        story.append(Paragraph(slide_title or f"Slide {slide_idx + 1}", title_style))
        story.append(Spacer(1, 14))
        
        for content in slide_contents:
            story.append(Paragraph(f"&bull; {content}", body_style))
            story.append(Spacer(1, 6))
            
    pdf.build(story)
    return pdf_output_path

def pdf_to_pptx(pdf_path: str, pptx_output_path: str) -> str:
    prs = Presentation()
    prs.slide_width = PptxInches(13.33)
    prs.slide_height = PptxInches(7.5)
    blank_layout = prs.slide_layouts[6]
    
    pdf = pdfium.PdfDocument(pdf_path)
    reader = PdfReader(pdf_path)
    
    for i, page in enumerate(pdf):
        slide = prs.slides.add_slide(blank_layout)
        pil_img = page.render(scale=2.0).to_pil()
        img_bytes = io.BytesIO()
        pil_img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        slide.shapes.add_picture(
            img_bytes,
            PptxInches(0.5),
            PptxInches(0.5),
            width=PptxInches(7.5)
        )
        
        text = reader.pages[i].extract_text() or ""
        if text.strip():
            tx_box = slide.shapes.add_textbox(PptxInches(8.3), PptxInches(0.8), PptxInches(4.5), PptxInches(6.0))
            tf = tx_box.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = f"Page {i + 1} Content"
            p.font.size = PptxPt(16)
            p.font.bold = True
            
            for line in text.splitlines()[:15]:
                if line.strip():
                    p2 = tf.add_paragraph()
                    p2.text = line.strip()
                    p2.font.size = PptxPt(11)
                    
    prs.save(pptx_output_path)
    return pptx_output_path

def excel_to_pdf(xlsx_path: str, pdf_output_path: str) -> str:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    pdf = SimpleDocTemplate(
        pdf_output_path,
        pagesize=landscape(letter),
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30
    )
    styles = getSampleStyleSheet()
    h1_style = styles["Heading1"]
    h1_style.textColor = colors.HexColor("#10B981")
    normal = styles["Normal"]
    normal.fontSize = 8
    normal.leading = 10
    
    story = []
    for sheet_idx, sheet_name in enumerate(wb.sheetnames):
        ws = wb[sheet_name]
        if sheet_idx > 0:
            story.append(PageBreak())
            
        story.append(Paragraph(f"Sheet: {sheet_name}", h1_style))
        story.append(Spacer(1, 10))
        
        table_data = []
        for row in ws.iter_rows(values_only=True):
            if any(cell is not None for cell in row):
                row_cells = [Paragraph(str(c) if c is not None else "", normal) for c in row]
                table_data.append(row_cells)
                
        if table_data:
            t = Table(table_data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
            ]))
            story.append(t)
            
    pdf.build(story)
    return pdf_output_path

def pdf_to_excel(pdf_path: str, xlsx_output_path: str) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Extracted Tables"
    row_cursor = 1
    
    pdf_doc = pymupdf.open(pdf_path)
    for page_idx in range(len(pdf_doc)):
        page = pdf_doc[page_idx]
        tabs = page.find_tables()
        if tabs and len(tabs.tables) > 0:
            for tab in tabs:
                table_data = tab.extract()
                if table_data:
                    ws.cell(row=row_cursor, column=1, value=f"Page {page_idx + 1} - Table").font = Font(bold=True, color="4F46E5")
                    row_cursor += 1
                    for r_idx, row in enumerate(table_data):
                        for c_idx, val in enumerate(row):
                            cell = ws.cell(row=row_cursor, column=c_idx + 1, value=str(val or ""))
                            if r_idx == 0:
                                cell.font = Font(bold=True)
                                cell.fill = PatternFill(start_color="E0E7FF", end_color="E0E7FF", fill_type="solid")
                        row_cursor += 1
                    row_cursor += 1
        else:
            text = page.get_text()
            if text:
                ws.cell(row=row_cursor, column=1, value=f"Page {page_idx + 1} Content").font = Font(bold=True)
                row_cursor += 1
                for line in text.splitlines():
                    ws.cell(row=row_cursor, column=1, value=line)
                    row_cursor += 1
                row_cursor += 1
                
    pdf_doc.close()
    wb.save(xlsx_output_path)
    return xlsx_output_path

def html_to_pdf(html_text: str, pdf_output_path: str) -> str:
    import re
    pdf = SimpleDocTemplate(
        pdf_output_path,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40
    )
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    h1 = styles["Heading1"]
    story = []
    
    cleaned_html = re.sub(r'<script.*?</script>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    cleaned_html = re.sub(r'<style.*?</style>', '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
    
    title_match = re.search(r'<title>(.*?)</title>', cleaned_html, re.IGNORECASE)
    if title_match:
        story.append(Paragraph(title_match.group(1), h1))
        story.append(Spacer(1, 12))
        
    paragraphs = re.findall(r'<(?:p|h[1-6]|li|div)[^>]*>(.*?)</(?:p|h[1-6]|li|div)>', cleaned_html, re.DOTALL | re.IGNORECASE)
    if paragraphs:
        for p_text in paragraphs:
            plain_p = re.sub(r'<[^>]+>', '', p_text).strip()
            if plain_p:
                story.append(Paragraph(plain_p.replace("&", "&amp;"), normal))
                story.append(Spacer(1, 6))
    else:
        plain_text = re.sub(r'<[^>]+>', ' ', cleaned_html)
        for line in plain_text.splitlines():
            if line.strip():
                story.append(Paragraph(line.strip().replace("&", "&amp;"), normal))
                story.append(Spacer(1, 4))
                
    pdf.build(story)
    return pdf_output_path

def is_tesseract_available() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False

def ocr_pdf(pdf_path: str, pdf_output_path: str, language: str = "eng") -> str:
    """
    Performs real OCR to produce a searchable PDF document with selectable text.
    If Tesseract is installed, renders pages to images and generates real OCR text layer.
    If Tesseract is not installed:
      - If PDF already has selectable digital text, preserves and cleans the document.
      - If PDF is purely scanned with no text, raises RuntimeError explaining dependency requirements.
    """
    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    
    # Check if document already has digital text
    has_digital_text = any(len(page.get_text().strip()) > 0 for page in doc)
    tess_available = is_tesseract_available()
    
    if tess_available:
        import pytesseract
        from PIL import Image
        writer = PdfWriter()
        for i in range(total_pages):
            page = doc[i]
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            try:
                pdf_bytes = pytesseract.image_to_pdf_or_hocr(img, extension='pdf', lang=language)
                ocr_reader = PdfReader(io.BytesIO(pdf_bytes))
                for ocr_p in ocr_reader.pages:
                    writer.add_page(ocr_p)
            except Exception:
                pdf_bytes = pytesseract.image_to_pdf_or_hocr(img, extension='pdf')
                ocr_reader = PdfReader(io.BytesIO(pdf_bytes))
                for ocr_p in ocr_reader.pages:
                    writer.add_page(ocr_p)
        doc.close()
        with open(pdf_output_path, "wb") as f:
            writer.write(f)
        return pdf_output_path
    else:
        doc.close()
        if has_digital_text:
            doc2 = pymupdf.open(pdf_path)
            doc2.save(pdf_output_path, garbage=4, deflate=True, clean=True)
            doc2.close()
            return pdf_output_path
        else:
            raise RuntimeError(
                "Tesseract OCR engine is not installed on this server. "
                "To generate searchable text from scanned non-text documents, Tesseract OCR must be installed on the system PATH."
            )