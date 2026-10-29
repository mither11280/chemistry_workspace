"""Exercise bundled repairs against actual published base/full index states.

Only isolated metadata profiles are used. Source availability/PDF export is
covered separately by verify_reliability_update.py, not claimed by this tool.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from unittest.mock import patch
import zipfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from bank.catalog import Catalog
from bank.format import read_json, write_json
from bank.teaching.extension import recognized
from runtime import RuntimePaths


def verify(previous, snapshot, released_full, output):
    previous, snapshot, output = map(Path, (previous, snapshot, output))
    if output.exists():raise ValueError('Use a fresh output folder')
    old = read_json(previous / 'question-index.json');manifest = read_json(previous / 'source-manifest.json')
    new = read_json(snapshot / 'question-index.json')
    with zipfile.ZipFile(released_full) as archive:
        full = json.loads(archive.read('question-index.json'));full_manifest = json.loads(archive.read('source-manifest.json'))
    assert recognized(old, manifest) and recognized(full, full_manifest)
    resources = {}
    for name, index, version in [('old', old, '0.5.1'), ('new', new, '0.5.2')]:
        folder = output / (name + '-resources');folder.mkdir(parents=True)
        shutil.copytree(ROOT / 'schemas', folder / 'schemas')
        write_json(folder / 'indexes/question-index.json', index)
        write_json(folder / 'indexes/source-manifest.json', manifest)
        write_json(folder / 'build-info.json', {'version': version, 'distribution': 'isolated-adoption-test'})
        resources[name] = folder
    results = []
    for mode in ['bundled-base', 'activated-full', 'custom-full', 'failed-rebuild']:
        profile = output / mode
        runtime = RuntimePaths(resources['old'], profile, False);runtime.prepare()
        cat = Catalog(profile, resources=resources['old']);runtime.mark_ready()
        personal = profile / 'data/personal.sqlite3'
        with sqlite3.connect(personal) as db:
            db.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,title TEXT,body TEXT,updated REAL)')
            db.execute('INSERT INTO jobs VALUES (?,?,?,?)', ('authored-test', 'Keep work', json.dumps({'question_ids': ['cie-9701-m24-12-q4'], 'notes': 'Keep teacher note.'}), 1))
        local = profile / 'data/question-index.local.json';calibrated = copy.deepcopy(old['questions'][0])
        calibrated['metadata']['calibration'] = 'manual'
        write_json(local, {'questions': [calibrated]})
        if mode != 'bundled-base':
            active = copy.deepcopy(full)
            if mode == 'custom-full':active['questions'][-1]['metadata']['custom_test_annotation'] = 'Preserve explicit custom version'
            folder = profile / 'data/bank-updates/generations/old-full'
            write_json(folder / 'question-index.json', active);write_json(folder / 'source-manifest.json', full_manifest)
            write_json(profile / 'data/bank-updates/current.json', {'generation': 'generations/old-full', 'revision': active['revision']})
        cat.rebuild()
        before, overlay_before = personal.read_bytes(), local.read_bytes()
        pointer = profile / 'data/bank-updates/current.json'
        pointer_before = pointer.read_bytes() if pointer.exists() else None
        runtime = RuntimePaths(resources['new'], profile, False)
        version_backup = runtime.prepare();assert version_backup and (version_backup / 'personal.sqlite3').exists()
        if mode == 'failed-rebuild':
            with patch.object(Catalog, 'rebuild', side_effect=RuntimeError('injected actual-index rebuild failure')):
                try:Catalog(profile, resources=resources['new']);raise AssertionError('Failure not injected')
                except RuntimeError:pass
            assert pointer.read_bytes() == pointer_before
            assert personal.read_bytes() == before and local.read_bytes() == overlay_before
        upgraded = Catalog(profile, resources=resources['new'])
        if mode == 'custom-full':
            assert upgraded.index['revision'] == full['revision'] and '自定义' in upgraded.upgrade_notice
            assert pointer.read_bytes() == pointer_before
        else:
            assert upgraded.index['revision'] == new['revision']
            assert upgraded.search()['total'] == sum(q['metadata']['teaching']['status'] == 'ready' for q in new['questions'])
            assert not pointer.exists()
        runtime.mark_ready()
        backups = len(list((profile / 'data/bundled-extension-backups').glob('*')))
        again = Catalog(profile, resources=resources['new']);assert again.index['revision'] == upgraded.index['revision']
        assert len(list((profile / 'data/bundled-extension-backups').glob('*'))) == backups
        assert RuntimePaths(resources['new'], profile, False).prepare() is None
        assert personal.read_bytes() == before and local.read_bytes() == overlay_before
        results.append(dict(mode=mode, status='passed', revision=upgraded.index['revision'],
                            personal_and_manual_overlay_byte_identical=True, repeated_adoption_idempotent=True,
                            version_backup_created=True, custom_preserved=mode == 'custom-full',
                            actual_published_full_metadata_used=mode != 'bundled-base'))
    report = dict(status='passed', previous_revision=old['revision'], revision=new['revision'],
                  environment='Isolated runtime/catalog metadata profiles; actual published v0.5.1 base/full indices.',
                  cases=results, original_teacher_profile_accessed=False, source_rendering_not_claimed_by_this_tool=True)
    write_json(output / 'verification.json', report);print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['previous', 'snapshot', 'released-full', 'output']:p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args();verify(a.previous, a.snapshot, a.released_full, a.output)
