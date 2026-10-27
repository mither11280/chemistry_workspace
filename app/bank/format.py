"""Library-independent JSON contract validation and PDF adapter geometry."""
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import List, TypedDict
import fitz
from jsonschema import Draft202012Validator

VERSION = '1.0.0'
COORDINATES = 'pdf-point-unrotated-cropbox-top-left-v1'

class Region(TypedDict):
    page_index: int
    bbox: List[float]

class Material(TypedDict):
    source_id: str
    regions: List[Region]

class DataError(ValueError):
    pass

class SourceError(DataError):
    pass

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(path)

def relative_path(value):
    p = PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or '\\' in value or ':' in value:
        raise DataError('必须使用无父目录跳转的 POSIX 相对路径')
    return p

def safe_path(root, relative):
    relative_path(relative)
    root = Path(root).resolve()
    result = (root/relative).resolve()
    if root not in result.parents:
        raise DataError('路径超出本地资料目录')
    return result

def validate_schema(data, schema_path):
    Draft202012Validator.check_schema(read_json(schema_path))
    errors = sorted(Draft202012Validator(read_json(schema_path)).iter_errors(data), key=lambda e:str(e.path))
    if errors:
        raise DataError(f'{list(errors[0].path)}: {errors[0].message}')

def validate(index, manifest, schemas):
    validate_schema(index, Path(schemas)/'question-index.schema.json')
    validate_schema(manifest, Path(schemas)/'source-manifest.schema.json')
    sources = {s['source_id']:s for s in manifest['sources']}
    if len(sources) != len(manifest['sources']):
        raise DataError('重复 source_id')
    ids = set()
    topics = {t['id'] for t in index['topics']}
    if len(topics) != len(index['topics']):raise DataError('重复 topic ID')
    paths = set()
    for s in sources.values():
        relative_path(s['path'])
        if s['path'] in paths:raise DataError('重复 source path')
        paths.add(s['path'])
        if len(s['pages']) != s['page_count']:raise DataError('页数与几何记录不一致')
        for n,p in enumerate(s['pages']):
            if p['page_index'] != n:raise DataError('页面几何必须从零连续编号')
            media,crop=p['media_box'],p['crop_box']
            if not (media[0]<=crop[0]<crop[2]<=media[2] and media[1]<=crop[1]<crop[3]<=media[3]):
                raise DataError('CropBox 超出 MediaBox')
            if abs(crop[2]-crop[0]-p['width'])>.02 or abs(crop[3]-crop[1]-p['height'])>.02:
                raise DataError('页面参考尺寸与 CropBox 不一致')
        for r in s['metadata'].get('references',[]):
            if not isinstance(r.get('page_index'),int) or not 0<=r['page_index']<s['page_count']:raise DataError('参考资料页码越界')
            p=s['pages'][r['page_index']];x0,y0,x1,y1=r['bbox']
            if not (0<=x0<x1<=p['width']+.01 and 0<=y0<y1<=p['height']+.01) or r.get('rotate',0) not in [0,90,180,270]:raise DataError('参考资料区域越界')
    for q in index['questions']:
        if q['question_id'] in ids:raise DataError('重复 question_id')
        ids.add(q['question_id'])
        if not set(q['topics'])<=topics:raise DataError('未知 topic')
        for kind in ['question','answer']:
            block=q[kind]
            if block['source_id'] not in sources:raise DataError('未知 source_id')
            source=sources[block['source_id']]
            identity=source['metadata']
            expected_role='qp' if kind=='question' else 'ms'
            if identity.get('role') in ['qp','ms'] and identity['role']!=expected_role:raise DataError('题目/答案来源类型不匹配')
            for key in ['exam_board','subject_code','year','session','paper','variant']:
                if key in identity and identity[key]!=q[key]:raise DataError('考试来源身份不匹配: '+key)
            for r in block['regions']:
                if r['page_index']>=source['page_count']:raise DataError('page_index 超出源文件')
                p=source['pages'][r['page_index']];x0,y0,x1,y1=r['bbox']
                if not all(math.isfinite(v) for v in r['bbox']) or not (0<=x0<x1<=p['width']+.01 and 0<=y0<y1<=p['height']+.01):
                    raise DataError(f"区域越界: {q['question_id']} {kind}")
    return True

def raw_box(page, name, default=None):
    """Read inherited native PDF box, including indirect arrays."""
    doc=page.parent; xref=page.xref
    for _ in range(100):
        typ,val=doc.xref_get_key(xref,name)
        if typ=='xref':val=doc.xref_object(int(val.split()[0]));typ='array'
        if typ=='array':
            numbers=[float(x) for x in re.findall(r'[-+]?(?:\d*\.\d+|\d+)',val)]
            if len(numbers)!=4:raise SourceError('非法 PDF 页面 box')
            return numbers
        typ,val=doc.xref_get_key(xref,'Parent')
        if typ!='xref':break
        xref=int(val.split()[0])
    if default is not None:return default
    raise SourceError('缺少 MediaBox')

def geometry(doc):
    pages=[]
    for i,p in enumerate(doc):
        typ,unit=doc.xref_get_key(p.xref,'UserUnit')
        if typ not in ['null'] and float(unit)!=1:raise SourceError('暂不支持非 1 UserUnit，请先校准规范化副本')
        media=raw_box(p,'MediaBox');crop=raw_box(p,'CropBox',media)
        # Effective CropBox is its intersection with MediaBox (PDF specification).
        crop=[max(crop[0],media[0]),max(crop[1],media[1]),min(crop[2],media[2]),min(crop[3],media[3])]
        pages.append({'page_index':i,'media_box':media,'crop_box':crop,'rotation':p.rotation,
                      'width':crop[2]-crop[0],'height':crop[3]-crop[1],'user_unit':1})
    return pages

def normalized_page(doc, page_index):
    page=doc[page_index]
    if page.rotation:page.set_rotation(0)  # in-memory view only; never save the source
    return page
