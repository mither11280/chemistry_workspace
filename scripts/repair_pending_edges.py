"""Recheck existing crop-edge alarms without moving coordinates or waiving QA.

Writes a fresh, reversible public snapshot plus an evidence report. Does not
install it, change sources, update personal data or infer teaching decisions.
"""
import argparse
import collections
import copy
from contextlib import ExitStack
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import fitz
from bank.format import read_json, write_json, validate, sha256, geometry
from bank.importer.quality import region_issues, answer_content_issues
from bank.importer.crop_edges import PROOF_VERSION
from bank.importer.source_audit import audit_pagination
from bank.teaching.decisions import fingerprint
from bank.teaching.taxonomy import topic_id, course_for

EDGE = {'question:text_crosses_crop_edge', 'context:text_crosses_crop_edge',
        'answer:text_crosses_crop_edge'}


def finish_dependencies(index):
    """Recompute statuses only after material gates; retain all unresolved issues."""
    qs = {q['question_id']: q for q in index['questions']}
    done = set()
    def resolve(qid):
        if qid in done:
            return
        q = qs[qid];m = q['metadata']['teaching']
        chapters = set(m['required_chapters'])
        for dep in m['prerequisites']:
            resolve(dep);dm = qs[dep]['metadata']['teaching']
            chapters.update(dm['required_chapters'])
            if dm['primary_chapter']:
                chapters.add(dm['primary_chapter'])
        issues = set(m['issues']) - {'prerequisite_pending'}
        if any(qs[d]['metadata']['teaching']['status'] != 'ready' for d in m['prerequisites']):
            issues.add('prerequisite_pending')
        m['issues'] = sorted(issues)
        if not issues and chapters and m['evidence']:
            m.update(status='ready', primary_chapter=max(chapters))
            m.pop('candidate_chapters', None)
            q['topics'] = [topic_id(max(chapters), course_for(q))]
        else:
            m.update(status='pending', primary_chapter=None)
            q['topics'] = []
        done.add(qid)
    for qid in qs:
        resolve(qid)
    return qs


def repair(snapshot, paths_file, decisions_file, output, revision):
    snapshot, output = Path(snapshot), Path(output)
    if output.exists():
        raise ValueError('Use a fresh output folder; previous evidence is not overwritten')
    index = read_json(snapshot / 'question-index.json')
    manifest = read_json(snapshot / 'source-manifest.json')
    validate(index, manifest, ROOT / 'schemas')
    if revision == index['revision'] or not revision:
        raise ValueError('Repair requires a new revision')
    previous = copy.deepcopy(index)
    sources = {s['source_id']: s for s in manifest['sources']}
    decisions, paths = read_json(decisions_file), read_json(paths_file)
    records = []
    with ExitStack() as stack:
        opened = {}
        def source(sid):
            if sid not in opened:
                if sha256(paths[sid]) != sources[sid]['sha256']:
                    raise ValueError('Source hash mismatch: ' + sid)
                doc = stack.enter_context(fitz.open(paths[sid]))
                if len(doc) != sources[sid]['page_count'] or geometry(doc) != sources[sid]['pages']:
                    raise ValueError('Source geometry mismatch: ' + sid)
                opened[sid] = doc
            return opened[sid]
        for q in index['questions']:
            m = q['metadata']['teaching']
            if m['status'] != 'pending' or not EDGE.intersection(m['issues']):
                continue
            qid = q['question_id']
            material = fingerprint(q, sources)
            if decisions.get(qid, {}).get('fingerprint') != material:
                raise ValueError('Missing or stale classification decision: ' + qid)
            qdoc, mdoc = source(q['question']['source_id']), source(q['answer']['source_id'])
            checked = ['question:' + v for v in region_issues(qdoc, m['own_regions'])]
            checked += ['context:' + v for c in m['contexts'] for v in region_issues(qdoc, c['regions'])]
            checked += ['answer:' + v for v in region_issues(mdoc, q['answer']['regions'])]
            checked += answer_content_issues(q, mdoc)
            # Source-level quarantines are immutable here. Even an ink-free
            # crop cannot prove that an absent page contained nothing useful.
            checked += ['source:' + issue for kind in ['question', 'answer']
                        for issue in sources[q[kind]['source_id']]['metadata'].get('source_integrity_issues', [])]
            before = list(m['issues'])
            remaining_edges = EDGE.intersection(checked)
            removed = sorted(EDGE.intersection(before) - remaining_edges)
            if removed:
                m['issues'] = sorted(set(before) - set(removed) | set(checked))
                qa = q['metadata']['automatic_qa']
                qa['issues'] = sorted(set(qa.get('issues', [])) - set(removed) | set(checked))
                qa['status'] = 'quarantined' if qa['issues'] else 'passed'
                qa['checks_version'] = 'teaching-parts-visible-ink-v2'
                q['metadata']['crop_edge_recheck'] = {
                    'method': PROOF_VERSION, 'material_fingerprint': material,
                    'coordinates_changed': False, 'classification_reused_without_change': True,
                    'removed_issues': removed, 'independent_human_review': False,
                }
            records.append({'question_id': qid, 'material_fingerprint': material,
                            'removed_issues': removed, 'before': before,
                            'after_material_checks': sorted(set(checked))})
    qs = finish_dependencies(index)
    index['revision'] = revision
    validate(index, manifest, ROOT / 'schemas')
    old = {q['question_id']: q for q in previous['questions']}
    for q in index['questions']:
        for key in ['question', 'answer', 'marks', 'original_question_number', 'paper', 'year', 'variant', 'session']:
            if old[q['question_id']][key] != q[key]:
                raise ValueError('Repair changed stable identity or material: ' + q['question_id'])
    newly_ready = [qid for qid, q in qs.items() if q['metadata']['teaching']['status'] == 'ready'
                   and old[qid]['metadata']['teaching']['status'] == 'pending']
    pending = [q for q in qs.values() if q['metadata']['teaching']['status'] == 'pending']
    audits = [audit_pagination(Path(paths[sid]), sources[sid]) for sid, s in sources.items()
              if s['metadata'].get('source_integrity_issues')]
    report = {'previous_revision': previous['revision'], 'revision': revision,
              'method': PROOF_VERSION, 'total': len(qs), 'newly_ready_count': len(newly_ready),
              'newly_ready_ids': newly_ready, 'remaining_pending': len(pending),
              'issue_counts': dict(collections.Counter(i for q in pending for i in q['metadata']['teaching']['issues'])),
              'rechecked': records, 'source_audits': audits,
              'stable_ids_marks_coordinates_source_hashes_preserved': True,
              'user_data_modified': False, 'independent_human_review': False}
    write_json(output / 'question-index.json', index)
    write_json(output / 'source-manifest.json', manifest)
    write_json(output / 'repair-report.json', report)
    write_json(output / 'pending.json', {'bank_id': index['bank_id'], 'revision': revision, 'questions': pending})
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', type=Path, default=ROOT / 'indexes')
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--decisions', type=Path, default=ROOT / 'indexes/teaching19-decisions.json')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--revision', required=True)
    a = p.parse_args()
    r = repair(a.snapshot, a.sources, a.decisions, a.output, a.revision)
    print({k: r[k] for k in ['total', 'newly_ready_count', 'remaining_pending']})
