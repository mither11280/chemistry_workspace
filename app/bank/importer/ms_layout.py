"""Shared MS column/label analysis, including split historical labels. No answer prose stored."""
import re

def columns(page):
    ws=page.get_text('words');w=page.rect.width
    heads=[v for v in ws if v[4].lower()=='marks' and v[0]>w*.5 and 30<=v[1]<page.rect.height*.7]
    mark=min(heads,key=lambda v:v[1]) if heads else None
    questions=[v for v in ws if v[4].lower()=='question' and v[0]<w*.3]
    question=min(questions,key=lambda v:v[1]) if questions else None
    mark_min=mark[0]-max(3,w*.006) if mark else w*.87
    mark_max=w
    if mark:
        center=(mark[0]+mark[2])/2;y=(mark[1]+mark[3])/2;vertical=[]
        for drawing in page.get_drawings():
            box=drawing['rect']
            if box.y0-.5<=y<=box.y1+.5 and box.height>8:vertical.extend([box.x0,box.x1])
            for item in drawing['items']:
                if item[0]=='l':
                    a,b=item[1:3]
                    if abs(a.x-b.x)<.3 and min(a.y,b.y)-.5<=y<=max(a.y,b.y)+.5 and abs(a.y-b.y)>8:vertical.append(a.x)
                if item[0]=='re':
                    box=item[1]
                    if box.y0-.5<=y<=box.y1+.5 and box.height>8:vertical.extend([box.x0,box.x1])
        left=max((x for x in vertical if x<center),default=mark_min)
        right=min((x for x in vertical if x>center),default=w)
        if left<=mark[0]+1 and right>=mark[2]-1:mark_min=left-1;mark_max=right+1
    return {'marks_min':mark_min,'marks_max':mark_max,'question_max':w*.23,'question_min':max(15,(question[0]-15) if question else w*.045),'right':min(w-12,max(w-35,(mark[2]+18) if mark else 0)),'left':max(15,(question[0]-12) if question else w*.045)}

def labels(page,ws=None):
    ws=page.get_text('words') if ws is None else ws;col=columns(page);result=[]
    for word in ws:
        if not col['question_min']<=word[0]<col['question_max']:continue
        text=re.sub(r'\s+','',word[4]);match=re.fullmatch(r'(\d+)(?:\([a-z]\))(?:\([ivx]+\))?',text)
        if match:result.append((int(match[1]),word[1]));continue
        if word[4].isdigit() and 1<=int(word[4])<=20:
            parts=[v for v in ws if abs(v[1]-word[1])<3 and word[2]<v[0]<col['question_max'] and re.match(r'^\([a-z]\)',v[4])]
            if parts:result.append((int(word[4]),word[1]))
    return sorted(set(result),key=lambda v:v[1])

def count_marks(page,ws):
    col=columns(page);threshold=col['marks_min']
    result=0
    for w in ws:
        if not (w[4].isdigit() and 0<int(w[4])<=30 and threshold<=w[0]<col['marks_max']):continue
        left=sorted((z for z in ws if abs(z[1]-w[1])<3 and z[0]<threshold),key=lambda z:z[0])
        # A subtotal label is not an awarded mark. "total electrons in s
        # subshell", however, is an actual scored table row, not a subtotal.
        if re.search(r'\btotal(?:\s+marks?)?\s*:?\s*$',' '.join(z[4] for z in left),re.I):continue
        result+=int(w[4])
    return result
