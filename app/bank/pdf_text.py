"""Read-only recovery of one observed broken Latin ToUnicode map.

The source file, page content streams and glyph rendering are never rewritten. We
only decode fonts with cover-level witnesses (9701 and CHEMISTRY). Unrecognized
encodings remain unreadable and are quarantined by the importer.
"""
import re
import fitz


def shift29(value):
    return ''.join(chr(ord(c)+29) if 0<=ord(c)<=226 else c for c in value)


def encoded_fonts(doc):
    cached=getattr(doc,'_chem_shift29_fonts',None)
    if cached is not None:return cached
    fonts=set();witnesses=set()
    for block in doc[0].get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            for span in line['spans']:
                raw=span['text'];decoded=shift29(raw)
                if '9701/' in decoded and '9701/' not in raw:witnesses.add('code');fonts.add(span['font'])
                if 'CHEMISTRY' in decoded and 'CHEMISTRY' not in raw:witnesses.add('subject');fonts.add(span['font'])
    # Both independent identity witnesses must agree before this deterministic decoder is used.
    if witnesses!={'code','subject'}:fonts=set()
    else:
        for block in doc[0].get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    decoded=shift29(span['text'])
                    if any(t in decoded for t in ['This document','INSTRUCTIONS','total mark','May/June','October/November','Paper 1','Paper 2']):fonts.add(span['font'])
    doc._chem_shift29_fonts=fonts
    return fonts


class TextPageAdapter:
    def __init__(self,page,fonts):self.page=page;self.fonts=fonts
    def __getattr__(self,name):return getattr(self.page,name)
    def get_text(self,option='text',**kwargs):
        raw=self.page.get_text('rawdict',**kwargs)
        for block in raw['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    if span['font'] in self.fonts:
                        for c in span['chars']:c['c']=shift29(c['c'])
        if option=='rawdict':return raw
        if option=='dict':
            for block in raw['blocks']:
                for line in block.get('lines',[]):
                    for span in line['spans']:span['text']=''.join(c['c'] for c in span.pop('chars'))
            return raw
        if option=='words':
            result=[]
            for bi,block in enumerate(raw['blocks']):
                for li,line in enumerate(block.get('lines',[])):
                    word=[];wi=0
                    def flush():
                        nonlocal wi
                        if not word:return
                        box=fitz.Rect(word[0]['bbox'])
                        for c in word[1:]:box|=fitz.Rect(c['bbox'])
                        result.append((*box,''.join(c['c'] for c in word),bi,li,wi));wi+=1;word.clear()
                    for span in line['spans']:
                        for c in span['chars']:
                            if c['c'].isspace():flush()
                            else:word.append(c)
                    flush()
            return result
        if option not in ['text','']:
            raise ValueError('Encoded PDF text adapter supports text/dict/rawdict/words only')
        return '\n'.join(''.join(c['c'] for span in line['spans'] for c in span['chars']) for block in raw['blocks'] for line in block.get('lines',[]))+'\n'
    def search_for(self,needle,**kwargs):
        raw=self.get_text('rawdict',**kwargs);found=[]
        for block in raw['blocks']:
            for line in block.get('lines',[]):
                chars=[c for span in line['spans'] for c in span['chars']];text=''.join(c['c'] for c in chars)
                for match in re.finditer(re.escape(needle),text,re.I):
                    box=fitz.Rect(chars[match.start()]['bbox'])
                    for c in chars[match.start()+1:match.end()]:box|=fitz.Rect(c['bbox'])
                    found.append(box)
        return found
