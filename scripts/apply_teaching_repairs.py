"""Source-bound teaching changes after explicit curriculum and material checks.

Only classification scope alarms can be resolved. Material, marks, identities,
dependencies and official answers cannot be overridden by a teaching decision.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import fitz
from bank.format import read_json, write_json, validate, validate_schema, sha256, geometry
from bank.teaching.taxonomy import A2_TAXONOMY_ID, topics
from bank.teaching.decisions import fingerprint
from bank.importer.quality import region_issues, answer_content_issues
from repair_pending_edges import finish_dependencies

RESOLVABLE = {'no_reliable_primary_chapter', 'pure_as_task_without_reliable_a2_theme',
              'standalone_as_foundation_without_reliable_a2_theme', 'no_reliable_a2_serving_theme',
              'standalone_as_stereochemistry_without_reliable_a2_theme',
              'standalone_as_carbonyl_reduction_without_reliable_a2_theme',
              'standalone_as_optical_activity_without_reliable_a2_theme'}


def teaching_fingerprint(q):
    return hashlib.sha256(json.dumps(q['metadata']['teaching'], sort_keys=True).encode()).hexdigest()


def apply(snapshot, paths_file, decisions_file, approvals_file, output, revision):
    snapshot, output = Path(snapshot), Path(output)
    if output.exists():raise ValueError('Use a fresh output folder')
    index = read_json(snapshot / 'question-index.json');manifest = read_json(snapshot / 'source-manifest.json')
    validate(index, manifest, ROOT / 'schemas')
    if not revision or revision == index['revision']:raise ValueError('Repair needs a new revision')
    approvals = read_json(approvals_file)
    validate_schema(approvals, ROOT / 'schemas/teaching-classification-repairs.schema.json')
    sources = {s['source_id']: s for s in manifest['sources']}
    paths = read_json(paths_file);decisions = read_json(decisions_file)
    before_status = {q['question_id']: q['metadata']['teaching']['status'] for q in index['questions']}
    before_primary = {q['question_id']: q['metadata']['teaching']['primary_chapter'] for q in index['questions']}
    qs = {q['question_id']: q for q in index['questions']};seen = set();changes = []
    previous_revision = index['revision']
    for row in approvals['questions']:
        qid = row['question_id']
        if qid in seen:raise ValueError('Duplicate classification repair: ' + qid)
        seen.add(qid);q = qs[qid];m = q['metadata']['teaching']
        if q['paper'] != 4 or q['qualification'] != 'A2':raise ValueError('This policy applies only to A2 Paper 4')
        if fingerprint(q, sources) != row['material_fingerprint'] or decisions[qid]['fingerprint'] != row['material_fingerprint']:
            raise ValueError('Stale material judgment: ' + qid)
        if teaching_fingerprint(q) != row['before_teaching_fingerprint']:
            raise ValueError('Stale teaching judgment: ' + qid)
        for kind in ['question', 'answer']:
            s = sources[q[kind]['source_id']]
            if sha256(paths[s['source_id']]) != s['sha256']:raise ValueError('Source hash mismatch: ' + s['source_id'])
        with fitz.open(paths[q['question']['source_id']]) as qdoc, fitz.open(paths[q['answer']['source_id']]) as mdoc:
            for kind, doc in [('question', qdoc), ('answer', mdoc)]:
                if geometry(doc) != sources[q[kind]['source_id']]['pages']:raise ValueError('Source geometry mismatch')
            checks = ['question:' + e for e in region_issues(qdoc, m['own_regions'])]
            checks += ['context:' + e for c in m['contexts'] for e in region_issues(qdoc, c['regions'])]
            checks += ['answer:' + e for e in region_issues(mdoc, q['answer']['regions'])]
            checks += answer_content_issues(q, mdoc)
        checks += ['source:' + e for kind in ['question', 'answer']
                   for e in sources[q[kind]['source_id']]['metadata'].get('source_integrity_issues', [])]
        old_teaching_hash = teaching_fingerprint(q)
        q['metadata'].setdefault('classification_history', []).append({
            'taxonomy_id': m['taxonomy_id'], 'required_chapters': m['required_chapters'],
            'evidence': m['evidence'], 'issues': m['issues'], 'superseded_by': approvals['policy_id']})
        evidence = {'method': 'agent-read-task-context-ms-under-confirmed-teaching-policy-v1',
                    'reason': row['reason'], 'policy_id': approvals['policy_id']}
        m.update(taxonomy_id=A2_TAXONOMY_ID, required_chapters=row['required_chapters'],
                 evidence=[evidence] + [e for e in m['evidence'] if e.get('method', '').startswith('outer-vertical-')],
                 issues=sorted((set(m['issues']) - RESOLVABLE) | set(checks)))
        q['metadata']['knowledge_tags'] = row['knowledge_tags']
        q['metadata']['knowledge_tags_version'] = 'chemistry-workspace-knowledge-tags-1.0.0'
        q['metadata']['classification_repair'] = dict(policy_id=approvals['policy_id'],
            material_fingerprint=row['material_fingerprint'], before_teaching_fingerprint=old_teaching_hash,
            independent_human_review=False)
        decisions[qid].update(required_chapters=row['required_chapters'], evidence=m['evidence'],
                              issues=sorted(set(decisions[qid].get('issues', [])) - RESOLVABLE))
        changes.append(dict(question_id=qid, previous_primary_chapter=before_primary[qid],
                            resolved_scope_issues=sorted(set(q['metadata']['classification_history'][-1]['issues']) & RESOLVABLE)))
    finish_dependencies(index)
    index.update(revision=revision, topics=topics() + topics('A2'))
    validate(index, manifest, ROOT / 'schemas')
    for row in changes:
        m = qs[row['question_id']]['metadata']['teaching']
        row.update(status=m['status'], primary_chapter=m['primary_chapter'], remaining_issues=m['issues'])
    pending = [q for q in qs.values() if q['metadata']['teaching']['status'] == 'pending']
    report = dict(previous_revision=previous_revision, revision=revision, policy_id=approvals['policy_id'],
        directly_reclassified=len(changes), newly_ready=[qid for qid, q in qs.items()
            if before_status[qid] == 'pending' and q['metadata']['teaching']['status'] == 'ready'],
        newly_pending=[qid for qid, q in qs.items()
            if before_status[qid] == 'ready' and q['metadata']['teaching']['status'] == 'pending'],
        dependent_chapter_changes=[dict(question_id=qid, before=before_primary[qid], after=q['metadata']['teaching']['primary_chapter'])
            for qid, q in qs.items() if qid not in seen and before_primary[qid] != q['metadata']['teaching']['primary_chapter']],
        remaining_pending=len(pending), changes=changes, coordinates_and_stable_identities_unchanged=True,
        independent_human_review=False)
    for name, value in [('question-index', index), ('source-manifest', manifest),
                        ('teaching19-decisions', decisions), ('classification-report', report),
                        ('pending', dict(bank_id=index['bank_id'], revision=revision, questions=pending))]:
        write_json(output / (name + '.json'), value)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['snapshot', 'sources', 'decisions', 'approvals', 'output']:p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--revision', required=True);a = p.parse_args()
    r = apply(a.snapshot, a.sources, a.decisions, a.approvals, a.output, a.revision)
    print({k: r[k] for k in ['directly_reclassified', 'newly_ready', 'newly_pending', 'remaining_pending']})
