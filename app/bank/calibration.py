"""Explicit teacher-drawn calibration, independently validated before replacing coordinates."""
import copy
from .format import DataError, validate, write_json
from .migration import backup

def calibrate(catalog, store, payload):
    qid=payload['question_id'];old=catalog.question(qid)
    if 'question_id' in old:q=copy.deepcopy(old)
    else:
        required=['year','paper','variant','number','marks','topics']
        if any(k not in old for k in required):raise DataError('旧题身份字段不完整，请先补齐元数据')
        q={'question_id':qid,'exam_board':'CIE','qualification':'AS','subject_code':'9701','year':int(old['year']),'session':'March','paper':int(old['paper']),'variant':int(str(old['variant'])[-1]),'original_question_number':str(old['number']),'marks':old['marks'],'topics':old['topics'],'metadata':{}}
    q['question']=payload['question'];q['answer']=payload['answer']
    q['metadata'].update({'review_status':'pending_review','calibration':'manual','migration_status':'manually_calibrated'})
    for kind in ['question','answer']:store.resolve(q[kind]['source_id'])
    index,manifest=catalog.read_contract();index['questions']=[x for x in index['questions'] if x['question_id']!=qid]+[q]
    validate(index,manifest,catalog.root/'schemas')
    saved=backup(catalog.root)
    write_json(catalog.data/'question-index.local.json',index)
    try:catalog.rebuild(force=True)
    except Exception:
        from .migration import rollback
        rollback(catalog.root,saved);catalog.rebuild(force=True);raise
    with catalog.connect() as c:c.execute('DELETE FROM legacy WHERE question_id=?',(qid,))
    store.extract_local_content({q['question']['source_id'],q['answer']['source_id']})
    return {'question_id':qid,'backup':str(saved),'review_status':'pending_review'}
