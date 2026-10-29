"""Register in-paper appendices and an optional user-provided historical Data Booklet.

Registration is separate from redistribution permission; packaging still requires
an explicit exact-hash authorization allowlist for every included PDF.
"""
import argparse,copy,re,sys
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,sha256,geometry,normalized_page,validate
from bank.importer.parsing import references
from bank.teaching.parts import ms_parts

BOOKLET_ID='cie-9701-data-booklet-2016'

def attach(snapshot,paths_file,output,booklet=None):
    output=Path(output)
    if output.exists():raise ValueError('Use a fresh output folder')
    index=read_json(Path(snapshot)/'question-index.json');manifest=read_json(Path(snapshot)/'source-manifest.json');paths=read_json(paths_file)
    if booklet:
        booklet=Path(booklet)
        with fitz.open(booklet) as doc:
            cover=normalized_page(doc,0).get_text()
            if not all(v in cover for v in ['9701','2016','Chemistry']):raise ValueError('Historical booklet cover identity mismatch')
            source={'source_id':BOOKLET_ID,'filename':'9701-data-booklet-2016.pdf','path':'sources/cie/9701/reference/9701-data-booklet-2016.pdf','sha256':sha256(booklet),'page_count':len(doc),'pages':geometry(doc),'metadata':{'role':'data-booklet','exam_board':'CIE','subject_code':'9701','edition':'for-use-from-2016','title':'CIE 9701 Data Booklet (2016)','registration_method':'local-cover-and-exact-hash','redistribution_permission_not_inferred_from_registration':True}}
        old=next((s for s in manifest['sources'] if s['source_id']==BOOKLET_ID),None)
        if old and old['sha256']!=source['sha256']:raise ValueError('Existing booklet identity has a different hash')
        if not old:manifest['sources'].append(source)
        paths[BOOKLET_ID]=str(booklet.resolve())
    required=[];appendices=0
    for source in manifest['sources']:
        meta=source['metadata']
        if meta.get('paper')!=4 or meta.get('role') not in ['qp','ms']:continue
        if sha256(paths[source['source_id']])!=source['sha256']:raise ValueError('Source changed: '+source['source_id'])
        with fitz.open(paths[source['source_id']]) as doc:
            rows=ms_parts(doc)[0] if meta['role']=='ms' else {}
            meta['references']=references(doc,4,meta['role'],rows);appendices+=len(meta['references'])
            if meta['role']=='qp' and re.search(r'Data\s+Booklet',normalized_page(doc,0).get_text(),re.I):
                meta['required_external_documents']=[{'source_id':BOOKLET_ID,'title':'CIE 9701 Data Booklet (2016)','delivery':'separate-reusable-reference'}]
                required.append(source['source_id'])
    validate(index,manifest,ROOT/'schemas');output.mkdir(parents=True)
    write_json(output/'question-index.json',index);write_json(output/'source-manifest.json',manifest);write_json(output/'source-files.private.json',paths)
    for name in ['candidates.private.json']:
        if (Path(snapshot)/name).exists():write_json(output/name,read_json(Path(snapshot)/name))
    report={'paper4_appendix_regions':appendices,'papers_requiring_separate_booklet':required,'booklet_registered':any(s['source_id']==BOOKLET_ID for s in manifest['sources']),'source_files':len(manifest['sources'])}
    write_json(output/'reference-report.json',report);print(report)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--data-booklet',type=Path);a=p.parse_args();attach(a.snapshot,a.sources,a.output,a.data_booklet)
