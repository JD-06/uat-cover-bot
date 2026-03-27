"""
cover_generator.py
Genera una hoja de presentación en PDF con logos e información del alumno.
"""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from PyPDF2 import PdfReader, PdfWriter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOGO_UAT       = os.path.join(BASE_DIR, "logoUat.jpg")
LOGO_FI        = os.path.join(BASE_DIR, "logoFi.jpg")
LOGO_WATERMARK = os.path.join(BASE_DIR, "logoUatMarcaDeAgua.jpg")

_UAT_RATIO = 246 / 53    # ancho/alto real de logoUat.jpg
_FI_RATIO  = 224 / 82    # ancho/alto real de logoFi.jpg


def generate_cover(
    alumno: str,
    maestro: str,
    materia: str,
    tema: str,
    grado_grupo: str,
    fecha: str,
    output_path: str,
) -> str:
    """Genera una hoja de presentación como PDF y devuelve output_path."""

    PAGE_W, PAGE_H = letter
    MARGIN = 1.8 * cm
    AZUL   = colors.HexColor("#003366")
    ROJO   = colors.HexColor("#CC0000")
    CENTER_X = PAGE_W / 2

    c = canvas.Canvas(output_path, pagesize=letter)

    # ── 1. MARCA DE AGUA ──────────────────────────────────────────────────
    wm = 11 * cm
    c.saveState()
    c.setFillAlpha(0.07)
    c.drawImage(LOGO_WATERMARK, (PAGE_W - wm) / 2, (PAGE_H - wm) / 2,
                width=wm, height=wm, preserveAspectRatio=True, mask="auto")
    c.restoreState()

    # ── 2. LOGOS (mismo alto) ─────────────────────────────────────────────
    LOGO_H = 1.4 * cm               # misma altura para los dos logos
    LOGO_TOP = PAGE_H - MARGIN      # borde superior

    # UAT — izquierda
    UAT_W = LOGO_H * _UAT_RATIO
    c.drawImage(LOGO_UAT, MARGIN, LOGO_TOP - LOGO_H,
                width=UAT_W, height=LOGO_H, mask="auto")

    # FI — derecha
    FI_W = LOGO_H * _FI_RATIO
    c.drawImage(LOGO_FI, PAGE_W - MARGIN - FI_W, LOGO_TOP - LOGO_H,
                width=FI_W, height=LOGO_H, mask="auto")

    # ── 3. LÍNEAS SEPARADORAS (debajo de los logos) ───────────────────────
    SEP1_Y = LOGO_TOP - LOGO_H - 6

    c.setStrokeColor(AZUL)
    c.setLineWidth(2.5)
    c.line(MARGIN, SEP1_Y, PAGE_W - MARGIN, SEP1_Y)

    c.setStrokeColor(ROJO)
    c.setLineWidth(1)
    c.line(MARGIN, SEP1_Y - 5, PAGE_W - MARGIN, SEP1_Y - 5)

    # ── 4. TEXTO UNIVERSIDAD (debajo de las líneas) ───────────────────────
    UAT_TEXT_Y = SEP1_Y - 5 - 32   # gap de ~1cm bajo la línea roja

    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(AZUL)
    c.drawCentredString(CENTER_X, UAT_TEXT_Y, "Universidad Autónoma de Tamaulipas")

    c.setFont("Helvetica", 10)
    c.setFillColor(colors.black)
    c.drawCentredString(CENTER_X, UAT_TEXT_Y - 15, "Facultad de Ingeniería")

    # ── 5. TÍTULO / TEMA ──────────────────────────────────────────────────
    TITLE_Y = PAGE_H * 0.54

    _draw_centered_block(c, f"\u201c{tema}\u201d", CENTER_X, TITLE_Y,
                         PAGE_W - 4 * cm, "Helvetica-Bold", 20, AZUL)

    # ── 6. TABLA DE DATOS ─────────────────────────────────────────────────
    fields = [
        ("Alumno",        alumno),
        ("Maestro",       maestro),
        ("Materia",       materia),
        ("Grado y grupo", grado_grupo),
        ("Fecha",         fecha),
    ]

    ROW_H   = 0.82 * cm
    LABEL_W = 4.0 * cm
    BOX_W   = 13.0 * cm
    BOX_H   = len(fields) * ROW_H
    BOX_X   = (PAGE_W - BOX_W) / 2
    BOX_Y   = PAGE_H * 0.27

    # Fondo de celdas de etiqueta (columna izquierda)
    c.setFillColor(colors.HexColor("#E8EEF4"))
    c.rect(BOX_X, BOX_Y, LABEL_W, BOX_H, fill=1, stroke=0)

    # Fondo de celdas de valor (columna derecha)
    c.setFillColor(colors.white)
    c.rect(BOX_X + LABEL_W, BOX_Y, BOX_W - LABEL_W, BOX_H, fill=1, stroke=0)

    # Líneas horizontales entre filas
    c.setStrokeColor(colors.HexColor("#A0B4C8"))
    c.setLineWidth(0.5)
    for i in range(1, len(fields)):
        row_line_y = BOX_Y + BOX_H - i * ROW_H
        c.line(BOX_X, row_line_y, BOX_X + BOX_W, row_line_y)

    # Línea vertical entre label y valor
    c.setStrokeColor(colors.HexColor("#6688AA"))
    c.setLineWidth(0.8)
    c.line(BOX_X + LABEL_W, BOX_Y, BOX_X + LABEL_W, BOX_Y + BOX_H)

    # Borde exterior de la tabla
    c.setStrokeColor(AZUL)
    c.setLineWidth(1.2)
    c.rect(BOX_X, BOX_Y, BOX_W, BOX_H, fill=0, stroke=1)

    # Texto de cada fila
    PAD = 0.3 * cm
    for i, (label, value) in enumerate(fields):
        text_y = BOX_Y + BOX_H - (i + 1) * ROW_H + (ROW_H - 11) / 2

        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(AZUL)
        c.drawString(BOX_X + PAD, text_y, label)

        c.setFont("Helvetica", 11)
        c.setFillColor(colors.black)
        c.drawString(BOX_X + LABEL_W + PAD, text_y, value)

    # ── 7. LÍNEAS SEPARADORAS INFERIORES ──────────────────────────────────
    BOT_Y = MARGIN + 1.0 * cm

    c.setStrokeColor(ROJO)
    c.setLineWidth(1)
    c.line(MARGIN, BOT_Y + 5, PAGE_W - MARGIN, BOT_Y + 5)

    c.setStrokeColor(AZUL)
    c.setLineWidth(2.5)
    c.line(MARGIN, BOT_Y, PAGE_W - MARGIN, BOT_Y)

    c.save()
    return output_path


def _draw_centered_block(c, text, cx, center_y, max_w, font, size, color):
    c.setFont(font, size)
    c.setFillColor(color)
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        if c.stringWidth(test, font, size) <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    line_h = size * 1.4
    start_y = center_y + (len(lines) * line_h) / 2
    for line in lines:
        c.drawCentredString(cx, start_y, line)
        start_y -= line_h


def prepend_cover_to_pdf(cover_path: str, original_pdf_path: str,
                          output_path: str) -> str:
    """Inserta la portada al inicio de un PDF existente."""
    writer = PdfWriter()
    for page in PdfReader(cover_path).pages:
        writer.add_page(page)
    for page in PdfReader(original_pdf_path).pages:
        writer.add_page(page)
    with open(output_path, "wb") as f:
        writer.write(f)
    return output_path


if __name__ == "__main__":
    cover = generate_cover(
        alumno="Constantino Lemus Jared Said",
        maestro="Cervantes Chirinos Erick Emmanuel",
        materia="Probabilidad y estadística",
        tema="Distribuciones de probabilidad",
        grado_grupo="3.- M",
        fecha="25/03/2026",
        output_path=os.path.join(BASE_DIR, "portada_prueba.pdf"),
    )
    print(f"Portada generada: {cover}")
