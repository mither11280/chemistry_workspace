"""Copy an old project into a standalone app profile without overwriting user data."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import uuid
from bank.format import DataError, read_json, validate, write_json
from bank.migration import backup, rollback

IGNORED=shutil.ignore_patterns('cache','swift-cache','backups','imports','legacy-archives','__pycache__','*.sqlite3','*.sqlite3-wal','*.sqlite3-shm','server.log','backend.lock')

def import_project(old_root,catalog,store,personal_db):
    old=Path(old_root).expanduser().resolve();home=catalog.root.resolve()
    if not old.is_dir() or old==home or old in home.parents or home in old.parents:
        raise DataError('请选择独立的旧项目目录，不能导入当前用户目录或其父子目录')
    if not any((old/name).exists() for name in ['data','sources','question_bank']):raise DataError('未发现旧项目数据')
    ident=uuid.uuid4().hex;session=catalog.data/'imports'/ident;snapshot=session/'snapshot';snapshot.mkdir(parents=True)
    saved=backup(home)
    report={'snapshot':str(snapshot),'backup':str(saved),'jobs_added':0,'sources_added':0,'conflicts':[],'errors':[]}
    # Snapshot first: regular data is copied, committed SQLite is captured with the backup API.
    for name in ['data','sources','question_bank']:
        if (old/name).exists():shutil.copytree(old/name,snapshot/name,ignore=IGNORED)
    for db in (old/'data').glob('*.sqlite3'):
        target=snapshot/'data'/db.name;target.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(db) as src,sqlite3.connect(target) as dst:src.backup(dst)
    try:
        index,manifest=catalog.read_contract();known_q={q['question_id']:q for q in index['questions']};known_s={s['source_id']:s for s in manifest['sources']};conflicting_sources=set()
        for path in [snapshot/'data/source-manifest.local.json',old/'indexes/source-manifest.json']:
            if not path.exists():continue
            for source in read_json(path)['sources']:
                prior=known_s.get(source['source_id'])
                if prior and prior!=source:
                    report['conflicts'].append('保留当前来源: '+source['source_id'])
                    if prior['sha256']!=source['sha256']:conflicting_sources.add(source['source_id'])
                elif not prior:known_s[source['source_id']]=source
        for path in [old/'indexes/question-index.json',snapshot/'data/question-index.local.json']:
            if not path.exists():continue
            incoming=read_json(path)
            topics={t['id']:t for t in index['topics']}
            for topic in incoming['topics']:topics.setdefault(topic['id'],topic)
            index['topics']=list(topics.values())
            for question in incoming['questions']:
                if any(question[k]['source_id'] in conflicting_sources for k in ['question','answer']):
                    report['conflicts'].append('来源版本冲突，保留于快照待校准: '+question['question_id']);continue
                prior=known_q.get(question['question_id'])
                if prior and prior!=question:report['conflicts'].append('保留当前题目坐标: '+question['question_id'])
                elif not prior:known_q[question['question_id']]=question
        index['questions']=list(known_q.values());manifest['sources']=list(known_s.values())
        validate(index,manifest,catalog.resource_root/'schemas')
        write_json(catalog.data/'question-index.local.json',index);write_json(catalog.data/'source-manifest.local.json',manifest);catalog.rebuild(force=True)
        # Files remain available in the import snapshot even if not recognized by the current manifest.
        seen=set()
        for folder in [snapshot/'sources',snapshot/'data/sources',snapshot/'question_bank']:
            for path in folder.rglob('*.pdf') if folder.exists() else []:
                if folder.name=='question_bank' and path.parent.name!='sources':continue
                try:
                    result=store.import_file(path,extract=False);seen.update(result['source_ids'])
                except ValueError as error:report['errors'].append(path.name+': '+str(error))
        report['sources_added']=len(seen)
        # Keep unknown legacy questions and their copied PDFs usable, rather than retaining developer paths.
        legacy={}
        for path in (snapshot/'question_bank').rglob('metadata.json') if (snapshot/'question_bank').exists() else []:
            q=read_json(path);qid=q.get('id')
            if not qid or qid in known_q:continue
            q['legacy_paths']={kind:str(path.parent/(kind+'.pdf')) for kind in ['question','answer'] if (path.parent/(kind+'.pdf')).is_file()}
            legacy[qid]=q
        oldcat=snapshot/'data/catalog.sqlite3'
        if oldcat.exists():
            with sqlite3.connect(oldcat) as src:
                exists=src.execute("SELECT 1 FROM sqlite_master WHERE name='legacy'").fetchone()
                if exists:
                    for qid,payload in src.execute('SELECT question_id,payload FROM legacy'):
                        if qid in known_q:continue
                        q=json.loads(payload);paths={}
                        for kind,original in q.get('legacy_paths',{}).items():
                            original=Path(original).resolve()
                            if kind not in ['question','answer'] or old not in original.parents:continue
                            if original.is_file():
                                target=session/'legacy-files'/hashlib.sha256(qid.encode()).hexdigest()/(kind+'.pdf');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target);paths[kind]=str(target)
                        q['legacy_paths']=paths;legacy[qid]=q
        with catalog.connect() as conn:
            for qid,q in legacy.items():conn.execute('INSERT OR IGNORE INTO legacy VALUES (?,?,?)',(qid,json.dumps(q),'pending_calibration'))
        olddb=snapshot/'data/personal.sqlite3'
        if olddb.exists():
            origin=hashlib.sha256(str(old).encode()).hexdigest()
            with sqlite3.connect(olddb) as src,sqlite3.connect(personal_db) as dst:
                dst.execute('CREATE TABLE IF NOT EXISTS project_imports(key TEXT PRIMARY KEY,new_id TEXT NOT NULL)')
                rows=src.execute('SELECT id,title,body,updated FROM jobs').fetchall() if src.execute("SELECT 1 FROM sqlite_master WHERE name='jobs'").fetchone() else []
                if src.execute("SELECT 1 FROM sqlite_master WHERE name='draft'").fetchone():
                    row=src.execute('SELECT body FROM draft WHERE slot=1').fetchone()
                    if row and json.loads(row[0]).get('question_ids'):
                        body=json.loads(row[0]);rows.append(('old-draft',body.get('title','旧草稿')+' · 旧草稿',row[0],0))
                for oldid,title,body,updated in rows:
                    key=hashlib.sha256((origin+oldid+body).encode()).hexdigest()
                    if dst.execute('SELECT 1 FROM project_imports WHERE key=?',(key,)).fetchone():continue
                    existing=dst.execute('SELECT body FROM jobs WHERE id=?',(oldid,)).fetchone()
                    if existing and json.loads(existing[0])==json.loads(body):newid=oldid
                    else:
                        newid=str(uuid.uuid4()) if existing or oldid=='old-draft' else oldid
                        value=json.loads(body);value['title']=title+(' · 旧项目副本' if existing else '')
                        dst.execute('INSERT INTO jobs VALUES (?,?,?,?)',(newid,value['title'],json.dumps(value,ensure_ascii=False),updated));report['jobs_added']+=1
                    dst.execute('INSERT INTO project_imports VALUES (?,?)',(key,newid))
        if seen:store.extract_local_content(seen)
        write_json(session/'report.json',report);return report
    except Exception:
        rollback(home,saved);catalog.rebuild(force=True)
        raise
