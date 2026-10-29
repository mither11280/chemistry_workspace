"""Assemble reviewed, source-bound AS/A2 snapshots without touching user data.

Inputs contain independently validated coordinates and judgments. Assembly
does not infer classifications, source equivalence, marks or missing regions.
"""
import argparse
import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from bank.format import read_json, write_json, validate
from bank.teaching.decisions import fingerprint
from bank.teaching.taxonomy import BANK_ID
from apply_teaching_decisions import apply


def assemble(as_snapshot, a2_snapshot, previous, output, revision):
    as_snapshot, a2_snapshot, previous, output = map(
        Path, (as_snapshot, a2_snapshot, previous, output))
    if output.exists():
        raise ValueError('Use a fresh assembly folder')
    base = read_json(previous / 'question-index.json')
    old_manifest = read_json(previous / 'source-manifest.json')
    snapshots = [as_snapshot, a2_snapshot]
    indices = [read_json(p / 'question-index.json') for p in snapshots]
    if any(i['bank_id'] != BANK_ID for i in [base, *indices]):
        raise ValueError('Same-generation extension requires the known bank ID')
    if revision in [base['revision'], base['revision'] + '.assets.1']:
        raise ValueError('Extension requires a new revision')
    if any(q['paper'] not in (1, 2) for q in indices[0]['questions']):
        raise ValueError('AS input contains another paper')
    if any(q['paper'] != 4 for q in indices[1]['questions']):
        raise ValueError('A2 input must contain only Paper 4')
    as_ids = {q['question_id'] for q in indices[0]['questions']}
    if as_ids != {q['question_id'] for q in base['questions']}:
        raise ValueError('AS extension must preserve every previous question ID')
    old_questions = {q['question_id']: q for q in base['questions']}
    for q in indices[0]['questions']:
        old = old_questions[q['question_id']]
        for field in ['original_question_number', 'marks', 'paper', 'variant',
                      'year', 'session', 'topics']:
            if q[field] != old[field]:
                raise ValueError('Unexpected AS identity/classification change: ' + q['question_id'])
    index = copy.deepcopy(indices[1])
    index['revision'] = revision
    index['questions'] = indices[0]['questions'] + indices[1]['questions']
    if len({q['question_id'] for q in index['questions']}) != len(index['questions']):
        raise ValueError('Duplicate question identity')
    manifest = read_json(a2_snapshot / 'source-manifest.json')
    source_map = {s['source_id']: s for s in manifest['sources']}
    for source in old_manifest['sources']:
        if source_map.get(source['source_id']) != source:
            raise ValueError('Previous AS source contract changed: ' + source['source_id'])
    decisions, records = {}, []
    for folder, source_index in zip(snapshots, indices):
        selected = {q['question_id'] for q in source_index['questions']}
        ds = read_json(folder / 'decisions.json')
        rs = read_json(folder / 'candidates.private.json')
        if set(ds) != selected or {r['question_id'] for r in rs} != selected:
            raise ValueError('Every input question requires a bound judgment and candidate record')
        for q in source_index['questions']:
            if ds[q['question_id']]['fingerprint'] != fingerprint(q, source_map):
                raise ValueError('Stale input decision: ' + q['question_id'])
        decisions.update(ds)
        records.extend(rs)
    validate(index, manifest, ROOT / 'schemas')
    # Intermediate private input remains separate from the portable public
    # output. Only the latter should be copied into the repository's indexes.
    measured = output / 'private-input'
    write_json(measured / 'question-index.json', index)
    write_json(measured / 'source-manifest.json', manifest)
    write_json(measured / 'decisions.json', decisions)
    write_json(measured / 'candidates.private.json', records)
    report = apply(measured, measured / 'decisions.json', output / 'public')
    write_json(output / 'assembly.json', {
        'bank_id': BANK_ID, 'revision': revision,
        'previous_revision': base['revision'],
        'preserved_as_ids': len(as_ids),
        'added_a2_ids': len(indices[1]['questions']),
        'sources': len(manifest['sources']),
        'ready': report['ready'], 'pending': report['pending'],
        'user_data_modified': False,
    })
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-snapshot', type=Path, required=True)
    parser.add_argument('--a2-snapshot', type=Path, required=True)
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    assemble(args.as_snapshot, args.a2_snapshot, args.previous, args.output, args.revision)
