"""One-time, recoverable switch to the teaching generation; old work is archived, not converted."""
import contextlib,json,os,shutil,uuid,sqlite3
from pathlib import Path
from ..format import DataError,read_json,write_json,safe_path
from .taxonomy import BANK_ID,TAXONOMY_ID,A2_TAXONOMY_ID

def existing_teaching_state(data):
    """A missing marker must not reset an otherwise identifiable v0.5 profile."""
    pointer=data/'bank-updates/current.json'
    try:
        if pointer.exists():
            active=safe_path(data/'bank-updates',read_json(pointer)['generation'])/'question-index.json'
            if active.exists() and read_json(active).get('bank_id')==BANK_ID:return True
        db=data/'catalog.sqlite3'
        if db.exists():
            from urllib.parse import quote
            with sqlite3.connect('file:'+quote(str(db.resolve()))+'?mode=ro',uri=True) as connection:
                total,teaching=connection.execute("SELECT count(*),sum(json_extract(payload,'$.metadata.teaching.taxonomy_id') IN (?,?)) FROM questions",(TAXONOMY_ID,A2_TAXONOMY_ID)).fetchone()
                return total>0 and total==teaching
    except (OSError,sqlite3.DatabaseError,ValueError,KeyError,DataError):pass
    return False

@contextlib.contextmanager
def locked(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        if os.name=='nt':
            import msvcrt
            stream.write(b'0');stream.flush();stream.seek(0)
            try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise DataError('请先退出正在运行的题间，再切换题库')
            try:yield
            finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise DataError('请先退出正在运行的题间，再切换题库')
            try:yield
            finally:fcntl.flock(stream,fcntl.LOCK_UN)


def recover(root):
    root=Path(root);journal=root/'.teaching-transition.json'
    if not journal.exists():return
    value=read_json(journal)
    if not __import__('re').fullmatch('[a-f0-9]{32}',str(value.get('archive_id',''))):raise DataError('切换恢复记录中的归档ID无效')
    archive=root/'generation-archives'/value['archive_id'];data=root/'data'
    if (archive/'data').exists():
        if data.exists():os.replace(data,archive/('incomplete-new-'+uuid.uuid4().hex))
        os.replace(archive/'data',data)
    journal.unlink()


def prepare(root,resources):
    root=Path(root);resources=Path(resources)
    root.mkdir(parents=True,exist_ok=True)
    with locked(root/'.generation.lock'):
        recover(root)
        if not (resources/'indexes/question-index.json').is_file():return None
        index=read_json(resources/'indexes/question-index.json')
        if index['bank_id']!=BANK_ID:return None
        data=root/'data';marker=data/'teaching-generation.json'
        if marker.exists() and read_json(marker).get('bank_id')==BANK_ID:return None
        if existing_teaching_state(data):
            write_json(marker,{'bank_id':BANK_ID,'archive_id':None,'recovered_from':'existing-teaching-contract'})
            return None
        # Empty, fresh profiles need no archive. Existing state is moved intact,
        # including local calibration overlays, immutable generations and backup pointers.
        old_state=data.exists() and any(data.iterdir())
        archive_id=uuid.uuid4().hex;archive=root/'generation-archives'/archive_id
        if old_state:
            with locked(data/'backend.lock'):
                archive.mkdir(parents=True)
                write_json(root/'.teaching-transition.json',{'archive_id':archive_id,'target_bank_id':BANK_ID})
                try:
                    os.replace(data,archive/'data');data.mkdir()
                    write_json(marker,{'bank_id':BANK_ID,'archive_id':archive_id})
                    write_json(archive/'archive.json',{'archive_id':archive_id,'target_bank_id':BANK_ID,'restore_requires_old_app':True,'sources_preserved_in_place':True})
                    (root/'.teaching-transition.json').unlink()
                except Exception:recover(root);raise
        else:
            data.mkdir(parents=True,exist_ok=True);write_json(marker,{'bank_id':BANK_ID,'archive_id':None})
        return archive_id if old_state else None


def restore(root,archive_id):
    root=Path(root)
    if not __import__('re').fullmatch('[a-f0-9]{32}',archive_id):raise DataError('无效归档 ID')
    archive=root/'generation-archives'/archive_id
    if not (archive/'data').is_dir():raise DataError('归档不存在或已经恢复')
    with locked(root/'.generation.lock'),locked(root/'data/backend.lock'):
        # Preserve new work as a separate archive too. Never overwrite either generation.
        replacement=root/'generation-archives'/uuid.uuid4().hex;replacement.mkdir(parents=True)
        os.replace(root/'data',replacement/'data')
        try:os.replace(archive/'data',root/'data')
        except Exception:os.replace(replacement/'data',root/'data');raise
        write_json(replacement/'archive.json',{'restored_from':archive_id,'restore_requires_old_app':False})
    return {'restored':archive_id,'new_generation_archived_as':replacement.name,'next_step':'退出当前版本并使用原版本App打开恢复后的用户目录'}
