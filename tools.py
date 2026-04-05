from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import fitz
import io
import zipfile
import traceback
import re
from typing import List, Optional

router = APIRouter(prefix="/tools", tags=["tools"])


# ─── Utility: Get page count ───────────────────────────────────────────────
@router.post("/page-count")
async def get_page_count(file: UploadFile = File(...)):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        count = len(doc)
        doc.close()
        return {"pages": count}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


# ─── 1. Merge PDF ──────────────────────────────────────────────────────────
@router.post("/merge")
async def merge_pdfs(files: List[UploadFile] = File(...)):
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="At least 2 files required to merge.")
    try:
        merged_doc = fitz.open()
        for file in files:
            content = await file.read()
            doc = fitz.open(stream=content, filetype="pdf")
            merged_doc.insert_pdf(doc)
            doc.close()
        out_bytes = merged_doc.tobytes()
        merged_doc.close()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="merged.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 2. Split PDF ──────────────────────────────────────────────────────────
@router.post("/split")
async def split_pdf(file: UploadFile = File(...), ranges: str = Form(...)):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        pages_to_keep = _parse_page_ranges(ranges, len(doc))
        doc.select(pages_to_keep)
        out_bytes = doc.tobytes()
        doc.close()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="split.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 3. Compress PDF ───────────────────────────────────────────────────────
@router.post("/compress")
async def compress_pdf(
    file: UploadFile = File(...),
    level: str = Form("medium"),  # low, medium, high, extreme
):
    try:
        content = await file.read()
        original_size = len(content)
        doc = fitz.open(stream=content, filetype="pdf")

        if level == "extreme":
            # Downsample all images to very low quality
            for page in doc:
                il = page.get_images(full=True)
                for img in il:
                    xref = img[0]
                    try:
                        base = doc.extract_image(xref)
                        if base and base["width"] > 150:
                            img_data = base["image"]
                            pix = fitz.Pixmap(img_data)
                            # Shrink to 25%
                            factor = 0.25
                            new_pix = fitz.Pixmap(pix, int(pix.width * factor), int(pix.height * factor))
                            page.replace_image(xref, pixmap=new_pix)
                    except Exception:
                        continue

            out_bytes = doc.tobytes(garbage=4, deflate=True, clean=True)

        elif level == "high":
            for page in doc:
                il = page.get_images(full=True)
                for img in il:
                    xref = img[0]
                    try:
                        base = doc.extract_image(xref)
                        if base and base["width"] > 300:
                            img_data = base["image"]
                            pix = fitz.Pixmap(img_data)
                            factor = 0.5
                            new_pix = fitz.Pixmap(pix, int(pix.width * factor), int(pix.height * factor))
                            page.replace_image(xref, pixmap=new_pix)
                    except Exception:
                        continue
            out_bytes = doc.tobytes(garbage=4, deflate=True, clean=True)

        elif level == "medium":
            out_bytes = doc.tobytes(garbage=4, deflate=True, clean=True)

        else:  # low
            out_bytes = doc.tobytes(garbage=3, deflate=True)

        doc.close()
        compressed_size = len(out_bytes)
        reduction = round((1 - compressed_size / original_size) * 100, 1) if original_size > 0 else 0

        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="compressed.pdf"',
                "X-Original-Size": str(original_size),
                "X-Compressed-Size": str(compressed_size),
                "X-Reduction": str(reduction),
                "Access-Control-Expose-Headers": "X-Original-Size, X-Compressed-Size, X-Reduction",
            }
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 4. PDF to Image ───────────────────────────────────────────────────────
@router.post("/to-image")
async def pdf_to_image(
    file: UploadFile = File(...),
    pages: str = Form("1"),
    quality: int = Form(200),
):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        page_list = _parse_page_ranges(pages, len(doc))

        if len(page_list) == 1:
            pix = doc.load_page(page_list[0]).get_pixmap(dpi=quality)
            img_bytes = pix.tobytes(output="png")
            doc.close()
            return StreamingResponse(
                io.BytesIO(img_bytes),
                media_type="image/png",
                headers={"Content-Disposition": f'attachment; filename="page_{page_list[0]+1}.png"'}
            )
        else:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in page_list:
                    pix = doc.load_page(p).get_pixmap(dpi=quality)
                    zf.writestr(f"page_{p+1}.png", pix.tobytes(output="png"))
            doc.close()
            zip_buffer.seek(0)
            return StreamingResponse(
                zip_buffer,
                media_type="application/zip",
                headers={"Content-Disposition": 'attachment; filename="pdf_images.zip"'}
            )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 5. Protect PDF ────────────────────────────────────────────────────────
@router.post("/protect")
async def protect_pdf(file: UploadFile = File(...), password: str = Form(...)):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        out_bytes = doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw=password,
            user_pw=password
        )
        doc.close()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="protected.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 6. Unlock PDF ─────────────────────────────────────────────────────────
@router.post("/unlock")
async def unlock_pdf(file: UploadFile = File(...), password: str = Form(...)):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        if not doc.is_encrypted:
            raise ValueError("This PDF is not encrypted.")
        if not doc.authenticate(password):
            raise ValueError("Incorrect password.")
        out_bytes = doc.tobytes()
        doc.close()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="unlocked.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


# ─── 7. Rotate PDF ─────────────────────────────────────────────────────────
@router.post("/rotate")
async def rotate_pdf(file: UploadFile = File(...), degrees: int = Form(90)):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        for page in doc:
            page.set_rotation(degrees)
        out_bytes = doc.tobytes()
        doc.close()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="rotated.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 8. Watermark ──────────────────────────────────────────────────────────
@router.post("/watermark")
async def watermark_pdf(
    file: UploadFile = File(...),
    text: str = Form("CONFIDENTIAL"),
    position: str = Form("center"),
    fontsize: int = Form(40),
    opacity: float = Form(0.3),
    color: str = Form("gray"),
):
    COLOR_MAP = {
        "gray": (0.5, 0.5, 0.5),
        "red": (0.8, 0.1, 0.1),
        "blue": (0.1, 0.1, 0.8),
        "black": (0.15, 0.15, 0.15),
    }
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        rgb = COLOR_MAP.get(color, (0.5, 0.5, 0.5))

        for page in doc:
            rect = page.rect
            w, h = rect.width, rect.height

            if position == "diagonal":
                import math
                shape = page.new_shape()
                angle = -45 * math.pi / 180
                morph = (fitz.Point(w / 2, h / 2), fitz.Matrix(math.cos(angle), math.sin(angle), -math.sin(angle), math.cos(angle), 0, 0))
                shape.insert_text(fitz.Point(w / 4, h / 2), text, fontsize=fontsize, color=rgb, morph=morph)
                shape.commit(overlay=True)
            else:
                pos_map = {
                    "center": (w / 2 - len(text) * fontsize * 0.25, h / 2),
                    "top-left": (40, 60),
                    "top-right": (w - len(text) * fontsize * 0.5 - 20, 60),
                    "bottom-left": (40, h - 40),
                    "bottom-right": (w - len(text) * fontsize * 0.5 - 20, h - 40),
                }
                pt = pos_map.get(position, pos_map["center"])
                page.insert_text(pt, text, fontsize=fontsize, color=rgb, overlay=True)

        out_bytes = doc.tobytes()
        doc.close()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="watermarked.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 9. Add Page Numbers ───────────────────────────────────────────────────
@router.post("/page-numbers")
async def add_page_numbers(
    file: UploadFile = File(...),
    position: str = Form("bottom-center"),
    start_number: int = Form(1),
):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        for i, page in enumerate(doc):
            rect = page.rect
            num = str(start_number + i)
            w, h = rect.width, rect.height
            pos_map = {
                "bottom-center": (w / 2 - 10, h - 30),
                "bottom-right": (w - 50, h - 30),
                "bottom-left": (30, h - 30),
                "top-center": (w / 2 - 10, 30),
            }
            pt = pos_map.get(position, pos_map["bottom-center"])
            page.insert_text(pt, num, fontsize=11, color=(0.3, 0.3, 0.3))
        out_bytes = doc.tobytes()
        doc.close()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="numbered.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 10. Extract Images ────────────────────────────────────────────────────
@router.post("/extract-images")
async def extract_images(file: UploadFile = File(...)):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        zip_buffer = io.BytesIO()
        img_count = 0
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                images = page.get_images(full=True)
                for img_idx, img_info in enumerate(images):
                    xref = img_info[0]
                    try:
                        base_image = doc.extract_image(xref)
                        img_bytes = base_image["image"]
                        ext = base_image.get("ext", "png")
                        zf.writestr(f"page{page_num+1}_img{img_idx+1}.{ext}", img_bytes)
                        img_count += 1
                    except Exception:
                        continue
        doc.close()
        if img_count == 0:
            raise ValueError("No images found in this PDF.")
        zip_buffer.seek(0)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="extracted_images.zip"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 11. Organize PDF ──────────────────────────────────────────────────────
@router.post("/organize")
async def organize_pdf(file: UploadFile = File(...), page_order: str = Form(...)):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        order = [int(p.strip()) - 1 for p in page_order.split(",")]
        for p in order:
            if p < 0 or p >= len(doc):
                raise ValueError(f"Page {p+1} out of range (document has {len(doc)} pages)")
        doc.select(order)
        out_bytes = doc.tobytes()
        doc.close()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="organized.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 12. JPG to PDF ────────────────────────────────────────────────────────
@router.post("/jpg-to-pdf")
async def jpg_to_pdf(files: List[UploadFile] = File(...)):
    try:
        doc = fitz.open()
        for file in files:
            img_bytes = await file.read()
            img_doc = fitz.open(stream=img_bytes, filetype=file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png")
            # Convert to single-page PDF
            pdf_bytes = img_doc.convert_to_pdf()
            img_doc.close()
            img_pdf = fitz.open("pdf", pdf_bytes)
            doc.insert_pdf(img_pdf)
            img_pdf.close()
        out_bytes = doc.tobytes()
        doc.close()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="images_to_pdf.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 13. Repair PDF ────────────────────────────────────────────────────────
@router.post("/repair")
async def repair_pdf(file: UploadFile = File(...)):
    try:
        content = await file.read()
        # PyMuPDF auto-repairs on open + re-save
        doc = fitz.open(stream=content, filetype="pdf")
        out_bytes = doc.tobytes(garbage=4, deflate=True, clean=True)
        doc.close()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="repaired.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 14. Crop PDF ──────────────────────────────────────────────────────────
@router.post("/crop")
async def crop_pdf(
    file: UploadFile = File(...),
    margin_top: float = Form(0),
    margin_bottom: float = Form(0),
    margin_left: float = Form(0),
    margin_right: float = Form(0),
):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        for page in doc:
            rect = page.rect
            new_rect = fitz.Rect(
                rect.x0 + margin_left,
                rect.y0 + margin_top,
                rect.x1 - margin_right,
                rect.y1 - margin_bottom
            )
            page.set_cropbox(new_rect)
        out_bytes = doc.tobytes()
        doc.close()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="cropped.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 15. Redact PDF ────────────────────────────────────────────────────────
@router.post("/redact")
async def redact_pdf(
    file: UploadFile = File(...),
    search_text: str = Form(...),
):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        redacted_count = 0
        for page in doc:
            areas = page.search_for(search_text)
            for area in areas:
                page.add_redact_annot(area, fill=(0, 0, 0))
                redacted_count += 1
            page.apply_redactions()
        if redacted_count == 0:
            raise ValueError(f'Text "{search_text}" not found in document.')
        out_bytes = doc.tobytes()
        doc.close()
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="redacted.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 16. PDF to Word ───────────────────────────────────────────────────────
@router.post("/to-word")
async def pdf_to_word(file: UploadFile = File(...)):
    try:
        from docx import Document as DocxDocument
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        word_doc = DocxDocument()

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            blocks = page.get_text("dict")["blocks"]

            if page_num > 0:
                word_doc.add_page_break()

            for block in blocks:
                if block["type"] == 0:  # text block
                    for line in block["lines"]:
                        text = ""
                        for span in line["spans"]:
                            text += span["text"]
                        if text.strip():
                            p = word_doc.add_paragraph()
                            run = p.add_run(text)
                            # Try to match font size
                            if line["spans"]:
                                size = line["spans"][0].get("size", 11)
                                run.font.size = Pt(min(max(size, 8), 36))

        doc.close()
        docx_buffer = io.BytesIO()
        word_doc.save(docx_buffer)
        docx_buffer.seek(0)

        return StreamingResponse(
            docx_buffer,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": 'attachment; filename="converted.docx"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── 17. PDF to Excel ──────────────────────────────────────────────────────
@router.post("/to-excel")
async def pdf_to_excel(file: UploadFile = File(...)):
    try:
        from openpyxl import Workbook

        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        wb = Workbook()

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            # Try to extract tables first
            tables = page.find_tables()

            if page_num == 0:
                ws = wb.active
                ws.title = f"Page {page_num + 1}"
            else:
                ws = wb.create_sheet(title=f"Page {page_num + 1}")

            if tables and len(tables.tables) > 0:
                row_offset = 1
                for table in tables:
                    data = table.extract()
                    for r_idx, row in enumerate(data):
                        for c_idx, cell in enumerate(row):
                            ws.cell(row=row_offset + r_idx, column=c_idx + 1, value=cell if cell else "")
                    row_offset += len(data) + 2  # gap between tables
            else:
                # Fallback: dump text line by line
                text = page.get_text("text")
                for r_idx, line in enumerate(text.split("\n")):
                    if line.strip():
                        ws.cell(row=r_idx + 1, column=1, value=line.strip())

        doc.close()
        xlsx_buffer = io.BytesIO()
        wb.save(xlsx_buffer)
        xlsx_buffer.seek(0)

        return StreamingResponse(
            xlsx_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="converted.xlsx"'}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── Helper: Parse page ranges ─────────────────────────────────────────────
def _parse_page_ranges(ranges_str: str, total_pages: int) -> list:
    """Parse '1,3,5-8,all' into 0-indexed page list."""
    pages = []
    if ranges_str.strip().lower() == "all":
        return list(range(total_pages))
    for part in ranges_str.split(","):
        part = part.strip()
        if "-" in part:
            s, e = part.split("-")
            for p in range(int(s) - 1, int(e)):
                pages.append(p)
        else:
            pages.append(int(part) - 1)
    # Validate
    for p in pages:
        if p < 0 or p >= total_pages:
            raise ValueError(f"Page {p+1} out of range (document has {total_pages} pages)")
    return pages
