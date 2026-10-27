"""Versioned year-specific layout policies, sharing geometry and consistency gates."""
from dataclasses import dataclass
import re
import fitz
from ..pdf_layout import layout_page
from .parsing import parse_qp,parse_ms,reference_page,body,region,has_content

@dataclass(frozen=True)
class Strategy:
    name:str
    legacy:bool

    def question_paper(self,doc,paper):
        if not self.legacy:return parse_qp(doc,paper)
        starts=[]
        for pi in range(1,len(doc)):
            page=layout_page(doc,pi)
            if reference_page(page):continue
            top,bottom=body(page)
            for word in page.get_text('words'):
                if word[4].isdigit() and 1<=int(word[4])<=40 and page.rect.width*.07<=word[0]<=page.rect.width*.105 and top<=word[1]<bottom:
                    starts.append((int(word[4]),pi,word[1]-3))
        starts=sorted(set(starts),key=lambda x:(x[1],x[2]))
        result,issues=parse_qp(doc,paper,starts)
        if paper==1:
            contexts=[]
            for pi in range(1,len(doc)):
                page=layout_page(doc,pi)
                if not re.search(r'^\s*Section B\s*$',page.get_text(),re.M):continue
                hits=page.search_for('Section B');anchors=[y for n,p,y in starts if p==pi and n>=31]
                if hits and anchors:
                    top=hits[0].y0-3;bottom=min(anchors)-5
                    if bottom>top+25:contexts.append(region(pi,[44,top,page.rect.width-43,bottom]))
            # Legacy Section B uses a shared answer-code table; a cropped stem alone is incomplete.
            if len(contexts)!=1:issues.append('legacy_section_b_context_missing_or_ambiguous')
            if contexts:
                context=contexts[0]
                for n,q in result.items():
                    rs=[]
                    for r in q['regions']:
                        if n<31 and r['page_index']==context['page_index'] and r['bbox'][3]>context['bbox'][1]:
                            r=dict(r,bbox=[*r['bbox'][:3],min(r['bbox'][3],context['bbox'][1]-3)])
                        if r['bbox'][3]>r['bbox'][1]+8 and has_content(layout_page(doc,r['page_index']),r['bbox']):rs.append(r)
                    if n>=31:rs=[context]+rs;q['section']='B';q['shared_context_regions']=1
                    q['regions']=rs;q['text']='\n'.join(layout_page(doc,r['page_index']).get_text(clip=fitz.Rect(r['bbox'])) for r in rs)
        return result,issues

    def mark_scheme(self,doc,paper):return parse_ms(doc,paper)


def strategy_for(year):return Strategy('cie-9701-legacy-2018-2021-v1',True) if year<=2021 else Strategy('cie-9701-modern-2022-plus-v2',False)
