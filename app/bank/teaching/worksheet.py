"""Resolve prerequisites once, preserving teacher order and original subpart identities."""
from ..format import DataError
from .taxonomy import BANK_ID


def resolve(catalog,ids,allow_pending=False):
    if len(ids)!=len(set(ids)):raise DataError('一份作业不能重复加入同一题')
    if len(ids)>200:raise DataError('每份作业最多200个独立小问')
    result=[];seen=set();visiting=set();selected=set(ids)
    def visit(qid):
        if qid in seen:return
        if qid in visiting:raise DataError('小问依赖循环')
        q=catalog.question(qid);m=q.get('metadata',{}).get('teaching')
        if m and m['status']!='ready' and not allow_pending:raise DataError('此题在待整理区，暂不参与组卷：'+qid)
        visiting.add(qid)
        for dep in m.get('prerequisites',[]) if m else []:visit(dep)
        visiting.remove(qid);seen.add(qid);result.append(qid)
    for qid in ids:visit(qid)
    if len(result)>200:raise DataError('连同必要前问超过200个小问，请减少选题')
    qs=[catalog.question(qid) for qid in result]
    groups={q.get('metadata',{}).get('teaching',{}).get('parent_question_id',q.get('question_id',q.get('id'))) for q in qs}
    return {'question_ids':result,'selected_question_ids':ids,'added_prerequisites':[qid for qid in result if qid not in selected],'question_count':len(result),'group_count':len(groups),'marks':sum(q.get('marks') or 0 for q in qs)}


def export_regions(q,kind,seen_contexts):
    if kind=='answer' or 'teaching' not in q.get('metadata',{}):return q[kind]['regions']
    m=q['metadata']['teaching'];regions=[]
    for context in m['contexts']:
        key=(q['question']['source_id'],context['key'])
        if key not in seen_contexts:regions.extend(context['regions']);seen_contexts.add(key)
    return regions+m['own_regions']
