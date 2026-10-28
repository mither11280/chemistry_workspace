"""The teacher's ordered course; this is deliberately not an official syllabus numbering."""
from typing import TypedDict,Literal,NotRequired
from ..format import DataError

BANK_ID='cie-9701-as-teaching19-v1'
TAXONOMY_ID='chemistry-workspace-teaching19-1.0.0'
NAMES=[
('原子结构','Atomic structure'),
('原子、分子与化学计量','Atoms, molecules and stoichiometry'),
('化学键','Chemical bonding'),('物质状态','States of matter'),
('化学能量','Chemical energetics'),('氧化还原','Redox'),('化学平衡','Equilibria'),
('反应动力学','Reaction kinetics'),('元素周期律','The Periodic Table: chemical periodicity'),
('第2族','Group 2'),('第17族','Group 17'),
('氮、硫及其他无机鉴定','Nitrogen and sulfur and other inorganic tests'),
('AS有机化学入门','An introduction to AS Level organic chemistry'),
('烃与聚合','Hydrocarbons + Polymerisation'),('卤代化合物','Halogen compounds'),
('羟基化合物','Hydroxy compounds'),('羧酸及衍生物（含腈）','Carboxylic acids and derivatives (with nitrile)'),
('羰基化合物及有机官能团检验','Carbonyl compounds (aldehydes and ketones) and organic functional group tests'),
('分析技术','Analytical techniques')]

class Teaching(TypedDict):
    taxonomy_id:str
    status:Literal['ready','pending']
    required_chapters:list[int]
    primary_chapter:int|None
    prerequisites:list[str]
    parent_question_id:str
    part_path:list[str]
    source_order:int
    own_regions:list[dict]
    contexts:list[dict]
    evidence:list[dict]
    issues:list[str]
    candidate_chapters:NotRequired[list[int]]

def normalize_provenance(question):
    """Do not present the old parent's keyword map as the new child's mapping."""
    meta=question['metadata']
    meta.pop('classification',None)
    meta['granularity']='independently_scored_subpart' if question['paper']==2 else 'multiple_choice_question'
    meta['classification_basis']='metadata.teaching.evidence; explicit solution-requirement judgments'
    current=meta.get('current_syllabus',{})
    if current.get('topic_mapping'):
        meta.setdefault('legacy_parent_topic_mapping',current['topic_mapping'])
        current['topic_mapping']=[]

def topic_id(n):return f'ch{n:02}'
def topics():return [{'id':topic_id(n),'name':f'{n} {zh}','english':en} for n,(zh,en) in enumerate(NAMES,1)]
def group(n):return 'Physical chemistry' if n<=8 else 'Inorganic chemistry' if n<=12 else 'Organic chemistry'

def validate_teaching(index):
    if index['bank_id']!=BANK_ID:return
    if index['topics']!=topics():raise DataError('教学题库章节及顺序必须与19章规范一致')
    qs={q['question_id']:q for q in index['questions']}
    visiting=set();done={};shared={}
    def visit(qid):
        if qid in visiting:raise DataError('小问依赖循环: '+qid)
        if qid in done:return done[qid]
        visiting.add(qid);q=qs[qid];m=q['metadata'].get('teaching',{})
        if m.get('taxonomy_id')!=TAXONOMY_ID:raise DataError('缺少教学分类版本')
        contexts=m.get('contexts',[]);own=m.get('own_regions',[])
        if q['question']['regions']!=[r for c in contexts for r in c['regions']]+own:raise DataError('题干区域必须与上下文及小问区域一致')
        for context in contexts:
            key=(q['question']['source_id'],context['key'])
            if key in shared and shared[key]!=context['regions']:raise DataError('同一共用上下文ID的区域不一致')
            shared[key]=context['regions']
        required=m.get('required_chapters')
        if not isinstance(required,list) or any(type(n)!=int or not 1<=n<=19 for n in required) or required!=sorted(set(required)):raise DataError('非法知识依赖章节')
        deps=m.get('prerequisites',[])
        if len(deps)!=len(set(deps)):raise DataError('重复依赖')
        chapters=set(required)
        for dep in deps:
            if dep not in qs:raise DataError('缺失前问: '+dep)
            if qs[dep]['metadata']['teaching']['parent_question_id']!=m['parent_question_id']:raise DataError('跨原题依赖需明确人工校准')
            if qs[dep]['metadata']['teaching']['source_order']>=m['source_order']:raise DataError('前问依赖必须位于当前小问之前')
            chapters.update(visit(dep))
        if m.get('status')=='ready':
            if not own or type(q['marks']) is not int or q['marks']<1:raise DataError('独立计分小问缺少区域或正整数分值')
            if not m.get('evidence') or not all(e.get('reason') and e.get('method') for e in m['evidence']):raise DataError('缺少解题知识的判定依据')
            if not chapters or m.get('issues'):raise DataError('可用题缺少可靠分类或仍含异常')
            if m.get('primary_chapter')!=max(chapters) or q['topics']!=[topic_id(max(chapters))]:raise DataError('主章节不是最靠后依赖章节')
            if any(qs[d]['metadata']['teaching']['status']!='ready' for d in deps):raise DataError('依赖待整理题不能进入章节题库')
        elif m.get('status')=='pending':
            if q['topics']:raise DataError('待整理题不得进入章节筛选')
        else:raise DataError('未知教学题状态')
        visiting.remove(qid);done[qid]=chapters;return chapters
    for qid in qs:visit(qid)
