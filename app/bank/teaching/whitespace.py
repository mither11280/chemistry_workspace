"""Conservative outer vertical whitespace removal, measured in canonical PDF points.

No internal gap is removed. Ink, glyph bounds, vector paths, images and annotation
appearance protect their full vertical extent. Purely empty/rotated/uncertain
regions retain their original geometry. Source documents are never saved.
"""
import math
import re
import fitz
from ..format import normalized_page
from ..pdf_layout import rotation

VERSION='outer-vertical-ink-and-geometry-v2-answer-space-guard'


def tighten(doc,region,padding=6,preserve_answer_space=False):
    original=dict(region,bbox=list(region['bbox']));box=fitz.Rect(original['bbox']);pi=original['page_index']
    if rotation(doc,pi):return original,None
    page=normalized_page(doc,pi)
    if not page.rect.contains(box) or box.height<2*padding+4:return original,None
    protected=[]
    for block in page.get_text('dict')['blocks']:
        if block.get('type')==1:protected.append(fitz.Rect(block['bbox']))
        for line in block.get('lines',[]):
            for span in line['spans']:
                if span['text'].strip():protected.append(fitz.Rect(span['bbox']))
    for drawing in page.get_drawings():
        rect=fitz.Rect(drawing['rect']);w=max(float(drawing.get('width') or 0),.5)/2
        protected.append(fitz.Rect(rect.x0-w,rect.y0-w,rect.x1+w,rect.y1+w))
    for image in page.get_images(full=True):protected.extend(page.get_image_rects(image[0]))
    scale=2;pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=box,colorspace=fitz.csGRAY,alpha=False,annots=True)
    if not pix.width or not pix.height:return original,None
    raw=pix.samples;ink=[]
    for y in range(pix.height):
        if min(raw[y*pix.stride:y*pix.stride+pix.width],default=255)<248:ink.append(y)
    if not ink:return original,None
    lo=(pix.y+ink[0])/scale;hi=(pix.y+ink[-1]+1)/scale
    for r in protected:
        r=r&box
        if not r.is_empty:lo=min(lo,r.y0);hi=max(hi,r.y1)
    y0=max(box.y0,math.floor((lo-padding)*1000)/1000);y1=min(box.y1,math.ceil((hi+padding)*1000)/1000)
    if preserve_answer_space:
        # Ink-free is not sufficient proof that an answer area is dispensable.
        # Some prompts print [n] on the instruction line, leaving an unruled
        # area beneath it. Keep that area's original lower boundary. A score
        # printed after substantial answer space, or on an actual answer line,
        # provides an independently identifiable terminal boundary.
        words=page.get_text('words',clip=box)
        marks=[w for w in words if re.fullmatch(r'\[\d+\]',w[4])]
        text=' '.join(w[4] for w in words)
        directive=bool(re.search(r'\b(?:draw|sketch|calculate|construct|complete|explain|describe|suggest|deduce|predict|write|show|determine)\b',text,re.I))
        if marks:
            last=max(marks,key=lambda w:w[3]);near=[w for w in words if abs((w[1]+w[3]-last[1]-last[3])/2)<4]
            answer_line=any(re.search(r'[._·…]{4,}',w[4]) for w in near)
            prose=[w[3] for w in words if w[1]<=last[1]+2 and re.search(r'[A-Za-z]{2}',w[4]) and not re.search(r'UCLES|9701|Total',w[4],re.I)]
            score_near_prompt=bool(prose) and 0<=last[3]-max(prose)<35
            if directive and score_near_prompt and not answer_line and box.y1-last[3]>48:y1=box.y1
        elif directive and box.y1-hi>48:
            y1=box.y1  # an unfinished cross-page task has no terminal mark here
    if box.height-(y1-y0)<4:return original,None
    result=dict(original,bbox=[box.x0,y0,box.x1,y1])
    # Independently inspect the discarded bands. Never remove visible ink even
    # when geometric extraction returned incomplete bounds.
    for a,b in [(box.y0,y0),(y1,box.y1)]:
        if b-a<=.5:continue
        strip=page.get_pixmap(matrix=fitz.Matrix(2,2),clip=fitz.Rect(box.x0,a,box.x1,b),colorspace=fitz.csGRAY,alpha=False,annots=True)
        if min(strip.samples,default=255)<248:return original,None
    return result,{'method':VERSION,'page_index':pi,'before_bbox':list(box),'after_bbox':result['bbox'],'padding_points':padding,'removed_height_points':round(box.height-(y1-y0),3),'discarded_bands_ink_free':True,'internal_answer_space_preserved':True,'unruled_answer_space_guard':preserve_answer_space}
