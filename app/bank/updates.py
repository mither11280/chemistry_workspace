"""Offline, checksummed bank snapshots. Immutable generations + one atomic activation pointer.
Personal SQLite is never opened. Checksums detect damage, not publisher authenticity.
"""
from copy import deepcopy
from collections import OrderedDict
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
import fitz
from .format import DataError,read_json,write_json,validate,validate_schema,relative_path,safe_path,sha256,geometry

MAX_BYTES=512*1024*1024
READER_VERSION=(0,5,0)

def encoded(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def digest(data):return hashlib.sha256(data).hexdigest()
def pointer_path(catalog):return catalog.data/'bank-updates/current.json'

def active_contract(catalog,index,manifest):
    pointer=pointer_path(catalog)
    if not pointer.exists():return index,manifest
    value=read_json(pointer);folder=safe_path(catalog.data/'bank-updates',value['generation'])
    return read_json(folder/'question-index.json'),read_json(folder/'source-manifest.json')


def compatible(old,old_manifest,index,manifest):
    if index['bank_id']!=old['bank_id']:raise DataError('更新包属于其他题库')
    previous={q['question_id']:q for q in old['questions']};new={q['question_id']:q for q in index['questions']}
    if not previous.keys()<=new.keys():raise DataError('更新不得删除或重命名现有题目 ID')
    identity=['exam_board','qualification','subject_code','year','session','paper','variant','original_question_number']
    for qid,q in previous.items():
        if any(q[k]!=new[qid][k] for k in identity):raise DataError('稳定题目 ID 的考试身份不可修改: '+qid)
    sources={s['source_id']:s for s in manifest['sources']}
    for s in old_manifest['sources']:
        if s['source_id'] not in sources or sources[s['source_id']]['sha256']!=s['sha256'] or sources[s['source_id']]['path']!=s['path']:
            raise DataError('既有 source_id、哈希和路径必须保留')


def build_package(output,index,manifest,base_index,base_manifest,schemas,changelog,source_files=None,authorization=None,minimum_app_version="0.3.0"):
    validate(index,manifest,schemas);compatible(base_index,base_manifest,index,manifest)
    if index['revision']==base_index['revision']:raise DataError('更新 revision 不得与基础版本相同')
    if not isinstance(changelog,str) or not changelog.strip():raise DataError('需要修复/更新说明')
    files={'question-index.json':encoded(index),'source-manifest.json':encoded(manifest)}
    # Source-inclusive publication requires an explicit, exact hash allowlist, not an inferred universal license.
    rights=authorization or {};allowed=set(rights.get('sha256',[]))
    if source_files and (not rights.get('redistribution_authorized') or not rights.get('statement')):raise DataError('附带原卷需要记录再分发授权声明及 SHA-256 清单')
    for s in manifest['sources']:
        path=(source_files or {}).get(s['source_id'])
        if path:
            if rights.get('exam_years') and s['metadata'].get('role') in ['qp','ms'] and s['metadata'].get('year') not in rights['exam_years']:raise DataError('原卷年份不在授权范围: '+s['source_id'])
            if s['sha256'] not in allowed:raise DataError('原卷不在授权哈希清单: '+s['source_id'])
            if sha256(path)!=s['sha256']:raise DataError('打包源文件哈希不一致')
            files[s['path']]=Path(path).read_bytes()
    info={'schema_version':'1.0.0','bank_id':index['bank_id'],'base_revision':base_index['revision'],'revision':index['revision'],'minimum_app_version':minimum_app_version,'changelog':changelog[:10000],'files':{n:digest(b) for n,b in files.items()},'authorization':{'statement':rights.get('statement','Index only; obtain source PDFs separately.'),'included_source_hashes':[digest(b) for n,b in files.items() if n.startswith('sources/')]}}
    files['update.json']=encoded(info)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=output.parent,suffix='.qbank.tmp');os.close(fd)
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
            for name,value in files.items():z.writestr(name,value)
        inspect_package(temp,schemas)
        os.replace(temp,output)
    finally:Path(temp).unlink(missing_ok=True)
    return {'path':str(output),'sha256':sha256(output),'bytes':output.stat().st_size,'revision':index['revision']}


def inspect_package(path,schemas):
    if Path(path).stat().st_size>MAX_BYTES:raise DataError('题库更新包过大')
    try:
        with zipfile.ZipFile(path) as z:
            names=z.namelist()
            if len(names)!=len(set(names)) or len(names)>5000:raise DataError('重复或过多的归档成员')
            if sum(i.file_size for i in z.infolist())>MAX_BYTES:raise DataError('更新包解压大小超限')
            for i in z.infolist():
                relative_path(i.filename)
                if i.is_dir() or (i.external_attr>>16)&0o170000==0o120000:raise DataError('不接受目录或符号链接')
                if i.filename not in ['question-index.json','source-manifest.json','update.json'] and not (i.filename.startswith('sources/') and i.filename.endswith('.pdf')):raise DataError('归档包含非题库文件')
            info=json.loads(z.read('update.json'));index=json.loads(z.read('question-index.json'));manifest=json.loads(z.read('source-manifest.json'))
            validate_schema(info,Path(schemas)/'bank-update.schema.json')
            if info.get('schema_version')!='1.0.0' or tuple(map(int,info['minimum_app_version'].split('.')))>READER_VERSION:raise DataError('更新包需要更新版本的 App')
            if set(info['files'])!=set(names)-{'update.json'}:raise DataError('更新清单与归档内容不一致')
            payload={n:z.read(n) for n in info['files']}
            if any(digest(b)!=info['files'][n] for n,b in payload.items()):raise DataError('更新包校验和不匹配')
            validate(index,manifest,schemas)
            if info['revision']!=index['revision'] or info['bank_id']!=index['bank_id']:raise DataError('更新包身份不一致')
            declared={s['path']:s for s in manifest['sources']}
            for name in declared:
                if not name.startswith('sources/') or not name.endswith('.pdf') or relative_path(name).as_posix()!=name:raise DataError('原卷必须位于规范化 sources/ PDF 路径')
            for name,data in payload.items():
                if name.startswith('sources/'):
                    if name not in declared or digest(data)!=declared[name]['sha256']:raise DataError('归档原卷与 manifest 不一致')
                    with fitz.open(stream=data,filetype='pdf') as d:
                        if geometry(d)!=declared[name]['pages']:raise DataError('归档原卷页面几何不一致')
            if set(info['authorization']['included_source_hashes'])!={digest(b) for name,b in payload.items() if name.startswith('sources/')}:raise DataError('授权原卷清单与归档内容不一致')
            if not isinstance(info.get('changelog'),str) or not info['changelog'].strip():raise DataError('缺少更新说明')
            return info,index,manifest,payload
    except (zipfile.BadZipFile,KeyError,TypeError,json.JSONDecodeError) as exc:raise DataError('损坏的更新包') from exc


def install_package(catalog,path,expected_sha256=None):
    """Caller serializes mutations. Verify full package again after the teacher's confirmation."""
    package_hash=sha256(path)
    if expected_sha256 and package_hash!=expected_sha256:raise DataError('确认后更新包已改变')
    info,index,manifest,payload=inspect_package(path,catalog.resource_root/'schemas')
    old,old_manifest=catalog.public_contract()
    old_effective,old_effective_manifest=catalog.read_contract()
    if info['base_revision']!=old['revision']:raise DataError('基础题库版本不匹配，请使用对应的更新包')
    compatible(old,old_manifest,index,manifest)
    if index['revision']==old['revision']:raise DataError('相同 revision 不允许重新定义内容')
    previous={q['question_id']:q for q in old['questions']}
    # Sources may be absent in index-only updates; then metadata stays browsable with a missing state.
    source_map={s['source_id']:s for s in manifest['sources']}
    documents=OrderedDict()
    def material_document(source):
        sid=source['source_id']
        if sid in documents:
            documents.move_to_end(sid);return documents[sid]
        data=payload.get(source['path']);local=safe_path(catalog.root,source['path'])
        if data:doc=fitz.open(stream=data,filetype='pdf')  # hash/geometry already checked during package inspection
        elif local.is_file():
            if sha256(local)!=source['sha256']:raise DataError('本机原卷哈希不匹配')
            doc=fitz.open(local)
            try:
                if geometry(doc)!=source['pages']:raise DataError('本机原卷几何不匹配')
            except Exception:doc.close();raise
        else:return None
        documents[sid]=doc
        if len(documents)>8:documents.popitem(last=False)[1].close()
        return doc
    try:
        for q in index['questions']:
            if q==previous.get(q['question_id']):continue
            if index['bank_id']=='cie-9701-as-teaching19-v1' and q['metadata'].get('teaching',{}).get('status')=='pending':continue
            if q['metadata'].get('automatic_qa',{}).get('status')=='quarantined':raise DataError('更新包包含隔离题目')
            from .importer.quality import region_issues,answer_content_issues
            for kind in ['question','answer']:
                source=source_map[q[kind]['source_id']];doc=material_document(source)
                # Index-only packages may be installed before originals; UI explicitly shows missing sources.
                if doc is None:continue
                issues=region_issues(doc,q[kind]['regions'])
                if kind=='answer' and q['exam_board']=='CIE':issues+=answer_content_issues(q,doc)
                if issues:raise DataError('修正未通过区域检测: '+q['question_id']+' '+','.join(issues))
    finally:
        for doc in documents.values():doc.close()
    folder=catalog.data/'bank-updates';folder.mkdir(parents=True,exist_ok=True)
    backup=folder/'backups'/str(uuid.uuid4());backup.mkdir(parents=True)
    pointer=pointer_path(catalog);previous_pointer=read_json(pointer) if pointer.exists() else None
    write_json(backup/'pointer.json',{'previous':previous_pointer,'revision':old['revision']})
    with catalog.connect() as src,sqlite3.connect(backup/'catalog.sqlite3') as dst:src.backup(dst)
    generation='generations/'+uuid.uuid4().hex;target=folder/generation;target.mkdir(parents=True)
    write_json(target/'question-index.json',index);write_json(target/'source-manifest.json',manifest);write_json(target/'update.json',info)
    # New verified raw files are immutable and can safely remain after a failed activation.
    for name,data in payload.items():
        if not name.startswith('sources/'):continue
        out=safe_path(catalog.root,name);out.parent.mkdir(parents=True,exist_ok=True)
        if out.exists():
            if sha256(out)!=digest(data):raise DataError('禁止覆盖不同内容的原卷')
            continue
        fd,temp=tempfile.mkstemp(dir=out.parent)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(data)
            os.replace(temp,out)
        finally:Path(temp).unlink(missing_ok=True)
    try:
        write_json(pointer,{'generation':generation,'revision':index['revision'],'package_sha256':package_hash})
        catalog.rebuild(force=True)
    except Exception:
        if previous_pointer is None:pointer.unlink(missing_ok=True)
        else:write_json(pointer,previous_pointer)
        with sqlite3.connect(backup/'catalog.sqlite3') as src,catalog.connect() as dst:src.backup(dst)
        catalog.index=old_effective;catalog.manifest=old_effective_manifest
        raise
    return {'revision':index['revision'],'questions':len(index['questions']),'backup_id':backup.name,'package_sha256':package_hash}


def rollback(catalog,backup_id):
    if not re.fullmatch(r'[a-f0-9-]{36}',backup_id):raise DataError('无效备份 ID')
    backup=catalog.data/'bank-updates/backups'/backup_id;value=read_json(backup/'pointer.json')
    pointer=pointer_path(catalog)
    if value['previous'] is None:pointer.unlink(missing_ok=True)
    else:write_json(pointer,value['previous'])
    # Rebuildable catalog avoids restoring personal data or discarding new local calibrations.
    catalog.rebuild(force=True)
    return {'revision':catalog.index['revision']}
