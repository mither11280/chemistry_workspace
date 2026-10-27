from dataclasses import asdict,dataclass
from pathlib import Path
import re
import fitz
from ..format import DataError,geometry,sha256

SESSIONS={'m':'March','s':'May/June','w':'October/November'}
@dataclass(frozen=True)
class Identity:
    year:int
    session_code:str
    paper:int
    variant:int
    kind:str
    @property
    def pair_key(self):return f'9701-{self.year}-{self.session_code}-{self.paper}{self.variant}'
    @property
    def source_id(self):return f'cie-{self.pair_key}-{self.kind}'
    @property
    def filename(self):return f'9701_{self.session_code}{self.year%100:02}_{self.kind}_{self.paper}{self.variant}.pdf'
    def question_id(self,n):return f'cie-9701-{self.session_code}{self.year%100:02}-{self.paper}{self.variant}-q{n}'

def identify(path):
    path=Path(path)
    with fitz.open(path) as doc:
        if doc.needs_pass:raise DataError('encrypted_pdf')
        text=doc[0].get_text()
        code=re.search(r'\b9701\s*/\s*([1-5])([1-6])\b',text)
        season=re.search(r'(February\s*/\s*March|May\s*/\s*June|October\s*/\s*November)\s+(20\d{2})',text,re.I)
        if not code or not season:raise DataError('cover_identity_unreadable')
        session='m' if season[1].lower().startswith('feb') else 's' if season[1].lower().startswith('may') else 'w'
        kind='ms' if re.search(r'MARK\s+SCHEME',text,re.I) else 'qp' if re.search(r'INSTRUCTIONS',text,re.I) else None
        if not kind:raise DataError('unsupported_document_kind')
        identity=Identity(int(season[2]),session,int(code[1]),int(code[2]),kind)
        name=re.fullmatch(r'9701_([msw])(\d{2})_(qp|ms)_([1-5])([1-6])\.pdf',path.name,re.I)
        if name and (name[1].lower(),int(name[2]),name[3].lower(),int(name[4]),int(name[5]))!=(session,identity.year%100,kind,identity.paper,identity.variant):raise DataError('filename_cover_identity_conflict')
        if identity.paper not in [1,2]:raise DataError('unsupported_paper_layout')
        marks=re.search(r'(?:total\s+mark\s+for\s+this\s+paper\s+is|Maximum\s+Mark\s*:)\s*(\d+)',text,re.I)
        if not marks:raise DataError('cover_total_marks_missing')
        pages=geometry(doc)
        printed=re.search(r'(?:document\s+(?:has|consists\s+of))\s*(\d+)\s*(?:printed\s+)?pages',text,re.I)
        if printed and int(printed[1])!=len(doc):raise DataError('physical_page_count_mismatch')
        source={'source_id':identity.source_id,'filename':identity.filename,'path':f'sources/cie/9701/{identity.year}/{session}/{identity.filename}','sha256':sha256(path),'page_count':len(doc),'pages':pages,'metadata':dict(asdict(identity),exam_board='CIE',subject_code='9701',session=SESSIONS[session],role=kind,cover_total_marks=int(marks[1]),identity_method='cover-text-crosschecked-filename-v1')}
        source['metadata'].pop('kind');source['metadata'].pop('session_code')
        return identity,source
