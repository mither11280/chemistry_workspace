"""A whitelist-only report builder. Never sends an issue or reads personal state."""
import json
import re
from pathlib import PurePosixPath
from urllib.parse import urlencode
from .format import DataError

CATEGORIES={'crop':'题目裁切错误','answer':'答案错误','topics':'知识点错误','marks':'分数错误','other':'其他问题'}
ISSUES='https://github.com/mither11280/chemistry_workspace/issues/new'

def redact(text):
    text=re.sub(r'(?i)(?:[a-z]:[\\/]|/(?:Users|home|private|var|tmp|Volumes|Applications)/)[^\s\n<>"\u3000]+','[本机路径已隐藏]',text)
    text=re.sub(r'(?<![:/A-Za-z0-9])/(?:[^\s/<>"`]+/)+[^\s<>"`]*','[本机路径已隐藏]',text)
    return text


def build_report(catalog,qid,category,description,app_version):
    if category not in CATEGORIES:raise DataError('未知报错类型')
    if not isinstance(description,str) or not 1<=len(description.strip())<=2000:raise DataError('请填写 1–2000 字的问题说明')
    q=catalog.question(qid)
    if 'question_id' not in q:raise DataError('旧题目请先恢复公开题目索引，再生成反馈')
    sources=[]
    for kind in ['question','answer']:
        s=catalog.source(q[kind]['source_id'])
        sources.append({'role':kind,'source_id':s['source_id'],'filename':PurePosixPath(s['filename'].replace('\\','/')).name,'sha256':s['sha256']})
    report={'report_schema_version':'1.0.0','question_id':qid,'category':category,'description':redact(description.strip()),'bank_id':catalog.index['bank_id'],'bank_revision':catalog.index['revision'],'app_version':str(app_version)[:80],'exam':{k:q[k] for k in ['exam_board','subject_code','year','session','paper','variant','original_question_number']},'sources':sources}
    markdown='## '+CATEGORIES[category]+'\n\n'+report['description']+'\n\n```json\n'+json.dumps(report,ensure_ascii=False,indent=2)+'\n```\n\n本报告由用户确认后提交。自动校验不代表人工内容复核。'
    title=f'[{category}] {qid}'
    url=ISSUES+'?'+urlencode({'title':title,'body':markdown})
    if len(url)>7500:
        url=ISSUES+'?'+urlencode({'title':title,'body':f'Question: {qid}\nBank revision: {report["bank_revision"]}\n请在提交前粘贴已复制的完整离线报告。'})
    return {'report':report,'markdown':markdown,'issue_url':url,'filename':qid+'-report.md','privacy':'只收集题目身份与原卷哈希，不含个人作业、登录信息或本机路径。请检查你填写的说明。'}
