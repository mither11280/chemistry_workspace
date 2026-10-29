"""Refresh exact official MS rows after explicit source-bound content checks.

No fuzzy labels, inferred marks, source substitutions or quarantine overrides.
Each approval binds both the old material and the newly measured official row.
"""
import argparse
import copy
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import fitz
from bank.format import read_json, write_json, validate, validate_schema, sha256, geometry
from bank.teaching.decisions import fingerprint
from bank.teaching.parts import label_path, ms_parts
from bank.importer.quality import region_issues, answer_content_issues
from repair_pending_edges import finish_dependencies

REPAIRABLE = {'exact_ms_label_missing', 'subpart_marks_mismatch'}


def repair(snapshot, paths_file, decisions_file, approvals_file, output, revision):
    snapshot, output = Path(snapshot), Path(output)
    if output.exists():
        raise ValueError('Use a fresh output folder')
    index = read_json(snapshot / 'question-index.json');manifest = read_json(snapshot / 'source-manifest.json')
    validate(index, manifest, ROOT / 'schemas')
    if not revision or revision == index['revision']:
        raise ValueError('Repair requires a new revision')
    approvals = read_json(approvals_file)
    validate_schema(approvals, ROOT / 'schemas/ms-row-repairs.schema.json')
    decisions, paths = read_json(decisions_file), read_json(paths_file)
    sources = {s['source_id']: s for s in manifest['sources']}
    qs = {q['question_id']: q for q in index['questions']}
    before = copy.deepcopy(index);changes = []
    seen = set()
    for approval in approvals['repairs']:
        qid = approval['question_id']
        if qid in seen:
            raise ValueError('Duplicate repair: ' + qid)
        seen.add(qid);q = qs[qid];m = q['metadata']['teaching']
        old_fingerprint = fingerprint(q, sources)
        if old_fingerprint != approval['before_fingerprint'] or decisions[qid]['fingerprint'] != old_fingerprint:
            raise ValueError('Stale before-material approval: ' + qid)
        if m['status'] != 'pending' or not set(m['issues']) or set(m['issues']) - REPAIRABLE:
            raise ValueError('Exact-row repair cannot waive other pending reasons: ' + qid)
        for kind in ['question', 'answer']:
            s = sources[q[kind]['source_id']]
            if sha256(paths[s['source_id']]) != s['sha256']:
                raise ValueError('Source hash mismatch: ' + s['source_id'])
            if s['metadata'].get('source_integrity_issues'):
                raise ValueError('Source integrity unresolved: ' + s['source_id'])
        with fitz.open(paths[q['question']['source_id']]) as qdoc, fitz.open(paths[q['answer']['source_id']]) as mdoc:
            for kind, doc in [('question', qdoc), ('answer', mdoc)]:
                if geometry(doc) != sources[q[kind]['source_id']]['pages']:
                    raise ValueError('Source geometry mismatch: ' + qid)
            row = ms_parts(mdoc)[0].get(label_path(q['original_question_number']))
            if not row or row['marks'] != q['marks']:
                raise ValueError('Exact MS label and marks still do not match: ' + qid)
            q['answer']['regions'] = copy.deepcopy(row['regions'])
            new_fingerprint = fingerprint(q, sources)
            if new_fingerprint != approval['after_fingerprint']:
                raise ValueError('Stale measured-row approval: ' + qid)
            problems = region_issues(qdoc, q['question']['regions']) + region_issues(mdoc, q['answer']['regions']) + answer_content_issues(q, mdoc)
            if problems:
                raise ValueError('Repaired material fails QA: ' + qid + ' ' + ','.join(problems))
        prior_issues = list(m['issues']);m['issues'] = []
        evidence = {'method': 'agent-read-exact-ms-row-restoration-v1', 'reason': approval['reason']}
        m['evidence'].append(evidence)
        q['metadata']['automatic_qa'] = {'status': 'passed', 'checks_version': 'teaching-parts-visible-ink-v2', 'issues': []}
        q['metadata']['ms_row_repair'] = dict(approval, method=evidence['method'], independent_human_review=False)
        decisions[qid]['fingerprint'] = new_fingerprint
        decisions[qid]['evidence'] = copy.deepcopy(m['evidence'])
        changes.append({'question_id': qid, 'before': prior_issues, 'before_fingerprint': old_fingerprint,
                        'after_fingerprint': new_fingerprint, 'reason': approval['reason']})
    finish_dependencies(index)
    index['revision'] = revision
    validate(index, manifest, ROOT / 'schemas')
    pending = [q for q in index['questions'] if q['metadata']['teaching']['status'] == 'pending']
    report = {'previous_revision': before['revision'], 'revision': revision, 'direct_ms_repairs': len(changes),
              'remaining_pending': len(pending), 'repairs': changes, 'user_data_modified': False,
              'question_coordinates_ids_marks_source_hashes_preserved': True, 'independent_human_review': False}
    for name, value in [('question-index', index), ('source-manifest', manifest),
                        ('teaching19-decisions', decisions), ('repair-report', report),
                        ('pending', {'bank_id': index['bank_id'], 'revision': revision, 'questions': pending})]:
        write_json(output / (name + '.json'), value)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ['snapshot', 'sources', 'decisions', 'approvals', 'output']:
        p.add_argument('--' + flag, type=Path, required=True)
    p.add_argument('--revision', required=True);a = p.parse_args()
    r = repair(a.snapshot, a.sources, a.decisions, a.approvals, a.output, a.revision)
    print({k: r[k] for k in ['direct_ms_repairs', 'remaining_pending']})
