"""Rebuildable public catalog. Personal work remains in its existing separate database."""
import hashlib
import json
import sqlite3
from pathlib import Path
from .format import DataError, read_json, validate

DB_VERSION=2

class Catalog:
    def __init__(self, root, data=None, resources=None):
        self.root=Path(root);self.resource_root=Path(resources or root);self.data=Path(data or self.root/'data');self.data.mkdir(parents=True,exist_ok=True)
        self.path=self.data/'catalog.sqlite3'
        self.index_path=self.resource_root/'indexes/question-index.json'
        self.manifest_path=self.resource_root/'indexes/source-manifest.json'
        self.initialize()
        self.rebuild()

    def connect(self):
        c=sqlite3.connect(self.path,timeout=30);c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c

    def initialize(self):
        with self.connect() as c:
            version=c.execute('PRAGMA user_version').fetchone()[0]
            if version>DB_VERSION:raise DataError('本地索引数据库版本较新，不能降级打开')
            if version==0:
                c.executescript('''
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources(source_id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS questions(question_id TEXT PRIMARY KEY,year INTEGER,paper INTEGER,marks REAL,type TEXT,payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS questions_filters ON questions(year,paper,type,marks);
                CREATE TABLE IF NOT EXISTS tags(question_id TEXT REFERENCES questions ON DELETE CASCADE,topic TEXT,PRIMARY KEY(question_id,topic));
                CREATE INDEX IF NOT EXISTS tags_topic ON tags(topic,question_id);
                CREATE TABLE IF NOT EXISTS local_content(question_id TEXT PRIMARY KEY,source_hash TEXT NOT NULL,text TEXT NOT NULL,answer_value TEXT);
                CREATE TABLE IF NOT EXISTS legacy(question_id TEXT PRIMARY KEY,payload TEXT NOT NULL,status TEXT NOT NULL);
                ''')
                try:
                    c.execute('CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(question_id UNINDEXED,text,tokenize="unicode61")')
                    c.execute("INSERT OR REPLACE INTO settings VALUES ('fts','1')")
                except sqlite3.OperationalError:
                    c.execute('CREATE TABLE IF NOT EXISTS search(question_id TEXT PRIMARY KEY,text TEXT)')
                    c.execute("INSERT OR REPLACE INTO settings VALUES ('fts','0')")
                c.execute('PRAGMA user_version=1')
            if version<2:
                c.execute('ALTER TABLE local_content ADD COLUMN answer_hash TEXT')
                c.execute('PRAGMA user_version=2')

    def read_contract(self):
        index=read_json(self.index_path);manifest=read_json(self.manifest_path)
        # Calibrated or migrated data is local and never automatically published.
        local_index=self.data/'question-index.local.json';local_manifest=self.data/'source-manifest.local.json'
        if local_manifest.exists():
            merged={s['source_id']:s for s in manifest['sources']}
            merged.update({s['source_id']:s for s in read_json(local_manifest)['sources']})
            manifest['sources']=list(merged.values())
        if local_index.exists():
            local=read_json(local_index)
            merged={q['question_id']:q for q in index['questions']};merged.update({q['question_id']:q for q in local['questions']})
            index['questions']=list(merged.values())
        validate(index,manifest,self.resource_root/'schemas')
        return index,manifest

    def rebuild(self, force=False):
        index,manifest=self.read_contract()
        fingerprint=hashlib.sha256(json.dumps([index,manifest],sort_keys=True).encode()).hexdigest()
        with self.connect() as c:
            row=c.execute("SELECT value FROM settings WHERE key='fingerprint'").fetchone()
            if force or not row or row[0]!=fingerprint:
                # A source ID is a content-version identity, not a mutable filename.
                existing={r['source_id']:json.loads(r['payload'])['sha256'] for r in c.execute('SELECT * FROM sources')}
                for source in manifest['sources']:
                    if source['source_id'] in existing and existing[source['source_id']]!=source['sha256']:
                        raise DataError('source_id 已关联不同哈希；修订版必须登记新的 source_id: '+source['source_id'])
                # Single transaction: a bad update never leaves a partial catalog. Does not touch personal DB.
                c.execute('DELETE FROM tags');c.execute('DELETE FROM questions');c.execute('DELETE FROM sources')
                c.executemany('INSERT INTO sources VALUES (?,?)',[(s['source_id'],json.dumps(s)) for s in manifest['sources']])
                for q in index['questions']:
                    c.execute('INSERT INTO questions VALUES (?,?,?,?,?,?)',(q['question_id'],q['year'],q['paper'],q['marks'],q['answer']['type'],json.dumps(q)))
                    c.executemany('INSERT INTO tags VALUES (?,?)',[(q['question_id'],t) for t in q['topics']])
                c.execute("INSERT OR REPLACE INTO settings VALUES ('fingerprint',?)",(fingerprint,))
                self._refresh_search(c,index)
        self.index=index;self.manifest=manifest
        return {'questions':len(index['questions']),'sources':len(manifest['sources'])}

    def _refresh_search(self,c,index=None):
        c.execute('DELETE FROM search')
        sources={r['source_id']:json.loads(r['payload']) for r in c.execute('SELECT * FROM sources')}
        topics={t['id']:t['name']+' '+t['english'] for t in (index or self.index)['topics']}
        for row in c.execute('SELECT q.payload,l.text,l.source_hash FROM questions q LEFT JOIN local_content l USING(question_id)').fetchall():
            q=json.loads(row['payload']);source=sources[q['question']['source_id']]
            text=row['text'] if row['source_hash']==source['sha256'] else ''
            labels=' '.join(topics[t] for t in q['topics'])
            c.execute('INSERT INTO search(question_id,text) VALUES (?,?)',(q['question_id'],' '.join([q['question_id'],labels,' '.join(q['topics']),text or ''])))

    def question(self,qid):
        with self.connect() as c:
            row=c.execute('SELECT payload FROM questions WHERE question_id=?',(qid,)).fetchone()
            if row:return json.loads(row[0])
            row=c.execute('SELECT payload FROM legacy WHERE question_id=?',(qid,)).fetchone()
            if row:return json.loads(row[0])
        raise DataError('未知题目: '+qid)

    def source(self,sid):
        with self.connect() as c:row=c.execute('SELECT payload FROM sources WHERE source_id=?',(sid,)).fetchone()
        if not row:raise DataError('未知源文件: '+sid)
        return json.loads(row[0])

    CANDIDATES="""WITH candidates AS (SELECT question_id,year,paper,marks,type,payload FROM questions UNION ALL SELECT question_id,json_extract(payload,'$.year'),json_extract(payload,'$.paper'),json_extract(payload,'$.marks'),CASE WHEN json_extract(payload,'$.paper')=1 THEN 'mcq' ELSE 'regions' END,payload FROM legacy WHERE question_id NOT IN (SELECT question_id FROM questions)) """

    def search(self,filters=None,limit=8,offset=0,exclude=None,random_order=False):
        filters=filters or {};where=[];args=[]
        for key in ['year','paper','type']:
            if filters.get(key) not in [None,'',0,'0']:
                where.append('q.'+key+'=?');args.append(str(filters[key]) if key=='type' else int(filters[key]))
        for key,op in [('min_marks','>='),('max_marks','<=')]:
            if filters.get(key) not in [None,'']:
                where.append('q.marks'+op+'?');args.append(float(filters[key]))
        topics=filters.get('topics') or ([filters['topic']] if filters.get('topic') else [])
        if topics:
            where.append('(EXISTS(SELECT 1 FROM tags t WHERE t.question_id=q.question_id AND t.topic IN ('+','.join('?'*len(topics))+')) OR EXISTS(SELECT 1 FROM json_each(q.payload,\'$.topics\') WHERE value IN ('+','.join('?'*len(topics))+')))');args.extend(topics);args.extend(topics)
        if exclude:
            where.append('q.question_id NOT IN ('+','.join('?'*len(exclude))+')');args.extend(exclude)
        text=filters.get('search','').strip()
        with self.connect() as c:
            if text:
                fts=c.execute("SELECT value FROM settings WHERE key='fts'").fetchone()[0]=='1'
                if fts:
                    terms=['"'+term.replace('"','""')+'"' for term in text.split()[:20]]
                    where.append('(q.question_id IN (SELECT question_id FROM search WHERE search MATCH ?) OR q.question_id LIKE ?)');args.extend([' AND '.join(terms),'%'+text+'%'])
                else:
                    where.append('q.question_id IN (SELECT question_id FROM search WHERE text LIKE ?)');args.append('%'+text+'%')
            clause=' WHERE '+' AND '.join(where) if where else ''
            total=c.execute(self.CANDIDATES+'SELECT count(*) FROM candidates q'+clause,args).fetchone()[0]
            order='RANDOM()' if random_order else "year,paper,CAST(COALESCE(json_extract(payload,'$.original_question_number'),json_extract(payload,'$.number')) AS INTEGER),question_id"
            rows=c.execute(self.CANDIDATES+'SELECT payload FROM candidates q'+clause+' ORDER BY '+order+' LIMIT ? OFFSET ?',args+[min(max(int(limit),1),200),max(0,int(offset))]).fetchall()
        return {'total':total,'questions':[json.loads(r[0]) for r in rows]}

    def local_content(self,qid,text,source_hash,answer=None):
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO local_content(question_id,source_hash,text,answer_value,answer_hash) VALUES (?,?,?,?,NULL)',(qid,source_hash,text,answer))
            self._refresh_search(c)

    def check(self):
        self.read_contract()
        with self.connect() as c:
            return {'integrity':c.execute('PRAGMA integrity_check').fetchone()[0],
                    'foreign_keys':[tuple(r) for r in c.execute('PRAGMA foreign_key_check')],
                    'questions':c.execute('SELECT count(*) FROM questions').fetchone()[0],
                    'legacy':c.execute('SELECT count(*) FROM legacy').fetchone()[0]}
