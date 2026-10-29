"""Reuse P4 judgments only when task, context, MS and ALL rendered regions agree.

Dependency part paths are translated within the matched parent and independently
checked for the same material. No chapter is inferred from a keyword match.
"""
import argparse,collections,copy,hashlib,json,sys
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,sha256,normalized_page
from bank.pdf_layout import rotation

PROOF_METHOD='identical-task-context-and-official-ms-rgb-108dpi-v2-canonical-clip'

def validate_reference_decision(decision):
    for evidence in decision.get('evidence',[]):
        method=evidence.get('method','')
        if method.startswith('identical-task-context-and-official-ms-rgb-') and method!=PROOF_METHOD:
            raise ValueError('Obsolete image-identity proof; restart from explicitly read judgments')

def region_raster(doc,region):
    # Saved regions are canonical, unrotated CropBox points. LayoutPage only
    # transforms text/drawings; its delegated get_pixmap still expects native
    # coordinates. Never pass a logical reading rectangle as a native clip.
    pi=region['page_index'];page=normalized_page(doc,pi)
    pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5).prerotate(rotation(doc,pi)),clip=fitz.Rect(region['bbox']),alpha=False,colorspace=fitz.csRGB)
    return [pix.width,pix.height,pix.n,hashlib.sha256(pix.samples).hexdigest()]

def text_key(record):
    return hashlib.sha256(json.dumps([record[k] for k in ['task','context','answer']],ensure_ascii=False).encode()).hexdigest()

def reuse(workdir,paths_file,decisions_file,output):
    workdir=Path(workdir);output=Path(output)
    if output.exists():raise ValueError('Use a fresh output folder')
    index=read_json(workdir/'question-index.json');qs={q['question_id']:q for q in index['questions']}
    records={r['question_id']:r for r in read_json(workdir/'candidates.private.json')}
    sources={s['source_id']:s for s in read_json(workdir/'source-manifest.json')['sources']}
    paths=read_json(paths_file);decisions=read_json(decisions_file);original=copy.deepcopy(decisions)
    groups=collections.defaultdict(list)
    for qid,r in records.items():groups[text_key(r)].append(qid)
    documents=collections.OrderedDict();materials={}
    def doc(sid):
        if sid not in documents:
            if sha256(paths[sid])!=sources[sid]['sha256']:raise ValueError('Source changed: '+sid)
            if len(documents)>=6:documents.popitem(last=False)[1].close()
            documents[sid]=fitz.open(paths[sid])
        documents.move_to_end(sid);return documents[sid]
    def material(qid):
        if qid not in materials:
            q=qs[qid];rasters=[]
            for kind in ['question','answer']:
                block=q[kind];pages=doc(block['source_id']);parts=[]
                for r in block['regions']:
                    parts.append(region_raster(pages,r))
                rasters.append(parts)
            materials[qid]=[text_key(records[qid]),q['marks'],rasters]
        return materials[qid]
    def matching(reference,target,seen=None):
        if material(reference)!=material(target):return False
        seen=set() if seen is None else seen
        if (reference,target) in seen:raise ValueError('Dependency cycle in reference judgment')
        seen=seen|{(reference,target)}
        source_parent=qs[reference]['metadata']['teaching']['parent_question_id'];target_parent=qs[target]['metadata']['teaching']['parent_question_id']
        deps=original.get(reference,{}).get('prerequisites',qs[reference]['metadata']['teaching']['prerequisites'])
        for dep in deps:
            if dep not in original or not dep.startswith(source_parent+'-'):return False
            mapped=target_parent+dep[len(source_parent):]
            if mapped not in qs or not matching(dep,mapped,seen):return False
        return True
    proofs=[]
    try:
        for qid,d in original.items():
            validate_reference_decision(d)
            if qid not in qs or d['fingerprint']!=records[qid]['fingerprint']:raise ValueError('Stale reference: '+qid)
        for ids in groups.values():
            references=[qid for qid in ids if qid in original]
            if not references:continue
            for target in ids:
                if target in decisions:continue
                for reference in references:
                    if not matching(reference,target):continue
                    d=copy.deepcopy(original[reference]);sm=qs[reference]['metadata']['teaching'];tm=qs[target]['metadata']['teaching']
                    d['fingerprint']=records[target]['fingerprint']
                    d['prerequisites']=[tm['parent_question_id']+dep[len(sm['parent_question_id']):] for dep in d.get('prerequisites',sm['prerequisites'])]
                    d['evidence'].append({'method':PROOF_METHOD,'reference_question_id':reference,'reason':'Exact task/context/MS text, marks and every canonical-clipped, reading-oriented QP/MS RGB region match the read reference; every necessary prerequisite has matching material and is mapped by original part identity.'})
                    decisions[target]=d;proofs.append({'question_id':target,'reference_question_id':reference,'material':material(target)});break
        # A copied dependent decision also needs its matching prerequisites.
        changed=True
        while changed:
            changed=False
            for qid in list(decisions):
                if qid in original:continue
                if any(d not in decisions for d in decisions[qid]['prerequisites']):del decisions[qid];changed=True
        proofs=[p for p in proofs if p['question_id'] in decisions]
        output.mkdir(parents=True);write_json(output/'decisions.json',decisions);write_json(output/'identity-proof.json',{'method':PROOF_METHOD,'matches':proofs})
        print({'read_decisions':len(original),'proven_reused':len(proofs),'total':len(decisions)})
    finally:
        for document in documents.values():document.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workdir',type=Path,required=True);p.add_argument('--sources',type=Path,required=True);p.add_argument('--decisions',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();reuse(a.workdir,a.sources,a.decisions,a.output)
