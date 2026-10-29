from dataclasses import asdict,dataclass
from pathlib import Path
import re
import fitz
from ..format import DataError,geometry,sha256,normalized_page

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

def identify(path,allow_page_count_mismatch=False):
    path=Path(path)
    with fitz.open(path) as doc:
        if doc.needs_pass:raise DataError('encrypted_pdf')
        pages=geometry(doc)
        text=normalized_page(doc,0).get_text()
        code=re.search(r'\b9701\s*/\s*([1-5])([1-6])\b',text)
        season=re.search(r'(February\s*/\s*March|May\s*/\s*June|October\s*/\s*November|March|June|November)\s+(20\d{2})',text,re.I)
        if not code or not season:raise DataError('cover_identity_unreadable')
        session='m' if season[1].lower().startswith(('feb','mar')) else 's' if season[1].lower().startswith(('may','jun')) else 'w'
        kind='ms' if re.search(r'MARK\s+SCHEME',text,re.I) else 'qp' if re.search(r'INSTRUCTIONS',text,re.I) else None
        if not kind:raise DataError('unsupported_document_kind')
        identity=Identity(int(season[2]),session,int(code[1]),int(code[2]),kind)
        name=re.fullmatch(r'9701_([msw])(\d{2})_(qp|ms)_([1-5])([1-6])\.pdf',path.name,re.I)
        if name and (name[1].lower(),int(name[2]),name[3].lower(),int(name[4]),int(name[5]))!=(session,identity.year%100,kind,identity.paper,identity.variant):raise DataError('filename_cover_identity_conflict')
        if identity.paper not in [1,2,4]:raise DataError('unsupported_paper_layout')
        marks=re.search(r'(?:total\s+mark\s+for\s+this\s+paper\s+is|Maximum\s+Mark\s*:)\s*(\d+)',text,re.I)
        total=int(marks[1]) if marks else 40 if identity.paper==1 and re.search(r'(?:forty|40) questions',text,re.I) and re.search(r'(?:one|1) mark',text,re.I) else None
        if total is None and not (identity.year<=2019 and kind=='qp' and identity.paper in [2,4]):raise DataError('cover_total_marks_missing')
        printed=re.search(r'(?:document\s+(?:has|consists\s+of))\s*(\d+)\s*(?:printed\s+)?pages',text,re.I)
        blanks=re.search(r'printed pages and (\d+) blank pages?',text,re.I)
        printed_pages=int(printed[1])+(int(blanks[1]) if blanks else 0) if printed else None
        count_mismatch=printed_pages is not None and printed_pages!=len(doc)
        if count_mismatch and not allow_page_count_mismatch:raise DataError('physical_page_count_mismatch')
        source={'source_id':identity.source_id,'filename':identity.filename,'path':f'sources/cie/9701/{identity.year}/{session}/{identity.filename}','sha256':sha256(path),'page_count':len(doc),'pages':pages,'metadata':dict(asdict(identity),exam_board='CIE',subject_code='9701',session=SESSIONS[session],role=kind,cover_total_marks=total,mark_total_method='cover-explicit' if total is not None else 'not-printed-crosscheck-qp-sum-against-ms',identity_method='cover-text-crosschecked-filename-v1')}
        source['metadata'].pop('kind');source['metadata'].pop('session_code')
        if count_mismatch:source['metadata'].update(cover_page_count=printed_pages,source_integrity_issues=['physical_page_count_mismatch'],assessment_completeness='requires-qp-ms-subpart-reconciliation')
        return identity,source
