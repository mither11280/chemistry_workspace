"""Conservative, repeatable legacy migration. Never infer coordinates from a cut PDF."""
import copy
import datetime
import json
import re
import shutil
import sqlite3
from pathlib import Path
import fitz
from .format import COORDINATES, VERSION, DataError, geometry, read_json, safe_path, sha256, validate, write_json


def backup(root, legacy=None):
    root=Path(root);folder=root/'data/backups'/('migration-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir(parents=True)
    # SQLite backup API includes committed WAL content; do not copy a live DB file alone.
    for db in (root/'data').glob('*.sqlite3'):
        with sqlite3.connect(db) as src, sqlite3.connect(folder/db.name) as dst:src.backup(dst)
    for name in ['question-index.local.json','source-manifest.local.json']:
        p=root/'data'/name
        if p.exists():shutil.copy2(p,folder/name)
    if legacy and Path(legacy).exists():shutil.copytree(legacy,folder/'legacy',ignore=shutil.ignore_patterns('backups','cache','swift-cache','legacy-archives'))
    write_json(folder/'backup.json',{'created':datetime.datetime.now().isoformat(),'kind':'coordinate-migration','legacy_path':str(Path(legacy).resolve()) if legacy else None})
    return folder


def rollback(root, folder):
    root=Path(root);folder=Path(folder)
    if read_json(folder/'backup.json').get('kind')!='coordinate-migration':raise DataError('不是有效迁移备份')
    for name in ['question-index.local.json','source-manifest.local.json']:
        target=root/'data'/name
        if (folder/name).exists():shutil.copy2(folder/name,target)
        elif target.exists():target.unlink()
    for db in folder.glob('*.sqlite3'):
        target=root/'data'/db.name
        with sqlite3.connect(db) as src,sqlite3.connect(target) as dst:src.backup(dst)
    # Originals and old PDFs were never removed; restore overlay/database state only.
    return {'restored':str(folder),'restart_required':True}


def source_identity(name, metadata=None):
    match=re.fullmatch(r'9701_m(\d{2})_(qp|ms)_(\d)(\d)\.pdf',name)
    if match:
        year,role,paper,variant=match.groups()
        return f'cie-9701-20{year}-m-{paper}{variant}-{role}',f'sources/cie/9701/20{year}/march/{name}',{'exam_board':'CIE','subject_code':'9701','year':2000+int(year),'session':'March','paper':int(paper),'variant':int(variant),'role':role}
    if name=='9701-syllabus-2025-2027.pdf':
        return 'cie-9701-syllabus-2025-2027','sources/cie/9701/syllabus/'+name,{'role':'syllabus','syllabus_version':'2025-2027'}
    raise DataError('未识别的旧版来源身份，需要手动登记: '+name)


def source_references(doc, info, questions):
    role=info.get('role');references=[]
    if role=='qp':
        last=doc[-1]
        if last.rotation:last.set_rotation(0)
        references.append({'page_index':len(doc)-1,'bbox':list(doc[-1].rect),'rotate':270})
        for i,page in enumerate(doc):
            hits=page.search_for('Important values')
            if i>0 and hits:
                bottom=min(780,hits[0].y0+235)
                lines=[drawing['rect'].y1 for drawing in page.get_drawings() if drawing['rect'].y0>=hits[0].y0 and drawing['rect'].y1<hits[0].y0+260]
                if lines:bottom=max(lines)+8
                references.insert(0,{'page_index':i,'bbox':[44,hits[0].y0,552,bottom],'rotate':0})
    elif role=='ms' and info.get('paper')==2:
        regions=[r['page'] for q in questions for r in q.get('answer_regions',[])]
        if regions:references=[{'page_index':i,'bbox':list(doc[i].rect),'rotate':0} for i in range(1,min(regions)-1)]
    return references


def convert_legacy(old, legacy_root, schemas=None):
    """Return only proven coordinates. Failures are returned for PDF-only fallback."""
    legacy_root=Path(legacy_root);manifest={'schema_version':VERSION,'coordinate_system':COORDINATES,'sources':[]};source_map={};failures=[]
    for name,info in old.get('sources',{}).items():
        path=legacy_root/'sources'/name
        if not path.exists() or sha256(path)!=info['sha256']:continue
        sid,relative,metadata=source_identity(name)
        with fitz.open(path) as doc:
            pages=geometry(doc)
            metadata['references']=source_references(doc,metadata,[q for q in old['questions'] if q.get('ms')==name])
            source={'source_id':sid,'filename':name,'path':relative,'sha256':info['sha256'],'page_count':len(doc),'pages':pages,'metadata':metadata}
        manifest['sources'].append(source);source_map[name]=source
    index={'schema_version':VERSION,'coordinate_system':COORDINATES,'bank_id':old.get('bank_id','cie-9701-as-starter'),'revision':'2026-10-27.coordinates.1','topics':old.get('topics',[]),'questions':[]}
    for q in old['questions']:
        try:
            if q['qp'] not in source_map or q['ms'] not in source_map:raise DataError('原卷缺失或 SHA-256 不符')
            if not q.get('question_regions') or not q.get('answer_regions'):raise DataError('没有可信原卷坐标，不能从裁片反推')
            qp=source_map[q['qp']];ms=source_map[q['ms']]
            # The legacy importer only used unrotated, full-CropBox pages. Other geometries require calibration.
            for block,name in [('question',q['qp']),('answer',q['ms'])]:
                for region in q[block+'_regions']:
                    p=source_map[name]['pages'][region['page']-1]
                    if p['rotation'] or p['media_box']!=p['crop_box']:raise DataError('旧坐标页面有旋转/CropBox 偏移，需手动校准')
            variant=str(q['variant'])
            question={'question_id':q['id'],'exam_board':'CIE','qualification':'AS','subject_code':'9701','year':q['year'],'session':'March','paper':q['paper'],'variant':int(variant[-1]),'original_question_number':str(q['number']),'marks':q.get('marks'),'topics':q.get('topics',[]),
                'question':{'source_id':qp['source_id'],'regions':[{'page_index':r['page']-1,'bbox':r['bbox']} for r in q['question_regions']]},
                'answer':{'type':'mcq' if q['paper']==1 else 'regions','source_id':ms['source_id'],'regions':[{'page_index':r['page']-1,'bbox':r['bbox']} for r in q['answer_regions']]},
                'metadata':{'review_status':'pending_review','classification_basis':'Legacy keyword candidates; syllabus statements not verified','syllabus_version':'2025-2027','syllabus_mapping_status':'unverified','granularity':q.get('granularity','whole_question'),'migration_status':'coordinates_verified_against_source_hash'}}
            single=copy.deepcopy(index);single['questions']=[question]
            validate(single,manifest,schemas or Path(__file__).resolve().parents[2]/'schemas')
            index['questions'].append(question)
        except (DataError,KeyError,IndexError,ValueError) as e:
            failures.append({'question_id':q.get('id','unknown'),'reason':str(e),'status':'pending_calibration','legacy':q})
    return index,manifest,failures


def migrate(root, legacy_root, catalog, store):
    root=Path(root);legacy_root=Path(legacy_root).resolve()
    # Always backup before opening metadata or making any writes.
    saved=backup(root,legacy_root)
    try:
        index_file=legacy_root/'index.json'
        if not index_file.exists() and (legacy_root/'bank.json').exists():index_file=legacy_root/'bank.json'
        if index_file.exists():old=read_json(index_file)
        else:
            old={'bank_id':'legacy-local','topics':catalog.index['topics'],'sources':{},'questions':[read_json(p) for p in legacy_root.rglob('metadata.json')]}
            # Standalone folders have no trustworthy source hashes: keep PDF compatibility.
        index,manifest,failures=convert_legacy(old,legacy_root,catalog.resource_root/'schemas')
        migrated_ids=[q['question_id'] for q in index['questions']]
        merged={q['question_id']:q for q in catalog.index['questions']};merged.update({q['question_id']:q for q in index['questions']});index['questions']=list(merged.values())
        topic_map={t['id']:t for t in catalog.index['topics']};topic_map.update({t['id']:t for t in index['topics']});index['topics']=list(topic_map.values())
        sources={s['source_id']:s for s in catalog.manifest['sources']};sources.update({s['source_id']:s for s in manifest['sources']});manifest['sources']=list(sources.values())
        validate(index,manifest,catalog.resource_root/'schemas')
        write_json(root/'data/question-index.local.json',index);write_json(root/'data/source-manifest.local.json',manifest)
        catalog.rebuild(force=True)
        with catalog.connect() as c:
            for failed in failures:
                q=failed['legacy'];qid=failed['question_id']
                q['legacy_root']=str(legacy_root)
                # Paths stay local; verify existence before use; missing sides are reported at preview time.
                q['legacy_paths']={}
                metadata_files=list(legacy_root.rglob('metadata.json')) if not index_file.exists() else []
                matched=next((p.parent for p in metadata_files if read_json(p).get('id')==qid),None)
                for kind in ['question','answer']:
                    path=None
                    relative=q.get('files',{}).get(kind)
                    if relative:
                        try:path=safe_path(legacy_root,relative)
                        except DataError:pass
                    if (not path or not path.is_file()) and matched:
                        path=matched/(kind+'.pdf')
                    if path and path.is_file():q['legacy_paths'][kind]=str(path)
                c.execute('INSERT OR REPLACE INTO legacy VALUES (?,?,?)',(qid,json.dumps(q),'pending_calibration'))
            c.executemany('DELETE FROM legacy WHERE question_id=?',[(qid,) for qid in migrated_ids])
        imported=[]
        for s in manifest['sources']:
            candidate=legacy_root/'sources'/s['filename']
            if candidate.exists() and sha256(candidate)==s['sha256']:imported.append(store.import_file(candidate,extract=False))
        store.extract_local_content()
        report={'backup':str(saved),'migrated':len(migrated_ids),'pending_calibration':[{'question_id':f['question_id'],'reason':f['reason']} for f in failures],'imported_sources':len(imported)}
        write_json(root/'data/migration-report.json',report);return report
    except Exception:
        rollback(root,saved)
        catalog.rebuild(force=True)
        raise


def archive_legacy(root,legacy_root,catalog):
    """Explicit opt-in only. Verify every legacy metadata entry migrated before moving."""
    legacy_root=Path(legacy_root).resolve();root=Path(root).resolve()
    if legacy_root==root or root not in legacy_root.parents:raise DataError('只归档本项目内的旧题库目录')
    old=read_json(legacy_root/'index.json')
    migrated={q['question_id'] for q in catalog.index['questions']}
    if any(q['id'] not in migrated for q in old['questions']):raise DataError('迁移未完成，不能归档')
    target=root/'data/legacy-archives'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')/legacy_root.name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.move(str(legacy_root),target)
    return {'archive':str(target)}
