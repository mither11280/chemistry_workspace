"""Real-source regression for a repaired snapshot, using only isolated profiles.

Exercises the actual HTTP update/save/share/preview/export paths, then rollback,
failure recovery and repeat installation. This is not a frozen-App acceptance.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time
import urllib.request
from unittest.mock import patch
import fitz
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from bank.catalog import Catalog
from bank.format import read_json, write_json, sha256, validate
from bank.updates import build_package, install_package, rollback


def verify(previous, snapshot, sources, output):
    previous, snapshot, output = map(Path, (previous, snapshot, output))
    if output.exists():raise ValueError('Use a fresh verification folder')
    old = read_json(previous / 'question-index.json');new = read_json(snapshot / 'question-index.json')
    manifest = read_json(snapshot / 'source-manifest.json');old_manifest = read_json(previous / 'source-manifest.json')
    validate(new, manifest, ROOT / 'schemas')
    assert manifest == old_manifest
    old_qs = {q['question_id']: q for q in old['questions']}
    assert old_qs.keys() == {q['question_id'] for q in new['questions']}
    recovered = [q['question_id'] for q in new['questions']
                 if q['metadata']['teaching']['status'] == 'ready'
                 and old_qs[q['question_id']]['metadata']['teaching']['status'] == 'pending']
    assert len(recovered) >= 20
    resources = output / 'resources';resources.mkdir(parents=True)
    shutil.copytree(ROOT / 'schemas', resources / 'schemas')
    shutil.copytree(ROOT / 'app', resources / 'app', ignore=shutil.ignore_patterns('__pycache__'))
    (resources / 'indexes').mkdir(exist_ok=True)
    for name in ['question-index.json', 'source-manifest.json']:shutil.copyfile(previous / name, resources / 'indexes' / name)
    write_json(resources / 'build-info.json', {'version': '0.5.2', 'distribution': 'development-source-acceptance'})
    profile = output / 'profile';paths = read_json(sources)
    for source in manifest['sources']:
        assert sha256(paths[source['source_id']]) == source['sha256']
        dest = profile / source['path'];dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(paths[source['source_id']], dest)
    # Model an installed v0.5.1 profile before adding teacher state. A loose
    # local overlay without a generation marker is legacy import input.
    from bank.teaching.generation import prepare
    prepare(profile, resources)
    calibrated = copy.deepcopy(old_qs['cie-9701-m24-12-q4'])
    calibrated['metadata']['calibration'] = 'manual'
    overlay = profile / 'data/question-index.local.json'
    write_json(overlay, {'questions': [calibrated]});overlay_before = overlay.read_bytes()
    package = output / 'reliability-index.qbank'
    package_info = build_package(package, new, manifest, old, old_manifest, ROOT / 'schemas',
        'Source-backed pending repairs and teacher-confirmed organic methods; preserves all identities and work.',
        minimum_app_version='0.5.2')
    env = dict(os.environ, QUESTION_BANK_HOME=str(profile.resolve()), QUESTION_BANK_RESOURCES=str(resources.resolve()))
    env.pop('QUESTION_BANK_ROOT', None)
    report = {'previous_revision': old['revision'], 'revision': new['revision'],
              'environment': 'Development Python HTTP backend; isolated profile; no real teacher data.',
              'source_files': len(manifest['sources']), 'recovered': len(recovered),
              'independent_human_review': False, 'package': dict(package_info, path=package.name)}
    log = (output / 'backend.log').open('w')
    process = subprocess.Popen([sys.executable, str(ROOT / 'app/server.py')], cwd=output,
                               env=env, stdout=subprocess.PIPE, stderr=log, text=True)
    try:
        assert select.select([process.stdout], [], [], 60)[0]
        base = process.stdout.readline().strip();assert base.startswith('http://127.0.0.1:')
        def get(path):return urllib.request.urlopen(base + path, timeout=180).read()
        def post(path, body):
            return json.load(urllib.request.urlopen(urllib.request.Request(base + path, json.dumps(body).encode(),
                headers={'Content-Type': 'application/json', 'X-Local-Request': '1'}), timeout=180))
        bank = json.loads(get('/api/bank'));report['previous_ready'] = bank['total']
        job = dict(title='Existing teacher work - preserve', notes='Preserve order and notes.',
                   question_ids=['cie-9701-m24-12-q4', 'cie-9701-m25-42-q1-c-ii'])
        saved = post('/api/save', job);post('/api/draft', saved);code = post('/api/share', saved)['code']
        personal = profile / 'data/personal.sqlite3';personal_before = personal.read_bytes()
        request = urllib.request.Request(base + '/api/bank-update-upload', package.read_bytes(),
            headers={'Content-Type': 'application/octet-stream', 'X-Local-Request': '1'})
        preview = json.load(urllib.request.urlopen(request, timeout=180))
        assert json.loads(get('/api/bank'))['revision'] == old['revision']
        start = time.perf_counter()
        installed = post('/api/bank-update-install', {'token': preview['token'], 'sha256': preview['sha256']})
        report['install_seconds'] = round(time.perf_counter() - start, 4)
        bank = json.loads(get('/api/bank'));assert bank['revision'] == new['revision']
        assert personal.read_bytes() == personal_before and overlay.read_bytes() == overlay_before
        assert post('/api/import', {'code': code})['question_ids'] == saved['question_ids']
        assert json.loads(get('/api/draft'))['question_ids'] == saved['question_ids']
        assert next(j for j in json.loads(get('/api/jobs')) if j['id'] == saved['id'])['notes'] == job['notes']
        previews = 0;cold = 0;warm = 0
        for qid in recovered:
            q = json.loads(get('/api/questions?ids=' + qid))['questions'][0]
            assert q['metadata']['teaching']['status'] == 'ready'
            for kind in ['question', 'answer']:
                for n in range(len(q[kind + '_regions'])):
                    path = f'/preview/{qid}/{kind}/{n}';start = time.perf_counter()
                    assert get(path).startswith(b'RIFF');cold += time.perf_counter() - start
                    start = time.perf_counter();assert get(path).startswith(b'RIFF');warm += time.perf_counter() - start
                    previews += 1
        # Stratify the 20-unit sample so it includes the restored diagram rows,
        # AS font-box overlaps, and the newly admitted A2 organic methods.
        ms_ids = [qid for qid in recovered if next(q for q in new['questions'] if q['question_id'] == qid)['metadata'].get('ms_row_repair')]
        a2_ids = [qid for qid in recovered if old_qs[qid]['paper'] == 4]
        selected = list(dict.fromkeys(ms_ids + a2_ids[:4] + recovered))[:20]
        remaining = [qid for qid in recovered if qid not in selected]
        exports = []
        for label, ids in [('twenty-repaired', selected), ('remaining-repaired', remaining)]:
            if not ids:continue
            resolved = json.loads(get('/api/worksheet?ids=' + ','.join(ids)))
            for kind in ['questions', 'answers']:
                start = time.perf_counter();result = post('/api/export', {'job': dict(title=label, notes='Complete every question.', question_ids=ids), 'kind': kind})
                pdf = get(result['url']);seconds = time.perf_counter() - start
                dest = output / (label + '-' + kind + '.pdf');dest.write_bytes(pdf)
                mapping = read_json(profile / result['url'].lstrip('/').replace('.pdf', '.mapping.json'))
                assert [m['question_id'] for m in mapping] == resolved['question_ids']
                with fitz.open(dest) as doc:
                    pages = len(doc);assert all(page.get_text().strip() for page in doc)
                    assert sum(len(page.get_fonts()) for page in doc) > 0
                    for n, page in enumerate(doc):
                        folder = output / 'rendered' / (label + '-' + kind);folder.mkdir(parents=True, exist_ok=True)
                        page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25)).save(folder / f'{n:03}.png')
                exports.append(dict(sample=label, kind=kind, selected_units=len(ids),
                    resolved_units=resolved['question_count'], marks=resolved['marks'], pages=pages,
                    seconds=round(seconds, 4), bytes=len(pdf), sha256=sha256(dest), filename=dest.name))
        checks = json.loads(get('/api/check'));assert checks['catalog']['integrity'] == 'ok'
        assert all(s['state'] == 'ready' for s in checks['sources'])
        report.update(ready=bank['total'], pending=bank['pending'], preview_regions=previews,
                      cold_preview_seconds=round(cold, 4), warm_preview_seconds=round(warm, 4), exports=exports,
                      old_share_draft_notes_order_preserved=True, personal_and_calibration_byte_identical=True)
    finally:
        if process.poll() is None:process.terminate()
        process.wait(timeout=30);log.close()
    cat = Catalog(profile, resources=resources)
    rollback(cat, installed['backup_id']);assert cat.index['revision'] == old['revision']
    assert cat.search()['total'] == report['previous_ready']
    assert personal.read_bytes() == personal_before and overlay.read_bytes() == overlay_before
    with patch.object(cat, 'rebuild', side_effect=RuntimeError('injected rebuild failure')):
        try:install_package(cat, package);raise AssertionError('Failure was not injected')
        except RuntimeError as exc:assert 'injected rebuild' in str(exc)
    assert not (profile / 'data/bank-updates/current.json').exists()
    assert personal.read_bytes() == personal_before and overlay.read_bytes() == overlay_before
    cat.rebuild();assert cat.search()['total'] == report['previous_ready']
    install_package(cat, package);assert install_package(cat, package)['already_installed']
    assert personal.read_bytes() == personal_before and overlay.read_bytes() == overlay_before
    report.update(status='passed', rollback_and_failed_rebuild_recovery=True, repeat_install=True,
                  all_export_pages_rendered=True, rendered_pages_independently_human_reviewed=False)
    write_json(output / 'verification.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['previous', 'snapshot', 'sources', 'output']:p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args();verify(a.previous, a.snapshot, a.sources, a.output)
