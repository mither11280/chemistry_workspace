"""Programmatic gates; passing is never a claim of human content review."""
import re
import fitz
from ..format import normalized_page


def region_issues(doc, regions):
    issues=[]
    if not regions:return ['empty_regions']
    for r in regions:
        pi=r.get('page_index');box=r.get('bbox',[])
        if not isinstance(pi,int) or not 0<=pi<len(doc) or len(box)!=4:
            issues.append('invalid_region');continue
        p=normalized_page(doc,pi);clip=fitz.Rect(box)
        if not (0<=clip.x0<clip.x1<=p.rect.width+.01 and 0<=clip.y0<clip.y1<=p.rect.height+.01):
            issues.append('out_of_bounds');continue
        pix=p.get_pixmap(matrix=fitz.Matrix(.25,.25),clip=clip,colorspace=fitz.csGRAY,alpha=False)
        if not pix.samples or min(pix.samples)>245:issues.append('blank_region')
        # Inspect the reading orientation while keeping the source bbox canonical.
        from ..pdf_layout import layout_page,transform
        p=layout_page(doc,pi);clip=clip*transform(doc,pi)
        # Ignore diagonal watermarks. Check horizontal text crossing a crop edge.
        for b in p.get_text('dict')['blocks']:
            for line in b.get('lines',[]):
                if abs(line.get('dir',(1,0))[1])>.01:continue
                for span in line['spans']:
                    if not span['text'].strip():continue
                    if span['size']<6 and (span['bbox'][1]>p.rect.height*.9 or any(ord(c)<32 for c in span['text'])):continue  # machine-readable printer/footer code
                    rect=fitz.Rect(span['bbox']);intersection=rect&clip
                    if intersection.is_empty:continue
                    if intersection.width>1 and intersection.height>1 and not clip.contains(rect):
                        # Tiny PDF bounding-box rounding differences are harmless.
                        expanded=fitz.Rect(clip.x0-.8,clip.y0-.8,clip.x1+.8,clip.y1+.8)
                        if not expanded.contains(rect):issues.append('text_crosses_crop_edge')
    return sorted(set(issues))


def pair_issues(qp,ms,paper,total,parse_issues):
    issues=list(parse_issues)
    nums=set(qp);answer_nums=set(ms)
    expected=set(range(1,41)) if paper==1 else set(range(1,max(nums|answer_nums,default=0)+1))
    if nums!=expected:issues.append('qp_number_sequence_incomplete')
    if sum(q.get('marks') or 0 for q in qp.values())!=total:issues.append('qp_total_marks_mismatch')
    # Missing answers quarantine that question. Unknown extra rows indicate an unsafe match.
    if answer_nums-nums:issues.append('unmatched_ms_question_numbers')
    return sorted(set(issues)),sorted(expected-nums),sorted(expected-answer_nums)


def question_issues(q,qp,ms,qdoc,mdoc):
    issues=[]
    if not qp:issues.append('missing_question')
    if not ms:issues.append('missing_answer')
    if qp and ms and qp.get('marks')!=ms.get('marks'):issues.append('qp_ms_marks_mismatch')
    if q['marks'] is None or q['marks']<=0:issues.append('unknown_marks')
    issues += ['question:'+v for v in region_issues(qdoc,q['question']['regions'])]
    issues += ['answer:'+v for v in region_issues(mdoc,q['answer']['regions'])]
    if q['answer']['regions'] and not any('out_of_bounds' in i or 'invalid_region' in i for i in issues):
        issues+=answer_content_issues(q,mdoc)
    return sorted(set(issues))


def answer_content_issues(q,doc):
    """Check the actual cropped MS rows, including question identity, not just its manifest."""
    label=q['original_question_number'];number=int(__import__('re').match(r'\d+',label)[0]);issues=[];marks=0;labels=set();letters=[]
    if q.get('metadata',{}).get('teaching') and q['paper'] in [2,4]:
        from ..teaching.parts import ms_parts,label_path
        from ..teaching.whitespace import tighten
        teaching=q['metadata']['teaching']
        rows,_=ms_parts(doc);expected=label_path(teaching.get('official_answer_label',label));entry=rows.get(expected)
        if not entry:return ['ms_crop_subpart_identity_mismatch']
        if entry['regions']!=q['answer']['regions']:
            # Allow only the independently reproducible, ink-free exterior trim.
            # Arbitrary smaller boxes, missing rows or answer-text clipping fail.
            trimmed=[tighten(doc,r)[0] for r in entry['regions']]
            if trimmed!=q['answer']['regions']:issues.append('ms_crop_subpart_region_mismatch')
        if entry['marks']!=q['marks']:issues.append('ms_crop_marks_mismatch')
        return issues
    for r in q['answer']['regions']:
        from ..pdf_layout import layout_page,transform
        from .ms_layout import labels as ms_labels,count_marks
        p=layout_page(doc,r['page_index']);box=fitz.Rect(r['bbox'])*transform(doc,r['page_index']);ws=p.get_text('words',clip=box)
        if q['paper']==1:
            labels.update(int(w[4]) for w in ws if w[4].isdigit() and p.rect.width*.10<w[0]<p.rect.width*.22)
            letters += [w[4] for w in ws if w[4] in ['A','B','C','D']]
        else:
            labels.update(n for n,_ in ms_labels(p,ws))
            marks+=count_marks(p,ws)
    if labels!={number}:issues.append('ms_crop_question_identity_mismatch')
    if q['paper']==1:
        if len(letters)!=1 or (q['answer'].get('value') is not None and letters[0]!=q['answer']['value']):issues.append('mcq_answer_row_ambiguous')
    elif marks!=q['marks']:issues.append('ms_crop_marks_mismatch')
    return issues
