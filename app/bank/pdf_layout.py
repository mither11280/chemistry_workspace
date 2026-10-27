"""Logical reading layout used only for analysis. Public regions stay unrotated CropBox points."""
from collections import Counter
import fitz
from .format import normalized_page


def rotation(doc,index):
    cache=getattr(doc,'_chem_layout_rotations',None)
    if cache is None:cache={};doc._chem_layout_rotations=cache
    if index not in cache:
        p=normalized_page(doc,index);weights=Counter()
        for b in p.get_text('dict')['blocks']:
            for line in b.get('lines',[]):
                dx,dy=line.get('dir',(1,0));n=sum(len(s['text'].strip()) for s in line['spans'])
                angle=90 if abs(dx)<.02 and dy<-.98 else 270 if abs(dx)<.02 and dy>.98 else 0
                weights[angle]+=n
        angle,count=weights.most_common(1)[0] if weights else (0,0)
        cache[index]=angle if angle and count>=20 and count>sum(weights.values())*.8 else 0
    return cache[index]


def transform(doc,index):
    p=normalized_page(doc,index);angle=rotation(doc,index)
    return fitz.Matrix(0,1,-1,0,p.rect.height,0) if angle==90 else fitz.Matrix(0,-1,1,0,0,p.rect.width) if angle==270 else fitz.Matrix(1,0,0,1,0,0)


class LayoutPage:
    def __init__(self,page,matrix):self.page=page;self.matrix=matrix
    def __getattr__(self,name):return getattr(self.page,name)
    @property
    def rect(self):return self.page.rect*self.matrix
    def get_text(self,option='text',**kwargs):
        if kwargs.get('clip') is not None:kwargs['clip']=fitz.Rect(kwargs['clip'])*(~self.matrix)
        value=self.page.get_text(option,**kwargs)
        if option=='words':return [(*tuple(fitz.Rect(w[:4])*self.matrix),*w[4:]) for w in value]
        if option in ['dict','rawdict']:
            for b in value['blocks']:
                b['bbox']=tuple(fitz.Rect(b['bbox'])*self.matrix)
                for line in b.get('lines',[]):
                    line['bbox']=tuple(fitz.Rect(line['bbox'])*self.matrix);dx,dy=line['dir'];m=self.matrix;line['dir']=(dx*m.a+dy*m.c,dx*m.b+dy*m.d)
                    for span in line['spans']:
                        span['bbox']=tuple(fitz.Rect(span['bbox'])*self.matrix)
                        if 'origin' in span:span['origin']=tuple(fitz.Point(span['origin'])*self.matrix)
                        for c in span.get('chars',[]):c['bbox']=tuple(fitz.Rect(c['bbox'])*self.matrix);c['origin']=tuple(fitz.Point(c['origin'])*self.matrix)
            value['width']=self.rect.width;value['height']=self.rect.height
        return value
    def search_for(self,text,**kwargs):return [r*self.matrix for r in self.page.search_for(text,**kwargs)]
    def get_drawings(self):
        drawings=self.page.get_drawings()
        for d in drawings:
            d['rect']=d['rect']*self.matrix
            d['items']=[(i[0],i[1]*self.matrix,i[2]*self.matrix) if i[0]=='l' else (i[0],i[1]*self.matrix,*i[2:]) if i[0]=='re' else i for i in d['items']]
        return drawings


def layout_page(doc,index):
    p=normalized_page(doc,index)
    return LayoutPage(p,transform(doc,index)) if rotation(doc,index) else p


def canonicalize(doc,regions):
    return [dict(r,bbox=[round(float(x),3) for x in fitz.Rect(r['bbox'])*(~transform(doc,r['page_index']))]) for r in regions]
