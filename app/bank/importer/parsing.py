"""Conservative text/geometry parsers. Region order follows the source; diagrams stay vector."""
from collections import defaultdict
import re
import fitz
from ..format import normalized_page

def words(page):return page.get_text('words')
def body(page):
    w,h=page.rect.width,page.rect.height
    foot=[r[1] for r in words(page) if r[1]>h*.85 and (r[4]=='©' or re.match(r'9701/',r[4]) or r[4]=='[Turn')]
    return 54,min(foot)-3 if foot else h-35

def reference_page(page):return bool(re.search(r'^\s*(?:BLANK PAGE|The Periodic Table(?: of Elements)?)\s*$',page.get_text(),re.I|re.M))
def region(page,bbox):return {'page_index':page,'bbox':[round(float(v),3) for v in bbox]}

def question_starts(doc):
    strong=[];weak=[]
    for pi in range(1,len(doc)):
        p=normalized_page(doc,pi)
        if reference_page(p):continue
        top,bottom=body(p)
        for block in p.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    text=span['text'].strip();box=span['bbox']
                    if text.isdigit() and 1<=int(text)<=200 and p.rect.width*.07<=box[0]<=p.rect.width*.105 and top<=box[1]<bottom:
                        rec=(int(text),pi,box[1]-3)
                        weak.append(rec)
                        if 'bold' in span['font'].lower() or span['flags']&16:strong.append(rec)
    selected=strong if strong else weak
    return sorted(set(selected),key=lambda r:(r[1],r[2]))

def parse_qp(doc,paper):
    starts=question_starts(doc);result={};issues=[]
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
            if bottom>top+8:regions.append(region(k,[44,top,p.rect.width-43,bottom]))
            if stop:break
        if n in result:continue
        text='\n'.join(normalized_page(doc,r['page_index']).get_text(clip=fitz.Rect(r['bbox'])) for r in regions)
        totals=re.findall(r'\[Total\s*:\s*(\d+)\]',text)
        bracket_marks=list(map(int,re.findall(r'\[(\d+)\]',text)))
        result[n]={'regions':regions,'marks':1 if paper==1 else int(totals[-1]) if len(totals)==1 else sum(bracket_marks) if bracket_marks else None,'explicit_total':int(totals[-1]) if len(totals)==1 else None,'bracket_sum':sum(bracket_marks),'text':text}
    return result,issues

def horizontal_rules(page):
    ys=[]
    for draw in page.get_drawings():
        box=draw['rect']
        if box.width>page.rect.width*.7:ys.extend([box.y0,box.y1])
        for item in draw['items']:
            if item[0]=='l' and abs(item[1].y-item[2].y)<.2 and abs(item[1].x-item[2].x)>page.rect.width*.7:ys.append(item[1].y)
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
            labels=[]
            for word in ws:
                match=re.fullmatch(r'(\d+)(?:\([a-z]\))(?:\([ivx]+\))?',word[4])
                if match and p.rect.width*.06<word[0]<p.rect.width*.17 and top<=word[1]<bottom:labels.append((int(match[1]),word[1]))
            labels=sorted(set(labels),key=lambda v:v[1]);groups=[]
            for n,y in labels:
                if not groups or groups[-1][0]!=n:groups.append((n,y))
            if not groups:continue
            rules=horizontal_rules(p)
            def border(y):return max((v for v in rules if y-45<v<=y),default=y-7)
            for i,(n,y) in enumerate(groups):
                start=max(top,border(y));end=border(groups[i+1][1]) if i+1<len(groups) else min(bottom,max((v for v in rules if v>y and v<=bottom),default=bottom))
                rs=region(pi,[max(35,p.rect.width*.07),start,p.rect.width-60,end])
                marks=[int(w[4]) for w in ws if w[4].isdigit() and 0<int(w[4])<=30 and w[0]>p.rect.width*.87 and start<=w[1] and w[3]<=end+.5 and not any('total' in z[4].lower() for z in ws if abs(z[1]-w[1])<3)]
                entry=result.setdefault(n,{'regions':[],'marks':0,'row_count':0});entry['regions'].append(rs);entry['marks']+=sum(marks);entry['row_count']+=sum(1 for num,yy in labels if num==n and start<=yy<=end)
    return result,issues

def references(doc,paper,role,ms):
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
        refs=[dict(region(pi,list(normalized_page(doc,pi).rect)),rotate=0) for pi in range(1,first) if not reference_page(normalized_page(doc,pi))]
    return refs
