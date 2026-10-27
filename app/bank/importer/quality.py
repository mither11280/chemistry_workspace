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
    if q['paper']==1:
        text='\n'.join(normalized_page(mdoc,r['page_index']).get_text(clip=fitz.Rect(r['bbox'])) for r in q['answer']['regions'])
        letters=re.findall(r'\b[A-D]\b',text)
        if letters!=[q['answer'].get('value')]:issues.append('mcq_answer_row_ambiguous')
    return sorted(set(issues))


def answer_content_issues(q,doc):
    """Check the actual cropped MS rows, including question identity, not just its manifest."""
    number=int(q['original_question_number']);issues=[];marks=0;labels=set();letters=[]
    for r in q['answer']['regions']:
        p=normalized_page(doc,r['page_index']);box=fitz.Rect(r['bbox']);ws=p.get_text('words',clip=box)
        if q['paper']==1:
            labels.update(int(w[4]) for w in ws if w[4].isdigit() and p.rect.width*.10<w[0]<p.rect.width*.22)
            letters += [w[4] for w in ws if w[4] in ['A','B','C','D']]
        else:
            labels.update(int(re.match(r'^(\d+)\(',w[4])[1]) for w in ws if re.match(r'^\d+\([a-z]\)',w[4]) and p.rect.width*.06<w[0]<p.rect.width*.17)
            marks+=sum(int(w[4]) for w in ws if w[4].isdigit() and 0<int(w[4])<=30 and w[0]>p.rect.width*.87 and not any('total' in z[4].lower() for z in ws if abs(z[1]-w[1])<3))
    if labels!={number}:issues.append('ms_crop_question_identity_mismatch')
    if q['paper']==1:
        if letters!=[q['answer'].get('value')]:issues.append('mcq_answer_row_ambiguous')
    elif marks!=q['marks']:issues.append('ms_crop_marks_mismatch')
    return issues
