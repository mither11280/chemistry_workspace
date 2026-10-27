#!/usr/bin/env python3
"""Export portable snapshots and source-free coverage reports after real acceptance succeeds."""
from pathlib import Path
import argparse,csv,json,shutil,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,validate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workdir',type=Path,required=True);p.add_argument('--snapshot',type=Path,default=ROOT/'indexes/releases/v0.4-2018-2026');p.add_argument('--docs',type=Path,default=ROOT/'docs/history-v04');args=p.parse_args()
    work=args.workdir;docs=args.docs;docs.mkdir(parents=True,exist_ok=True);args.snapshot.mkdir(parents=True,exist_ok=True)
    index=read_json(work/'final/question-index.json');manifest=read_json(work/'final/source-manifest.json');validate(index,manifest,ROOT/'schemas')
    acceptance=read_json(work/'acceptance.json');coverage=read_json(work/'coverage.json');reports=read_json(work/'batch-reports.json');anomalies=read_json(work/'anomalies.json')
    assert acceptance['bank_revision']==index['revision'] and acceptance['questions']==len(index['questions']) and acceptance['personal_databases_byte_identical'] and acceptance['rollback_and_reinstall_passed']
    for name in ['question-index.json','source-manifest.json']:shutil.copyfile(work/'final'/name,args.snapshot/name)
    for item in anomalies:
        cache=read_json(work/item['phase']/'cache'/(item['source_fingerprint']+'.json'))
        q=next(q for q in read_json(work/item['phase']/'quarantine.json') if q['question_id']==item['question_id'])['candidate'];n=q['original_question_number']
        item.update({k:q[k] for k in ['year','session','paper','variant','original_question_number']});item['qp_marks']=q['marks'];item['ms_detected_marks']=cache['ms'].get(n,{}).get('marks');item['source_ids']={'qp':q['question']['source_id'],'ms':q['answer']['source_id']}
    for row in coverage['rows']:
        local=[v for v in anomalies if (v['year'],v['session'],v['paper'],v['variant'])==(row['year'],row['session'],row['paper'],row['variant'])]
        row['issues']=sorted(set(row['issues']+[i for v in local for i in v['issues']]))
        if row['already_imported']:row['qa_status']='existing-preserved-and-material-verified-on-install'
    write_json(docs/'coverage.json',coverage);write_json(docs/'anomalies.json',anomalies);write_json(docs/'batch-reports.json',reports);write_json(docs/'acceptance.json',acceptance);write_json(docs/'authorization.json',read_json(work/'authorization.json'))
    fields=['year','session','paper','variant','exam_status','qp_found','ms_found','already_imported','imported_questions','quarantined_questions','qa_status','parser_version','qp_sha256','ms_sha256','issues']
    with (docs/'coverage.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");writer.writeheader()
        for row in coverage['rows']:
            value={k:row.get(k,'') for k in fields};value['qp_sha256']=';'.join(s['sha256'] for s in row['sources']['qp']);value['ms_sha256']=';'.join(s['sha256'] for s in row['sources']['ms']);value['issues']=';'.join(row['issues']);writer.writerow(value)
    mapping={(r['year'],r['session_code'],r['paper'],r['variant']):r for r in coverage['rows']}
    table=['# CIE 9701 2018–2026 覆盖矩阵','',f"快照 `{index['revision']}`：{len(index['questions'])} 题，比既有 266 题新增 {acceptance['new_questions']} 题。统计截至 {coverage['as_of']}。",'', '单元格为已入库题数；“隔离”项不在可用题库中。“—”为本矩阵不预期的 March variant。','', '| 年份 | 考季 | P11 | P12 | P13 | P21 | P22 | P23 |','|---|---|---:|---:|---:|---:|---:|---:|']
    for year in range(2018,2027):
        for se,label in [('m','March'),('s','May/June'),('w','Oct/Nov')]:
            cells=[]
            for paper,variant in [(1,1),(1,2),(1,3),(2,1),(2,2),(2,3)]:
                r=mapping.get((year,se,paper,variant))
                if r is None:cells.append('—');continue
                if r['exam_status']=='series-in-progress-not-publication-ready':cells.append('未完成考季');continue
                if not r['qp_found']:cells.append('缺 QP');continue
                if not r['ms_found']:cells.append('缺 MS');continue
                if any('conflicting' in i for i in r['issues']):cells.append('版本冲突');continue
                text=str(r['imported_questions'])
                if r.get('quarantined_questions'):text+='（隔离 '+str(r['quarantined_questions'])+'）'
                cells.append(text)
            if year==2020 and se=='s':label+='（取消，公开练习资料）'
            table.append('| '+str(year)+' | '+label+' | '+' | '.join(cells)+' |')
    table.extend(['','[完整 CSV，含逐文件哈希与 parser 版本](coverage.csv) · [机器报告](coverage.json) · [隔离题明细](anomalies.json) · [实际安装与导出测量](acceptance.json)','', '2020 May/June 取消考试的标记依据 [Cambridge 官方公告](https://www.cambridgeinternational.org/news/news-details/view/update-from-cambridge-international-on-may-june-2020-exams-20200323/)。现有相应 QP/MS 仅作为已公开练习资料收录。2026 Oct/Nov 在本次统计日尚未完成，单独标记，不计作普通缺卷。','', '原卷哈希不同但本次识别为重复的一组资料，逐页未旋转 boxes、文字位置和 RGB 像素完全相同；差异只在附录页显示旋转/保存信息。选择一份原始文件入库，并保留两个哈希记录；没有改写或重导出原卷。','', '自动 QA 通过只代表程序一致性检查通过，不是人工内容复核，也不是统计识别准确率。旧考纲与当前考纲的逐题兼容性保持未知。若旧卷依赖另行发放的 Data Booklet，教师仍需提供对应版本；本次未下载或静默替换旧版配套资料。'])
    (docs/'coverage.md').write_text('\n'.join(table)+'\n',encoding='utf-8')
    print(json.dumps({'questions':len(index['questions']),'snapshot':str(args.snapshot),'report':str(docs)},ensure_ascii=False))
if __name__=='__main__':main()
