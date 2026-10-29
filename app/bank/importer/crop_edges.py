"""Verify font-box edge overlaps against visible source ink, in native PDF points.

Embedded font ascenders/descenders often overlap a safe inter-line cut. This
does not make a clipped glyph safe: every excluded portion must render blank.
The raster is inspection evidence only; coordinates and exports remain vector.
"""
import fitz
from ..format import normalized_page
from ..pdf_layout import transform

PROOF_VERSION = 'excluded-font-box-ink-v1-288dpi'


def excluded_boxes(rect, clip):
    """Disjoint parts of rect outside clip; do not inspect adjacent kept text."""
    inside = rect & clip
    if inside.is_empty:
        return [rect]
    return [box for box in (
        fitz.Rect(rect.x0, rect.y0, rect.x1, inside.y0),
        fitz.Rect(rect.x0, inside.y1, rect.x1, rect.y1),
        fitz.Rect(rect.x0, inside.y0, inside.x0, inside.y1),
        fitz.Rect(inside.x1, inside.y0, rect.x1, inside.y1),
    ) if not box.is_empty]


def excluded_ink_free(doc, page_index, rect, clip):
    """Fail closed when an excluded band has ink or cannot be measured.

Inputs use the logical reading layout; render in canonical unrotated space.
Pixel cells intersecting a band are included (rather than sampling a band
midpoint), so a thin chemical stroke cannot be excused by fractional bounds.
"""
    page = normalized_page(doc, page_index)
    inverse = ~transform(doc, page_index)
    boxes = [box * inverse for box in excluded_boxes(rect, clip)]
    if not boxes:
        return True
    for box in boxes:
        if not page.rect.contains(box):
            return False
        pix = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=box,
                              colorspace=fitz.csGRAY, alpha=False)
        if not pix.width or not pix.height:
            return False
        # MuPDF rounds the clip to outward pixel boundaries. Retaining these
        # complete cells deliberately favours false alarms over lost glyphs.
        if min(pix.samples, default=0) < 250:
            return False
    return True
