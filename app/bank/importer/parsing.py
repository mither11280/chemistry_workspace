"""Conservative text/geometry parsers. Region order follows the source; diagrams stay vector."""
from collections import defaultdict,Counter
import re
from itertools import product
import fitz
from ..pdf_layout import layout_page as normalized_page
from .ms_layout import columns,labels as ms_labels,count_marks

def words(page):return page.get_text('words')
def body(page):
    w,h=page.rect.width,page.rect.height
    foot=[r[1] for r in words(page) if r[1]>h*.35 and (r[4]=='©' or re.match(r'(?:\d{2}_)?9701[_/]',r[4]) or r[4]=='[Turn')]
    page_numbers=[r[3]+4 for r in words(page) if r[4]==str(page.number+1) and w*.43<r[0]<w*.57 and r[1]<min(54,h*.065)]
    scale=min(1,(min(foot)/(h*.94))) if foot else 1
    return max([54*scale]+page_numbers),min(foot)-1 if foot else h-35

def reference_page(page):return bool(re.search(r'^\s*(?:BLANK PAGE|The Periodic Table(?: of Elements)?)\s*$',page.get_text(),re.I|re.M))
def region(page,bbox):return {'page_index':page,'bbox':[round(float(v),3) for v in bbox]}

def question_starts(doc):
    strong=[];weak=[]
    for pi in range(1,len(doc)):
        p=normalized_page(doc,pi)
        if reference_page(p):continue
        top,bottom=body(p)
        blocks=p.get_text('dict')['blocks']
        all_spans=[s for b in blocks for line in b.get('lines',[]) if abs(line.get('dir',(1,0))[1])<.01 for s in line['spans']]
        for block in blocks:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    text=span['text'].strip();box=span['bbox']
                    if text.isdigit() and 1<=int(text)<=200 and p.rect.width*.07<=box[0]<=p.rect.width*.105 and top<=box[1]<bottom:
                        baseline=span['origin'][1]
                        start=min([box[1]]+[s['bbox'][1] for s in all_spans if abs(s['origin'][1]-baseline)<7 and s['bbox'][0]>box[0]])-3
                        rec=(int(text),pi,start,box[0])
                        weak.append(rec)
                        if 'bold' in span['font'].lower() or span['flags']&16:strong.append(rec)
    selected=strong if strong else weak
    if not selected:return []
    alignment=Counter(round(r[3]) for r in selected).most_common(1)[0][0]
    # Main numbers align down the margin; diagram labels can be bold digits nearby.
    selected=[r[:3] for r in selected if abs(r[3]-alignment)<=2.5]
    return sorted(set(selected),key=lambda r:(r[1],r[2]))

def parse_qp(doc,paper,starts=None):
    starts=question_starts(doc) if starts is None else starts;result={};issues=[]
    by_number=defaultdict(list)
    for anchor in starts:by_number[anchor[0]].append(anchor)
    expected=list(range(1,(40 if paper==1 else max(by_number,default=0))+1))
    combinations=1
    for anchors in by_number.values():combinations*=len(anchors)
    if set(by_number)==set(expected) and 1<combinations<=64:
        # A repeated digit after a later question can be a diagram label. Resolve only
        # when exactly one choice preserves the complete chronological question sequence.
        valid=[]
        for selection in product(*(by_number[n] for n in expected)):
            ordered=sorted(selection,key=lambda v:(v[1],v[2]))
            if [v[0] for v in ordered]==expected:valid.append(ordered)
        if len(valid)==1:starts=valid[0]
    counts=defaultdict(int)
    for n,_,_ in starts:counts[n]+=1
    if any(x>1 for x in counts.values()):issues.append('ambiguous_question_number_anchors')
    for j,(n,pi,y) in enumerate(starts):
        end=starts[j+1][1:] if j+1<len(starts) else (len(doc)-1,99999)
        regions=[]
        for k in range(pi,end[0]+1):
            p=normalized_page(doc,k)
            if reference_page(p):break
            bodytop,bodybottom=body(p);top=y if k==pi else bodytop
            bottom=min(bodybottom,end[1]-4 if k==end[0] and j+1<len(starts) else bodybottom)
            for hit in p.search_for('Important values'):bottom=min(bottom,hit.y0-7)
            totals=[hit for hit in p.search_for('[Total:') if hit.y0>=top and hit.y0<bottom]
            stop=False
            if paper!=1 and totals:
                bottom=min(bottom,totals[0].y1+6);stop=True
            if bottom>top+8:
                box=[25,top,p.rect.width-20,bottom]
                if k==pi or has_content(p,box):regions.append(region(k,box))
            if stop:break
        if n in result:continue
        text='\n'.join(normalized_page(doc,r['page_index']).get_text(clip=fitz.Rect(r['bbox'])) for r in regions)
        totals=re.findall(r'\[Total\s*:\s*(\d+)\]',text)
        bracket_marks=list(map(int,re.findall(r'\[(\d+)\]',text)))
        result[n]={'regions':regions,'marks':1 if paper==1 else int(totals[-1]) if len(totals)==1 else sum(bracket_marks) if bracket_marks else None,'explicit_total':int(totals[-1]) if len(totals)==1 else None,'bracket_sum':sum(bracket_marks),'text':text}
    return result,issues

def has_content(page,box):
    clip=fitz.Rect(box)
    if page.get_text(clip=clip).strip():return True
    for drawing in page.get_drawings():
        rect=drawing['rect'];rect=fitz.Rect(rect.x0-1,rect.y0-1,rect.x1+1,rect.y1+1)
        if not (rect&clip).is_empty:return True
    for image in page.get_images(full=True):
        for rect in page.get_image_rects(image[0]):
            if hasattr(page,'matrix'):rect=rect*page.matrix
            if not (rect&clip).is_empty:return True
    return False

def horizontal_rules(page):
    ys=[];left_limit=columns(page)['left']+18
    for draw in page.get_drawings():
        box=draw['rect']
        if box.width>page.rect.width*.7 and box.x0<=left_limit:ys.extend([box.y0,box.y1])
        for item in draw['items']:
            if item[0]=='l' and abs(item[1].y-item[2].y)<.2 and abs(item[1].x-item[2].x)>page.rect.width*.7 and min(item[1].x,item[2].x)<=left_limit:ys.append(item[1].y)
    return sorted(set(ys))

def parse_ms(doc,paper):
    result={};issues=[]
    if paper==1:
        for pi in range(1,len(doc)):
            p=normalized_page(doc,pi);ws=words(p);top,bottom=body(p)
            for word in ws:
                if word[4].isdigit() and 1<=int(word[4])<=40 and p.rect.width*.10<word[0]<p.rect.width*.22 and top<=word[1]<bottom:
                    row=[w for w in ws if abs(w[1]-word[1])<3]
                    letters=[w[4] for w in row if w[4] in ['A','B','C','D'] and w[0]>word[2]]
                    if len(letters)!=1:continue
                    n=int(word[4])
                    if n in result:issues.append(f'duplicate_ms_row:{n}');continue
                    result[n]={'regions':[region(pi,[max(35,word[0]-20),word[1]-5,p.rect.width-40,word[3]+5])],'marks':1,'value':letters[0]}
    else:
        for pi in range(1,len(doc)):
            p=normalized_page(doc,pi);ws=words(p);top,bottom=body(p)
            labels=[v for v in ms_labels(p,ws) if top<=v[1]<bottom]
            labels=sorted(set(labels),key=lambda v:v[1]);groups=[]
            for n,y in labels:
                if not groups or groups[-1][0]!=n:groups.append((n,y))
            if not groups:continue
            rules=horizontal_rules(p)
            def border(y):return max((v for v in rules if v<=y),default=y-7)
            for i,(n,y) in enumerate(groups):
                start=max(top,border(y));end=border(groups[i+1][1]) if i+1<len(groups) else min(bottom,max((v for v in rules if v>y and v<=bottom),default=bottom))
                col=columns(p);rs=region(pi,[col['left'],start,col['right'],end])
                marks=count_marks(p,[w for w in ws if start<=w[1] and w[3]<=end+.5])
                entry=result.setdefault(n,{'regions':[],'marks':0,'row_count':0});entry['regions'].append(rs);entry['marks']+=marks;entry['row_count']+=sum(1 for num,yy in labels if num==n and start<=yy<=end)
    return result,issues

def references(doc,paper,role,ms):
    from ..format import normalized_page
    from ..pdf_layout import rotation
    refs=[]
    for pi in range(1,len(doc)):
        p=normalized_page(doc,pi);text=p.get_text()
        if role=='qp' and reference_page(p) and re.search(r'^\s*The Periodic Table',text,re.M):refs.append(dict(region(pi,list(p.rect)),rotate=270 if p.rect.height>p.rect.width else 0))
        if role=='qp':
            for hit in p.search_for('Important values'):
                # Data is an appendix from its heading to the footer, never silently cropped to a guessed height.
                refs.append(dict(region(pi,[44,hit.y0,p.rect.width-43,body(p)[1]]),rotate=0))
    if role=='ms' and paper!=1 and ms:
        first=min(r['page_index'] for value in ms.values() for r in value['regions'])
        refs=[dict(region(pi,list(normalized_page(doc,pi).rect)),rotate=(-rotation(doc,pi))%360) for pi in range(1,first) if not reference_page(normalized_page(doc,pi))]
    return refs
