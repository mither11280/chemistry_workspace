"""Conservative duplicate detection for PDF saves with different bytes.

Hash identity is never replaced: equivalence only chooses one source for a new
exam identity. Every page must have identical unrotated boxes, decoded text+positions
and rendered RGB pixels. A failing/unsupported case remains a version conflict.
"""
import hashlib,json
from pathlib import Path
import fitz
from ..format import geometry,normalized_page,read_json,write_json

VERSION='pdf-unrotated-rgb72-words-boxes-v2'

def fingerprint(path,source_hash,cache):
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True);target=cache/(source_hash+'.json')
    if target.exists():
        saved=read_json(target)
        if saved['version']==VERSION:return saved['fingerprint']
    digest=hashlib.sha256(VERSION.encode())
    with fitz.open(path) as doc:
        # /Rotate affects display only; source hashes and native geometry stay distinct.
        boxes=[{k:v for k,v in page.items() if k!='rotation'} for page in geometry(doc)]
        digest.update(json.dumps(boxes,sort_keys=True).encode())
        for pi in range(len(doc)):
            p=normalized_page(doc,pi);ws=p.get_text('words')
            text=[[*[round(float(v),3) for v in w[:4]],w[4]] for w in ws]
            digest.update(json.dumps(text,ensure_ascii=False).encode())
            pix=p.get_pixmap(matrix=fitz.Matrix(1,1),colorspace=fitz.csRGB,alpha=False,annots=True)
            digest.update(str((pix.width,pix.height)).encode());digest.update(pix.samples)
    value=digest.hexdigest();write_json(target,{'version':VERSION,'fingerprint':value});return value
