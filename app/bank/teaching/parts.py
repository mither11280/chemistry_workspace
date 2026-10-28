"""Native-point subpart boundaries. QP labels and MS labels must independently agree."""
from collections import defaultdict
import re
import fitz
from ..pdf_layout import layout_page,canonicalize,transform
from ..importer.parsing import body,horizontal_rules,has_content,region
from ..importer.ms_layout import columns,count_marks

LABEL=re.compile(r'^(\d+)\(([a-z])\)(?:\(([ivx]+)\))?$')

def label_path(value):
    m=LABEL.fullmatch(re.sub(r'\s+','',value))
    return (int(m[1]),tuple(x for x in m.groups()[1:] if x)) if m else None

def ms_label(row):
    """Join touching label tokens, excluding parenthesised answer prose."""
    row=sorted(row,key=lambda w:w[0]);tokens=[row[0]]
    for word in row[1:]:
        if word[0]>tokens[-1][2]+3:break
        tokens.append(word)
    text=''.join(w[4] for w in tokens)
    text=re.sub(r'^(\d+)\(\(',r'\1(',text)
    return label_path(text),bool(re.match(r'^\d+\([a-z]',text))

def supplement_contexts(parts,overrides,doc=None):
    """Apply explicitly checked cross-letter introductions, never scored answers.

    Only introductions already measured within the same parent may be reused.
    A missing key is an error rather than a guessed replacement region.
    """
    import copy
    by_id={p['id']:p for p in parts}
    for part in parts:
        for item in overrides.get(part['id'],[]):
            origin=by_id.get(item['from_question_id'])
            if origin is None:raise ValueError('Context must come from the same parent: '+part['id'])
            if not item.get('reason'):raise ValueError('Context correction requires a reason')
            found=[c for c in origin['contexts'] if c['key']==item['context_key']]
            if len(found)!=1:raise ValueError('Unknown shared context: '+item['context_key'])
            context=found[0]
            if not any(c['key']==context['key'] for c in part['contexts']):part['contexts'].append(copy.deepcopy(context))
        if overrides.get(part['id']) and doc is not None:
            part['contexts'].sort(key=lambda c:min((r['page_index'],r['bbox'][1]) for r in logical_regions(doc,c['regions'])))

def ms_parts(doc):
    cached=getattr(doc,'_teaching_ms_parts_v1',None)
    if cached is not None:return cached
    result={};issues=[]
    for pi in range(1,len(doc)):
        p=layout_page(doc,pi);ws=p.get_text('words');col=columns(p);top,bottom=body(p);anchors=[]
        # Cluster words on a baseline, permitting old PDFs to split 1 (a) (ii).
        by_y=defaultdict(list)
        for w in ws:
            if col['question_min']<=w[0]<col['question_max'] and top<=w[1]<bottom:by_y[round(w[1]/3)*3].append(w)
        for row in by_y.values():
            # Some older embedded fonts duplicate the same opening parenthesis
            # in overlapping words: "3(" + "(b)(ii)". Their visible label is exact.
            parsed,malformed=ms_label(row)
            if parsed:anchors.append((min(w[1] for w in row),parsed))
            elif malformed:
                # A printed typo such as 4(a(i) or 1(b)(i)(v) is a row
                # boundary, never extra scoring content for the previous row.
                anchors.append((min(w[1] for w in row),(-1,())))
        anchors=sorted(set(anchors));rules=horizontal_rules(p)
        starts=[max((v for v in rules if (anchors[i-1][0]+8 if i else top)<=v<=y),default=max(top,y-5)) for i,(y,_) in enumerate(anchors)]
        for i,(y,key) in enumerate(anchors):
            if key[0]<0:continue
            start=starts[i]
            next_y=anchors[i+1][0] if i+1<len(anchors) else None
            end=starts[i+1] if next_y else min(bottom,max((v for v in rules if v>y and v<=bottom),default=bottom))
            if end<=start:issues.append('ms_nonpositive_row');continue
            box=[col['left'],start,col['right'],end]
            row=[w for w in ws if start-.1<=w[1] and w[3]<=end+.5]
            entry=result.setdefault(key,{'regions':[],'marks':0,'text':''})
            entry['regions']+=canonicalize(doc,[region(pi,box)])
            entry['marks']+=count_marks(p,row)
            entry['text']+='\n'+p.get_text(clip=fitz.Rect(box))
    doc._teaching_ms_parts_v1=(result,issues)
    return result,issues

def logical_regions(doc,regions):
    return [dict(r,bbox=list(fitz.Rect(r['bbox'])*transform(doc,r['page_index']))) for r in regions]

def slices(doc,parent,start,end):
    out=[]
    for r in parent:
        pi=r['page_index'];b=r['bbox'];lo=max(b[1],start[1] if pi==start[0] else b[1]);hi=min(b[3],end[1] if pi==end[0] else b[3])
        if start[0]<=pi<=end[0] and hi-lo>3:
            box=[b[0],lo,b[2],hi]
            if has_content(layout_page(doc,pi),box):out.append(region(pi,box))
    return out

def safe_anchor_start(page,word):
    """Locate an actual white scanline when font bounding boxes overlap a prior mark.
    Rendering is an analysis aid only; the saved result is a native PDF-point cut.
    """
    y=word[1]-3
    previous=[w for w in page.get_text('words') if re.search(r'\[\d+\]$',w[4]) and w[1]<word[1] and w[3]>y]
    if not previous:return y
    box=fitz.Rect(25,max(0,word[1]-9),page.rect.width-20,word[1]+3)
    # Layout pages can be rotated; get_pixmap is delegated in native coordinates.
    if hasattr(page,'matrix'):return y
    scale=3;pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=box,colorspace=fitz.csGRAY,alpha=False)
    raw=pix.samples;candidates=[]
    for row in range(pix.height):
        point=(pix.y+row+.5)/scale
        if point<=word[1]+2 and min(raw[row*pix.stride:row*pix.stride+pix.width],default=0)>=250:candidates.append(point)
    return min(candidates,key=lambda v:abs(v-word[1])) if candidates else y


def qp_parts(doc,parent,n):
    """Return leaves with ancestor introduction regions, never preceding sibling answers."""
    rs=logical_regions(doc,parent);anchors=[];issues=[]
    for r in rs:
        p=layout_page(doc,r['page_index']);width=p.rect.width
        for w in p.get_text('words',clip=fitz.Rect(r['bbox'])):
            m=re.fullmatch(r'\(([a-z]+)\)',w[4])
            if not m:continue
            x=w[0]/width;v=m[1]
            if re.fullmatch(r'[ivx]+',v) and .15<=w[2]/width<=.20 and .125<=x<=.195:kind='roman'
            elif len(v)==1 and .095<=x<=.148:kind='letter'
            else:continue
            anchors.append({'kind':kind,'value':v,'pos':(r['page_index'],safe_anchor_start(p,w))})
    anchors.sort(key=lambda a:a['pos']);letter=None
    for a in anchors:
        if a['kind']=='letter':letter=a['value'];a['path']=(letter,)
        elif letter:a['path']=(letter,a['value'])
        else:issues.append('roman_without_letter');a['path']=None
    anchors=[a for a in anchors if a['path']]
    if len({a['path'] for a in anchors})!=len(anchors):issues.append('ambiguous_subpart_anchors')
    if not anchors:return [],issues+['no_subpart_anchors']
    root_start=(rs[0]['page_index'],rs[0]['bbox'][1]);root_end=(rs[-1]['page_index'],rs[-1]['bbox'][3]);contexts=[]
    intro=slices(doc,rs,root_start,anchors[0]['pos'])
    if intro:contexts.append({'key':str(n),'regions':canonicalize(doc,intro)})
    leaves=[]
    for i,a in enumerate(anchors):
        end=anchors[i+1]['pos'] if i+1<len(anchors) else root_end
        if len(a['path'])==1 and i+1<len(anchors) and anchors[i+1]['path'][:1]==a['path'] and len(anchors[i+1]['path'])==2:
            continue
        context=list(contexts)
        if len(a['path'])==2:
            ancestor=next(z for z in anchors if z['path']==a['path'][:1])
            first=next(z for z in anchors if len(z['path'])==2 and z['path'][:1]==a['path'][:1])
            cr=slices(doc,rs,ancestor['pos'],first['pos'])
            if cr:context.append({'key':f'{n}({a["path"][0]})','regions':canonicalize(doc,cr)})
        own=slices(doc,rs,a['pos'],end)
        text='\n'.join(layout_page(doc,r['page_index']).get_text(clip=fitz.Rect(r['bbox'])) for r in own)
        marks=[];mark_positions=[]
        for r in own:
            for word in layout_page(doc,r['page_index']).get_text('words'):
                m=re.search(r'\[(\d+)\]$',word[4]);cy=(word[1]+word[3])/2
                if m and r['bbox'][1]<=cy<r['bbox'][3]:marks.append(int(m[1]));mark_positions.append((r['page_index'],word[3]+2))
        leaves.append({'path':a['path'],'label':str(n)+''.join('('+v+')' for v in a['path']),'own_regions':canonicalize(doc,own),'contexts':context,'text':text,'marks':sum(marks) if marks else None,'order':len(leaves),'terminal_mark':max(mark_positions) if mark_positions else None})
    # A table or narrative printed after the preceding score belongs to the following
    # subparts, not to the preceding task. Keep it as an explicitly shared lead-in.
    for i,leaf in enumerate(leaves[:-1]):
        terminal=leaf.get('terminal_mark')
        if not terminal:continue
        native=logical_regions(doc,leaf['own_regions']);end=(native[-1]['page_index'],native[-1]['bbox'][3])
        tail=slices(doc,native,terminal,end)
        text='\n'.join(layout_page(doc,r['page_index']).get_text(clip=fitz.Rect(r['bbox'])) for r in tail)
        narrative=re.search(r'\b(?:The|A|An|Table|Fig|Figure|Some|When|Each|Use|In|This|These|For|Two|Three|Four)\b',text)
        labelled_compound=re.search(r'\b[A-Z](?:\s+and\s+[A-Z])?(?:,\s*[A-Za-z0-9]+,)?\s+(?:has|is|are|shows|reacts|contains)\b',text)
        if not (narrative or labelled_compound):continue
        before=slices(doc,native,(native[0]['page_index'],native[0]['bbox'][1]),terminal)
        before_text='\n'.join(layout_page(doc,r['page_index']).get_text(clip=fitz.Rect(r['bbox'])) for r in before)
        def references_in(value):
            # PDF extraction may use a nonbreaking/thin space in a reference and
            # a normal space in the corresponding caption. Compare identities.
            return {(kind.lower().rstrip('.'),number) for kind,number in
                    re.findall(r'(Table|Fig\.?|Figure)\s*(\d+\.\d+)',value,re.I)}
        references=references_in(before_text)
        tail_references=references_in(text)
        if references & tail_references:continue  # appendix printed after its own question's score
        # The standard infrared reference table is sometimes printed after the
        # score without being referred to by its table number in the task.
        if (re.search(r'\binfra[\s-]?red\b',before_text,re.I) and
                re.search(r'absorption',text,re.I) and re.search(r'wavenumber',text,re.I)):
            continue
        leading={'key':str(n)+':lead-after:'+ '-'.join(leaf['path']),'regions':canonicalize(doc,tail)}
        leaf['own_regions']=canonicalize(doc,slices(doc,native,(native[0]['page_index'],native[0]['bbox'][1]),terminal))
        kept=slices(doc,native,(native[0]['page_index'],native[0]['bbox'][1]),terminal)
        leaf['text']='\n'.join(layout_page(doc,r['page_index']).get_text(clip=fitz.Rect(r['bbox'])) for r in kept)
        next_path=leaves[i+1]['path']
        for following in leaves[i+1:]:
            if following['path'][:1]!=next_path[:1]:break
            following['contexts'].append(leading)
    return leaves,issues
