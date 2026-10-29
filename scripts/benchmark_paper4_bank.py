"""Measure the actual combined bank in an isolated local profile."""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from bank.catalog import Catalog
from bank.sources import SourceStore
from bank.render import Renderer
from bank.format import read_json, write_json, sha256
from bank.teaching.worksheet import resolve


def benchmark(snapshot, sources, output):
    snapshot, output = Path(snapshot), Path(output)
    if output.exists():
        raise ValueError('Use a fresh benchmark directory')
    resources = output / 'resources'
    resources.mkdir(parents=True)
    shutil.copytree(ROOT / 'schemas', resources / 'schemas')
    for name in ['question-index.json', 'source-manifest.json']:
        write_json(resources / 'indexes' / name, read_json(snapshot / name))
    manifest = read_json(snapshot / 'source-manifest.json')
    paths = read_json(sources)
    profile = output / 'profile'
    for source in manifest['sources']:
        path = Path(paths[source['source_id']])
        if sha256(path) != source['sha256']:
            raise ValueError('Source hash mismatch: ' + source['source_id'])
        destination = profile / source['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    start = time.perf_counter()
    catalog = Catalog(profile, resources=resources)
    initial = time.perf_counter() - start
    store = SourceStore(profile, catalog)
    renderer = Renderer(catalog, store)
    ready = [q for q in catalog.index['questions']
             if q['metadata']['teaching']['status'] == 'ready']
    p4 = [q for q in ready if q['paper'] == 4]
    for course, papers in [('AS', (1, 2)), ('A2', (4,))]:
        assert catalog.search({'course': course})['total'] == sum(q['paper'] in papers for q in ready)
    start = time.perf_counter()
    for q in ready:
        resolved = resolve(catalog, [q['question_id']])
        assert len(resolved['question_ids']) == len(set(resolved['question_ids']))
    closure_seconds = time.perf_counter() - start
    independent = [q for q in p4 if not q['metadata']['teaching']['prerequisites']]
    selected, source_ids = [], set()
    def select(q):
        selected.append(q['question_id'])
        source_ids.add(q['question']['source_id'])
    # Include every teaching chapter, then a genuinely cross-page task, then
    # spread the remaining units across additional actual source papers.
    for chapter in range(1, 13):
        select(next(q for q in independent if q['metadata']['teaching']['primary_chapter'] == chapter))
    cross_page = next(q for q in independent if q['question_id'] not in selected
                      and len({r['page_index'] for r in q['metadata']['teaching']['own_regions']}) > 1)
    select(cross_page)
    for q in independent:
        if q['question_id'] not in selected and q['question']['source_id'] not in source_ids:
            select(q)
            if len(selected) == 20:
                break
    assert len(selected) == 20
    cold, warm, regions = 0, 0, 0
    for qid in selected:
        q = catalog.question(qid)
        for kind in ['question', 'answer']:
            for n in range(len(q[kind]['regions'])):
                start = time.perf_counter()
                assert renderer.preview(qid, kind, n).startswith(b'RIFF')
                cold += time.perf_counter() - start
                start = time.perf_counter()
                renderer.preview(qid, kind, n)
                warm += time.perf_counter() - start
                regions += 1
    exports = {}
    groups = {
        'twenty-paper4': selected,
        'mixed-dependencies': ['cie-9701-m24-12-q4', 'cie-9701-m24-22-q1-a',
                               'cie-9701-m25-42-q1-c-ii', 'cie-9701-s26-42-q7-d-ii'],
    }
    for label, ids in groups.items():
        expected = resolve(catalog, ids)
        for kind in ['questions', 'answers']:
            start = time.perf_counter()
            path = renderer.export({'title': label, 'notes': 'Complete every question.',
                                    'question_ids': ids}, kind, output / 'exports')
            seconds = time.perf_counter() - start
            mapping = read_json(path.with_suffix('.mapping.json'))
            assert [r['question_id'] for r in mapping] == expected['question_ids']
            with fitz.open(path) as doc:
                assert all(p.get_text().strip() for p in doc)
                assert sum(len(p.get_fonts()) for p in doc) > 0
                exports[label + '-' + kind] = {
                    'seconds': round(seconds, 4), 'bytes': path.stat().st_size,
                    'pages': len(doc), 'resolved_units': len(expected['question_ids']),
                    'marks': expected['marks'],
                    'path': path.relative_to(output).as_posix(),
                }
    result = {
        'status': 'structural-checks-passed-awaiting-visual-inspection',
        'selection_units': len(catalog.index['questions']), 'ready': len(ready),
        'registered_sources': len(manifest['sources']),
        'initial_catalog_seconds': round(initial, 4),
        'all_ready_dependency_closures_seconds': round(closure_seconds, 4),
        'cold_preview_regions': regions, 'cold_preview_seconds': round(cold, 4),
        'cached_preview_seconds': round(warm, 4), 'twenty_question_ids': selected,
        'source_pdf_bytes': sum(Path(paths[s['source_id']]).stat().st_size for s in manifest['sources']),
        'index_json_bytes': sum((snapshot / n).stat().st_size for n in ['question-index.json', 'source-manifest.json']),
        'catalog_sqlite_bytes': catalog.path.stat().st_size,
        'webp_cache_bytes': sum(p.stat().st_size for p in renderer.cache.glob('*.webp')),
        'exports': exports,
        'limits': ['Cold previews have no WebP cache; OS disk caches were not flushed.',
                   'First catalog construction differs from complete native App startup.',
                   'No legacy per-question Paper 4 PDFs exist for an equivalent paired storage comparison.',
                   'Original bitmap content and source reference appendices are retained; vector content is not forcibly rasterised.'],
    }
    write_json(output / 'benchmark.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    benchmark(args.snapshot, args.sources, args.output)
