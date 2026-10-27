"""Collect exact dependency source archives and license texts for binary redistribution."""
import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import shutil
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
DEPENDENCIES=['PyMuPDF','Pillow','jsonschema','attrs','referencing','rpds-py','jsonschema-specifications','typing_extensions','PyInstaller']

def download(url,path,expected=None):
    if path.exists():
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if expected is None or digest==expected:return digest
    temp=path.with_suffix(path.suffix+'.part')
    with urllib.request.urlopen(url,timeout=120) as response,temp.open('wb') as target:shutil.copyfileobj(response,target)
    digest=hashlib.sha256(temp.read_bytes()).hexdigest()
    if expected and digest!=expected:raise ValueError('Upstream source SHA-256 mismatch: '+path.name)
    temp.replace(path);return digest

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--version',default='0.2.0');parser.add_argument('--output',type=Path,default=ROOT/'dist');parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();work=ROOT/'build/corresponding-source';work.mkdir(parents=True,exist_ok=True);records=[]
    for name in DEPENDENCIES:
        version=metadata.version(name)
        with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=60) as response:release=json.load(response)
        source=next(x for x in release['urls'] if x['packagetype']=='sdist')
        target=work/source['filename'];digest=download(source['url'],target,source['digests']['sha256'])
        records.append({'name':name,'version':version,'file':target.name,'url':source['url'],'sha256':digest})
        print('Verified source:',name,version,flush=True)
    # A PyMuPDF sdist may omit MuPDF entirely. Obtain the exact upstream version, never assume.
    pymupdf=next(r for r in records if r['name']=='PyMuPDF')
    with tarfile.open(work/pymupdf['file']) as archive:
        setup=archive.extractfile(next(m for m in archive.getmembers() if m.name.endswith('/setup.py'))).read().decode()
    version_mupdf=re.search(r"^version_mupdf = ['\"]([^'\"]+)['\"]",setup,re.M).group(1)
    import fitz
    if fitz.VersionFitz!=version_mupdf:raise ValueError('MuPDF source version differs from actual wheel runtime')
    mupdf=work/f'mupdf-{version_mupdf}-source.tar.gz';mupdf_url=f'https://mupdf.com/downloads/archive/{mupdf.name}'
    digest=download(mupdf_url,mupdf)
    with tarfile.open(mupdf) as archive:
        members=archive.getmembers()
        if not any('/source/fitz/' in m.name and m.name.endswith('.c') for m in members):raise ValueError('MuPDF archive lacks implementation source')
        copying=next(m for m in members if m.name.endswith('/COPYING'))
        agpl_text=archive.extractfile(copying).read()
        if b'GNU AFFERO GENERAL PUBLIC LICENSE' not in agpl_text:raise ValueError('Expected complete AGPL license in MuPDF source')
        (work/'AGPL-3.0.txt').write_bytes(agpl_text)
    records.append({'name':'MuPDF','version':version_mupdf,'file':mupdf.name,'url':mupdf_url,'sha256':digest})
    print('Verified full MuPDF implementation and AGPL license:',version_mupdf,flush=True)
    version=platform.python_version();python=work/f'Python-{version}.tar.xz'
    digest=download(f'https://www.python.org/ftp/python/{version}/Python-{version}.tar.xz',python)
    records.append({'name':'CPython','version':version,'file':python.name,'sha256':digest,'url':f'https://www.python.org/ftp/python/{version}/Python-{version}.tar.xz'})
    with tarfile.open(python) as archive:
        member=next(m for m in archive.getmembers() if m.name.endswith('/LICENSE'))
        (work/'PYTHON-LICENSE.txt').write_bytes(archive.extractfile(member).read())
    (work/'source-manifest.json').write_text(json.dumps(records,indent=2))
    if args.prepare_only:
        print('Exact dependency sources and full license texts are prepared.',flush=True);return
    app_source=args.output/f'ChemistryWorkspace-{args.version}-AppSource.tar.gz'
    if not app_source.exists():raise SystemExit('Build AppSource before collecting complete corresponding source')
    shutil.copyfile(app_source,work/app_source.name)
    (work/'source-manifest.json').write_text(json.dumps(records,indent=2))
    (work/'README.txt').write_text('Corresponding source for the matching Chemistry Workspace binary.\nApplication source, build scripts and dependency source archives are included.\nExact MuPDF source archive is included separately with its third-party source trees.\nCPython source is upstream for the recorded runtime version; its permissive PSF license is included.\nCambridge exam PDFs are separate data, not AGPL-licensed and not included in this source archive.\n')
    target=args.output/f'ChemistryWorkspace-{args.version}-CorrespondingSource.tar.gz'
    with tarfile.open(target,'w:gz') as archive:
        for p in sorted(work.iterdir()):
            if p.is_file() and not p.name.endswith('.part'):archive.add(p,arcname='CorrespondingSource/'+p.name)
    print('Complete corresponding source:',target,flush=True)
if __name__=='__main__':main()
