"""Reuse a read Paper 1 judgment only for byte-identical rendered question regions.

This does not classify unseen content by keywords. All context regions, extracted
text and 108-dpi RGB pixels must agree. IDs, MS coordinates and source-bound
fingerprints remain distinct. Paper 2 is excluded because dependencies can differ.
"""
import argparse, copy, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import fitz
from bank.format import read_json, write_json, sha256
from bank.pdf_layout import layout_page

RENDER_VERSION = 'identical-qp-regions-rgb-108dpi-v1'


def material_key(question, record, document):
    text_hash = hashlib.sha256(record['task'].encode()).hexdigest()
    rasters = []
    for region in question['question']['regions']:
        pix = layout_page(document, region['page_index']).get_pixmap(
            matrix=fitz.Matrix(1.5, 1.5), clip=fitz.Rect(region['bbox']), alpha=False)
        rasters.append((pix.width, pix.height, pix.n,
                        hashlib.sha256(pix.samples).hexdigest()))
    return (RENDER_VERSION, text_hash, tuple(rasters))


def reuse(workdir, paths_file, decisions_file, output, apply=False):
    index = read_json(workdir / 'question-index.json')
    sources = {s['source_id']: s for s in read_json(workdir / 'source-manifest.json')['sources']}
    records = {r['question_id']: r for r in read_json(workdir / 'candidates.private.json')}
    paths = read_json(paths_file)
    decisions = read_json(decisions_file)
    original_decisions = copy.deepcopy(decisions)
    grouped = {}
    for q in index['questions']:
        if q['paper'] == 1:
            grouped.setdefault(q['question']['source_id'], []).append(q)
    keys = {}
    for sid, questions in grouped.items():
        if sha256(paths[sid]) != sources[sid]['sha256']:
            raise ValueError('Source hash mismatch: ' + sid)
        with fitz.open(paths[sid]) as doc:
            for q in questions:
                keys[q['question_id']] = material_key(q, records[q['question_id']], doc)
    references = {}
    for qid, d in original_decisions.items():
        if qid not in keys or d.get('prerequisites') or d.get('issues'):
            continue
        if d['fingerprint'] != records[qid]['fingerprint']:
            raise ValueError('Stale reference decision: ' + qid)
        references.setdefault(keys[qid], qid)
    proof = []
    for qid, key in keys.items():
        if qid in decisions or key not in references:
            continue
        reference = references[key]
        d = copy.deepcopy(original_decisions[reference])
        d['fingerprint'] = records[qid]['fingerprint']
        d['evidence'].append({
            'method': 'identical-rendered-question-region',
            'reference_question_id': reference,
            'reason': f'All question/context RGB rasters at 108 dpi and exact extracted task text match {reference}; the read classification is reused without copying its ID or answer.'})
        decisions[qid] = d
        proof.append(dict(question_id=qid, reference_question_id=reference,
                          text_sha256=key[1], region_rasters=key[2]))
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'decisions.json', decisions)
    write_json(output / 'identity-proof.json', dict(render_version=RENDER_VERSION, matches=proof))
    if apply:
        write_json(output / 'decisions-before.json', original_decisions)
        write_json(decisions_file, decisions)
    print(f'Compared {len(keys)} Paper 1 units; reused {len(proof)} source-bound judgments; total {len(decisions)}.')
    return proof


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workdir', type=Path, default=ROOT / 'data/teaching19')
    p.add_argument('--sources', type=Path, default=ROOT / 'data/import-v04/all-source-files.private.json')
    p.add_argument('--decisions', type=Path, default=ROOT / 'data/teaching19-decisions.json')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    reuse(a.workdir, a.sources, a.decisions, a.output, a.apply)
