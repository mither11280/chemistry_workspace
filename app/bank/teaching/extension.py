"""Recoverable same-generation bundled-index adoption; personal work is never reset."""
import hashlib,json,shutil,sqlite3,uuid
from pathlib import Path
from ..format import read_json,write_json,safe_path,validate
from .taxonomy import BANK_ID

BASE_REVISION='2026-10-28.teaching19.1'
KNOWN_INDEX_HASH='598e8d55a93f6940008359aaef2d65740be2e622c5293f18d7a567595e798f8d'
KNOWN_MANIFEST_HASH='e3d4c0ec9e0f2b8e7ad4c1b191ad99d926cae319c3eb019aab7a8b8e864143b6'

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def recognized(index,manifest):
    if index.get('revision') not in [BASE_REVISION,BASE_REVISION+'.assets.1']:return False
    normalized=dict(index,revision=BASE_REVISION)
    return digest(normalized)==KNOWN_INDEX_HASH and digest(manifest)==KNOWN_MANIFEST_HASH

def restore(catalog,backup):
    backup=Path(backup);pointer=catalog.data/'bank-updates/current.json'
    value=read_json(backup/'state.json')
    if value['pointer'] is None:pointer.unlink(missing_ok=True)
    else:write_json(pointer,value['pointer'])
    with sqlite3.connect(backup/'catalog.sqlite3') as src,catalog.connect() as dst:src.backup(dst)

def recover(catalog):
    journal=catalog.data/'bundled-extension.pending.json'
    if journal.exists():
        backup=safe_path(catalog.data,read_json(journal)['backup'])
        restore(catalog,backup);journal.unlink()

def prepare(catalog):
    """Only retire an exact known v0.5.0 activation when the bundle adds A2."""
    recover(catalog)
    bundled=read_json(catalog.index_path);manifest=read_json(catalog.manifest_path)
    catalog.upgrade_notice=None
    if bundled.get('bank_id')!=BANK_ID or not any(q['paper']==4 for q in bundled['questions']):return None
    pointer=catalog.data/'bank-updates/current.json'
    previous=read_json(pointer) if pointer.exists() else None;folder=None
    if previous:
        folder=safe_path(catalog.data/'bank-updates',previous['generation'])
        old=read_json(folder/'question-index.json');old_manifest=read_json(folder/'source-manifest.json')
        if old['revision'] in [bundled['revision'],bundled['revision']+'.assets.1']:return None
        if not recognized(old,old_manifest):
            catalog.upgrade_notice='保留当前自定义题库。它与新版内置题库不同，请先导出备份，再选择要使用的版本。'
            return None
    else:
        # No activation pointer means the installed App supplies the public
        # contract. Back up a populated AS catalog before its first A2 rebuild.
        with catalog.connect() as db:
            if not db.execute('SELECT 1 FROM questions LIMIT 1').fetchone() or db.execute('SELECT 1 FROM questions WHERE paper=4 LIMIT 1').fetchone():return None
        old=None;old_manifest=None
    # Complete validation precedes activation. Compatibility includes every old
    # identity, source hash and source path, while allowing tighter coordinates.
    from ..updates import compatible
    validate(bundled,manifest,catalog.resource_root/'schemas')
    if old:compatible(old,old_manifest,bundled,manifest)
    backup=catalog.data/'bundled-extension-backups'/uuid.uuid4().hex;backup.mkdir(parents=True)
    write_json(backup/'state.json',{'pointer':previous,'old_revision':old['revision'] if old else 'previous-bundled-AS','new_revision':bundled['revision']})
    if folder:shutil.copytree(folder,backup/'active-index')
    else:
        with catalog.connect() as db:
            write_json(backup/'catalog-question-records.json',[json.loads(r[0]) for r in db.execute('SELECT payload FROM questions ORDER BY rowid')])
            write_json(backup/'catalog-source-records.json',[json.loads(r[0]) for r in db.execute('SELECT payload FROM sources ORDER BY rowid')])
    for name in ['question-index.local.json','source-manifest.local.json','teaching-generation.json']:
        if (catalog.data/name).exists():shutil.copyfile(catalog.data/name,backup/name)
    with catalog.connect() as src,sqlite3.connect(backup/'catalog.sqlite3') as dst:src.backup(dst)
    write_json(catalog.data/'bundled-extension.pending.json',{'backup':backup.relative_to(catalog.data).as_posix()})
    pointer.unlink(missing_ok=True)
    return backup

def finish(catalog,backup):
    if backup:
        write_json(Path(backup)/'completed.json',{'revision':catalog.index['revision']})
        (catalog.data/'bundled-extension.pending.json').unlink()

def fail(catalog,backup):
    if backup:
        restore(catalog,backup)
        (catalog.data/'bundled-extension.pending.json').unlink(missing_ok=True)
