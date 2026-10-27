"""Package existing audited coordinates as portable vector PDFs; never upgrade review status."""
import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def package(index, output):
    bank = copy.deepcopy(json.loads(index.read_text(encoding='utf-8')))
    source_root = index.parent / 'sources'
    output.mkdir(parents=True, exist_ok=True)
    # Preserve original source identities so existing CIE1 share codes remain compatible.
    for name, info in bank['sources'].items():
        source = source_root / name
        if digest(source) != info['sha256']:
            raise ValueError('Source hash mismatch: ' + name)
        target = output / 'sources' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        info.pop('original_path', None)
        info['path'] = 'sources/' + name
    topics = {t['id']: dict(t, question_ids=[]) for t in bank['topics']}
    documents = {}
    try:
        for q in bank['questions']:
            relative = Path(str(q['year']) + '-March') / ('Paper-' + str(q['paper'])) / ('Q%02d' % q['number'])
            folder = output / relative
            folder.mkdir(parents=True, exist_ok=True)
            q['files'] = {}
            q['file_sha256'] = {}
            for kind, source_key in [('question', 'qp'), ('answer', 'ms')]:
                name = q[source_key]
                if name not in documents:
                    documents[name] = fitz.open(source_root / name)
                source = documents[name]
                with fitz.open() as cut:
                    for r in q[kind + '_regions']:
                        clip = fitz.Rect(r['bbox'])
                        page = cut.new_page(width=clip.width, height=clip.height)
                        page.show_pdf_page(page.rect, source, r['page'] - 1, clip=clip)
                    cut.set_metadata({'title': q['id'] + ' ' + kind,
                                      'subject': 'Candidate crop - pending review; source: ' + name,
                                      'author': 'Original content: Cambridge / UCLES'})
                    target = folder / (kind + '.pdf')
                    cut.save(target, garbage=4, deflate=True, no_new_id=True)
                q['files'][kind] = (relative / target.name).as_posix()
                q['file_sha256'][kind] = digest(target)
            write_json(folder / 'metadata.json', q)
            for topic in q['topics']:
                topics[topic]['question_ids'].append(q['id'])
    finally:
        for document in documents.values():
            document.close()
    bank['distribution'] = {'format': 'portable-crops-v1', 'copyright': 'Exam and mark scheme content: Cambridge / UCLES. App source license does not license exam content.', 'classification': 'Keyword candidates; not independently verified.'}
    write_json(output / 'index.json', bank)
    write_json(output / 'topics.json', list(topics.values()))
    print(f"Packaged {len(bank['questions'])} questions and answers into {output}")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=ROOT / 'data/bank.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'question_bank/CIE/9701/AS')
    args = parser.parse_args()
    package(args.index.resolve(), args.output.resolve())

if __name__ == '__main__':
    main()
