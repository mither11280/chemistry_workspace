#!/usr/bin/env python3
"""Inventory and resumable phased expansion. Reads supplied PDFs only; no network access."""
import argparse,json,sys
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,validate
from bank.importer.inventory import scan
from bank.importer.engine import analyze
from bank.importer.syllabus import enrich

PHASES=[('modern',range(2022,2026)),('year2026',[2026]),('legacy',range(2018,2022))]

def coverage(inventory,index,reports,base):
    byexam={};held={}
    for q in index['questions']:byexam.setdefault((q['year'],q['session'],q['paper'],q['variant']),[]).append(q)
    for name,report in reports.items():
        for pair in report['pairs']:held[pair['pair']]=pair
    for row in inventory['rows']:
        qs=byexam.get((row['year'],row['session'],row['paper'],row['variant']),[]);pair=held.get(row['pair'],{})
        row['imported_questions']=len(qs);row['quarantined_questions']=pair.get('quarantined',0)
        row['detected_questions']=pair.get('detected_questions',len(qs) if qs else None)
        row['detected_answers']=pair.get('detected_answers',len(qs) if qs else None)
        row['qa_status']='partial-with-quarantine' if row['quarantined_questions'] and qs else 'quarantined' if row['quarantined_questions'] else 'imported' if qs else row['qa_status']
        row['parser_version']=pair.get('parser_version',report_version(qs,inventory))
        row['issues']=sorted(set(row['issues']+pair.get('issues',[])))
    old_ids={q['question_id'] for q in base['questions']};new_ids={q['question_id'] for q in index['questions']}
    inventory['final_revision']=index['revision'];inventory['summary'].update({'final_questions':len(index['questions']),'new_questions':len(new_ids-old_ids),'original_question_ids_retained':old_ids<=new_ids,'duplicate_question_ids':len(index['questions'])-len(new_ids),'quarantined_questions':sum(r['quarantined'] for r in reports.values())})
    return inventory


def report_version(qs,inventory):return qs[0]['metadata'].get('importer_version','existing-before-v04') if qs else inventory['parser_version']


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--corpus',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--revision-prefix',required=True);p.add_argument('--as-of',default=date.today().isoformat());p.add_argument('--phase',choices=['all']+[n for n,_ in PHASES],default='all')
    args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    index=read_json(args.base/'question-index.json');manifest=read_json(args.base/'source-manifest.json');original=read_json(args.base/'question-index.json')
    inv,selected=scan(args.corpus,index,manifest,out/'inventory',args.as_of);reports={};all_sources={}
    for number,(name,years) in enumerate(PHASES,1):
        if args.phase not in ['all',name]:continue
        files=[f for key,paths in selected.items() if int(key.split('-')[1]) in years for f in paths]
        print(json.dumps({'phase':name,'pairs':len(files)//2,'base_revision':index['revision']},ensure_ascii=False),flush=True)
        index=enrich(index)
        index,manifest,report=analyze(files,out/name,index,manifest,ROOT/'schemas',args.revision_prefix+'.'+str(number));reports[name]=report
        all_sources.update(read_json(out/name/'source-files.private.json'))
        print(json.dumps({'phase':name,'new':report['new_questions'],'held':report['quarantined'],'total':report['total_questions']},ensure_ascii=False),flush=True)
    final=out/'final';final.mkdir(exist_ok=True);validate(index,manifest,ROOT/'schemas')
    write_json(final/'question-index.json',index);write_json(final/'source-manifest.json',manifest);write_json(final/'source-files.private.json',all_sources)
    write_json(out/'coverage.json',coverage(inv,index,reports,original))
    write_json(out/'batch-reports.json',reports)
    # Public anomaly report contains IDs and reasons, never extracted question text or local absolute paths.
    anomalies=[]
    for name in reports:
        anomalies.extend({'phase':name,'question_id':q['question_id'],'issues':q['issues'],'source_fingerprint':q['source_fingerprint']} for q in read_json(out/name/'quarantine.json'))
    write_json(out/'anomalies.json',anomalies)
    print(json.dumps({'final_revision':index['revision'],'questions':len(index['questions']),'new_questions':len(index['questions'])-len(original['questions']),'quarantined':len(anomalies)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
