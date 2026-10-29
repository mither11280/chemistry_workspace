"""Apply the teacher-confirmed chapter 11 extension without clearing material gates."""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import fitz
from bank.format import read_json, write_json, validate, validate_schema, sha256, geometry
from bank.teaching.decisions import fingerprint
from bank.teaching.taxonomy import topics, A2_TAXONOMY_ID
from bank.importer.quality import region_issues, answer_content_issues
from repair_pending_edges import finish_dependencies

SCOPE_ISSUES = {'single_step_cycloaddition_without_reliable_taxonomy_fit',
                'single_step_ozonolysis_without_reliable_taxonomy_fit'}


def apply(snapshot, paths_file, decisions_file, approvals_file, output, revision):
    snapshot, output = Path(snapshot), Path(output)
    if output.exists():raise ValueError('Use a fresh output folder')
    index = read_json(snapshot / 'question-index.json');manifest = read_json(snapshot / 'source-manifest.json')
    validate(index, manifest, ROOT / 'schemas')
    if not revision or revision == index['revision']:raise ValueError('Extension needs a new revision')
    approvals = read_json(approvals_file)
    validate_schema(approvals, ROOT / 'schemas/organic-scope-extension.schema.json')
    paths = read_json(paths_file);decisions = read_json(decisions_file)
    sources = {s['source_id']: s for s in manifest['sources']}
    qs = {q['question_id']: q for q in index['questions']};seen = set();records = []
    previous_revision = index['revision']
    for row in approvals['questions']:
        qid = row['question_id']
        if qid in seen:raise ValueError('Duplicate scope correction')
        seen.add(qid);q = qs[qid];m = q['metadata']['teaching'];old_status = m['status']
        if q['paper'] != 4 or not SCOPE_ISSUES.intersection(m['issues']):
            raise ValueError('Scope extension only resolves the recorded single-step scope questions: ' + qid)
        if fingerprint(q, sources) != row['fingerprint'] or decisions[qid]['fingerprint'] != row['fingerprint']:
            raise ValueError('Stale scope judgment: ' + qid)
        for kind in ['question', 'answer']:
            s = sources[q[kind]['source_id']]
            if sha256(paths[s['source_id']]) != s['sha256']:raise ValueError('Source hash mismatch')
        with fitz.open(paths[q['question']['source_id']]) as qdoc, fitz.open(paths[q['answer']['source_id']]) as mdoc:
            for kind, doc in [('question', qdoc), ('answer', mdoc)]:
                if geometry(doc) != sources[q[kind]['source_id']]['pages']:
                    raise ValueError('Source geometry mismatch: ' + qid)
            # Any new alarm is retained; this curriculum decision is never an
            # override for a clipped diagram, missing page or incorrect MS row.
            checks = ['question:' + v for v in region_issues(qdoc, m['own_regions'])]
            checks += ['context:' + v for c in m['contexts'] for v in region_issues(qdoc, c['regions'])]
            checks += ['answer:' + v for v in region_issues(mdoc, q['answer']['regions'])]
            checks += answer_content_issues(q, mdoc)
        checks += ['source:' + issue for kind in ['question', 'answer']
                   for issue in sources[q[kind]['source_id']]['metadata'].get('source_integrity_issues', [])]
        q['metadata'].setdefault('classification_history', []).append({
            'taxonomy_id': m['taxonomy_id'], 'required_chapters': m['required_chapters'],
            'evidence': m['evidence'], 'issues': list(m['issues']),
            'superseded_by': approvals['policy_id']})
        evidence = {'method': 'teacher-confirmed-scope-and-agent-source-reading-v1',
                    'reason': row['reason'], 'policy_id': approvals['policy_id']}
        m.update(taxonomy_id=A2_TAXONOMY_ID, required_chapters=[11], evidence=[evidence] +
                 [e for e in m['evidence'] if e.get('method', '').startswith('outer-vertical-')])
        m['issues'] = sorted((set(m['issues']) - SCOPE_ISSUES - {'no_reliable_primary_chapter'}) | set(checks))
        q['metadata']['knowledge_tags'] = row['knowledge_tags']
        q['metadata']['knowledge_tags_version'] = 'chemistry-workspace-knowledge-tags-1.0.0'
        decisions[qid].update(required_chapters=[11], evidence=m['evidence'])
        decisions[qid]['issues'] = sorted(set(decisions[qid].get('issues', [])) - SCOPE_ISSUES - {'no_reliable_primary_chapter'})
        records.append({'question_id': qid, 'previous_status': old_status,
                        'fingerprint': row['fingerprint'], 'knowledge_tags': row['knowledge_tags']})
    finish_dependencies(index)
    index.update(revision=revision, topics=topics() + topics('A2'))
    validate(index, manifest, ROOT / 'schemas')
    pending = [q for q in qs.values() if q['metadata']['teaching']['status'] == 'pending']
    for row in records:
        m = qs[row['question_id']]['metadata']['teaching']
        row.update(status=m['status'], remaining_issues=m['issues'])
    report = dict(previous_revision=previous_revision, revision=revision, policy_id=approvals['policy_id'],
                  classified=len(records), newly_ready=sum(r['status'] == 'ready' for r in records),
                  remaining_pending=len(pending), questions=records,
                  ids_coordinates_marks_hashes_unchanged=True, independent_human_review=False)
    for name, obj in [('question-index', index), ('source-manifest', manifest),
                      ('teaching19-decisions', decisions), ('scope-report', report),
                      ('pending', dict(bank_id=index['bank_id'], revision=revision, questions=pending))]:
        write_json(output / (name + '.json'), obj)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['snapshot', 'sources', 'decisions', 'approvals', 'output']:p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--revision', required=True);a = p.parse_args()
    print(apply(a.snapshot, a.sources, a.decisions, a.approvals, a.output, a.revision))
