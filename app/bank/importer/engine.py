"""Resumable batch importer. Private work directories may contain licensed source text."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import time
import fitz
from ..pdf_layout import canonicalize,rotation
from . import VERSION
from .types import ImportReport,Repair
from .identity import identify,SESSIONS
from .parsing import references
from .strategies import strategy_for
from .quality import pair_issues,question_issues
from .topics import RULES,classify
from .syllabus import metadata as syllabus_metadata
from ..format import DataError,read_json,write_json,validate


def discover(paths):
    files=set()
    for value in paths:
        path=Path(value)
        files.update(p.resolve() for p in path.rglob('*') if p.is_file() and p.suffix.lower()=='.pdf') if path.is_dir() else files.add(path.resolve())
    return sorted(files)


def analyze(paths,workdir,base_index,base_manifest,schemas,revision,overrides=None):
    """Return accepted full snapshot and a report; never modifies the installed bank."""
    start=time.perf_counter();workdir=Path(workdir);cache=workdir/'cache';cache.mkdir(parents=True,exist_ok=True)
    base_index=deepcopy(base_index);base_manifest=deepcopy(base_manifest)
    if not revision or revision==base_index['revision']:raise DataError('需要不同于基础版本的新 revision')
    patches:dict[str,Repair]=read_json(overrides) if overrides else {}
    groups={};failures=[];duplicates=0
    for path in discover(paths):
        try:
            ident,source=identify(path);pair=groups.setdefault(ident.pair_key,{})
            if ident.kind in pair:
                if pair[ident.kind][2]['sha256']==source['sha256']:duplicates+=1;continue
                pair['conflict']=True;failures.append({'file':path.name,'error':'conflicting_source_identity'});continue
            pair[ident.kind]=(path,ident,source)
        except Exception as exc:failures.append({'file':path.name,'error':str(exc)})
    accepted=[];quarantined=[];pair_reports=[];source_files={};new_sources={}
    existing={q['question_id']:q for q in base_index['questions']}
    identity_ids={(q['year'],q['session'],q['paper'],q['variant'],q['original_question_number']):q['question_id'] for q in existing.values()}
    used_patches=set()
    for key,pair in sorted(groups.items()):
        if pair.get('conflict') or not all(k in pair for k in ['qp','ms']):
            pair_reports.append({'pair':key,'status':'quarantined','issues':['conflicting_source_identity' if pair.get('conflict') else 'missing_qp_or_ms']});continue
        qpath,ident,qsource=pair['qp'];mpath,_,msource=pair['ms']
        strategy=strategy_for(ident.year)
        digest=hashlib.sha256((VERSION+strategy.name+qsource['sha256']+msource['sha256']).encode()).hexdigest();cached=cache/(digest+'.json');hit=cached.exists()
        with fitz.open(qpath) as qdoc,fitz.open(mpath) as mdoc:
            if hit:
                parsed=read_json(cached);qp={int(k):v for k,v in parsed['qp'].items()};ms={int(k):v for k,v in parsed['ms'].items()};errors=parsed['issues']
            else:
                qp,qe=strategy.question_paper(qdoc,ident.paper);ms,me=strategy.mark_scheme(mdoc,ident.paper);errors=qe+me
                for item in qp.values():item['regions']=canonicalize(qdoc,item['regions'])
                for item in ms.values():item['regions']=canonicalize(mdoc,item['regions'])
                write_json(cached,{'qp':qp,'ms':ms,'issues':errors})
            for source,doc in [(qsource,qdoc),(msource,mdoc)]:
                source['metadata']['reading_rotations_clockwise']={str(pi):rotation(doc,pi) for pi in range(len(doc)) if rotation(doc,pi)}
            qsource['metadata']['references']=references(qdoc,ident.paper,'qp',ms)
            msource['metadata']['references']=references(mdoc,ident.paper,'ms',ms)
            errors,missing_q,missing_ms=pair_issues(qp,ms,ident.paper,qsource['metadata']['cover_total_marks'] or msource['metadata']['cover_total_marks'],errors)
            if qsource['metadata']['cover_total_marks'] is not None and qsource['metadata']['cover_total_marks']!=msource['metadata']['cover_total_marks']:errors.append('cover_marks_disagree')
            passed=0;pair_failed=[]
            for n in sorted(set(qp)|set(ms)):
                qid=identity_ids.get((ident.year,SESSIONS[ident.session_code],ident.paper,ident.variant,str(n)),ident.question_id(n))
                question=qp.get(n,{'regions':[],'marks':None,'text':''});answer=ms.get(n,{'regions':[],'marks':None})
                topics,classification=classify(question['text'])
                q={'question_id':qid,'exam_board':'CIE','qualification':'AS' if ident.paper in [1,2] else 'A2','subject_code':'9701','year':ident.year,'session':SESSIONS[ident.session_code],'paper':ident.paper,'variant':ident.variant,'original_question_number':str(n),'marks':question['marks'],'topics':topics,'question':{'source_id':qsource['source_id'],'regions':question['regions']},'answer':{'type':'mcq' if ident.paper==1 else 'regions','source_id':msource['source_id'],'regions':answer['regions']},'metadata':{'importer_version':VERSION,'layout_strategy':strategy.name,'section':question.get('section','A' if ident.paper==1 and ident.year<=2021 else None),'shared_context_regions':question.get('shared_context_regions',0),'classification':classification,'review_status':'not_human_reviewed','syllabus_version':None}}
                if ident.paper==1 and answer.get('value'):q['answer']['value']=answer['value']
                if qid in patches:
                    patch=patches[qid];used_patches.add(qid)
                    if patch.get('source_fingerprint')!=digest:raise DataError('修正与当前源文件/解析器不匹配: '+qid)
                    if set(patch)-{'source_fingerprint','question','answer','marks','topics','reason'}:raise DataError('不支持的修正字段')
                    for field in ['question','answer','marks','topics']:
                        if field in patch:q[field]=deepcopy(patch[field])
                    if q['question']['source_id']!=qsource['source_id'] or q['answer']['source_id']!=msource['source_id']:raise DataError('修正不能更换来源身份')
                    q['metadata']['repair_reason']=str(patch.get('reason',''))[:500]
                q['metadata'].update(syllabus_metadata(q['year'],q['topics'],q['session']))
                qi=errors+question_issues(q,question,answer,qdoc,mdoc)
                try:
                    validate(dict(base_index,questions=[q],topics=topic_list(base_index)),dict(base_manifest,sources=[qsource,msource]),schemas)
                except Exception as exc:qi.append('contract:'+str(exc))
                q['metadata']['automatic_qa']={'status':'quarantined' if qi else 'passed','checks_version':VERSION,'issues':sorted(set(qi))}
                if qi:
                    quarantined.append({'question_id':qid,'source_fingerprint':digest,'issues':sorted(set(qi)),'candidate':q});pair_failed.append(qid)
                else:accepted.append(q);passed+=1
            if passed:
                for path,_,source in [pair['qp'],pair['ms']]:
                    # Include the reference geometry built above, not the pre-parse metadata.
                    source=qsource if source['source_id']==qsource['source_id'] else msource
                    new_sources[source['source_id']]=source;source_files[source['source_id']]=str(path)
            pair_reports.append({'pair':key,'layout_strategy':strategy.name,'source_fingerprint':digest,'cache_hit':hit,'detected_questions':len(qp),'detected_answers':len(ms),'accepted':passed,'quarantined':len(pair_failed),'missing_questions':missing_q,'missing_answers':missing_ms,'qp_marks':sum(v.get('marks') or 0 for v in qp.values()),'ms_marks':sum(v.get('marks') or 0 for v in ms.values()),'issues':errors})
    if set(patches)-used_patches:raise DataError('修正包含本批次以外的题目')
    merged=dict(existing);merged.update({q['question_id']:q for q in accepted})
    sources={s['source_id']:s for s in base_manifest['sources']}
    for sid,s in new_sources.items():
        if sid in sources and sources[sid]['sha256']!=s['sha256']:raise DataError('同一 source_id 不允许更换哈希: '+sid)
        # Preserve old source paths/IDs, including source IDs used by previous shares.
        if sid not in sources:sources[sid]=s
    index=dict(base_index,revision=revision,topics=topic_list(base_index),questions=list(merged.values()))
    manifest=dict(base_manifest,sources=list(sources.values()))
    validate(index,manifest,schemas)
    report:ImportReport={'parser_version':VERSION,'base_revision':base_index['revision'],'revision':revision,'files_failed':failures,'duplicate_files':duplicates,'pairs':pair_reports,'accepted':len(accepted),'new_questions':sum(q['question_id'] not in existing for q in accepted),'updated_existing_questions':sum(q['question_id'] in existing for q in accepted),'quarantined':len(quarantined),'total_questions':len(index['questions']),'elapsed_seconds':round(time.perf_counter()-start,3),'review_claim':'Programmatic consistency checks only; not human content review. Missing-number detection is not a measured semantic recall score.'}
    write_json(workdir/'question-index.json',index);write_json(workdir/'source-manifest.json',manifest)
    write_json(workdir/'report.json',report);write_json(workdir/'quarantine.json',quarantined);write_json(workdir/'source-files.private.json',source_files)
    return index,manifest,report


def topic_list(base):
    topics={t['id']:t for t in base['topics']}
    for ident,name,english,_ in RULES:topics.setdefault(ident,{'id':ident,'name':name,'english':english})
    topics.setdefault('unclassified',{'id':'unclassified','name':'待分类','english':'Unclassified'})
    return list(topics.values())
