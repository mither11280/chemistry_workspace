"""Reject runtime dependencies outside the bundle or Apple system locations."""
import argparse
import json
from pathlib import Path
import plistlib
import re
import subprocess

MAGIC={b'\xcf\xfa\xed\xfe',b'\xce\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca'}

def audit(app):
    app=Path(app).resolve();issues=[];binaries=[]
    info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
    declared=tuple(int(n) for n in info['LSMinimumSystemVersion'].split('.'))
    for path in app.rglob('*'):
        if path.is_symlink():
            resolved=path.resolve()
            if app not in resolved.parents and resolved!=app:issues.append('External symlink: '+str(path))
            continue
        if not path.is_file():continue
        with path.open('rb') as stream:magic=stream.read(4)
        if magic not in MAGIC:continue
        text=subprocess.check_output(['/usr/bin/otool','-L',str(path)],text=True)
        deps=[]
        for line in text.splitlines()[1:]:
            dep=line.strip().split(' (compatibility')[0];deps.append(dep)
            if dep.startswith('/') and not dep.startswith(('/System/Library/','/usr/lib/')):issues.append('External library: '+dep)
        arch=subprocess.check_output(['/usr/bin/lipo','-archs',str(path)],text=True).strip()
        if 'arm64' not in arch.split():issues.append('Missing arm64: '+str(path))
        loads=subprocess.check_output(['/usr/bin/otool','-l',str(path)],text=True)
        for version in re.findall(r'\bminos (\d+(?:\.\d+)+)',loads):
            if tuple(map(int,version.split('.'))) > declared:issues.append('Deployment target exceeds declared minimum: '+str(path)+' '+version)
        # Absolute rpaths into the developer environment would defeat an otherwise self-contained bundle.
        for rpath in re.findall(r'\n\s*path (\S+) \(offset',loads):
            if rpath.startswith('/') and not rpath.startswith(('/System/Library/','/usr/lib/')):issues.append('External rpath: '+rpath)
        binaries.append({'path':str(path.relative_to(app)),'architectures':arch,'libraries':deps})
    return {'app':app.name,'minimum_macos':info['LSMinimumSystemVersion'],'mach_o_count':len(binaries),'binaries':binaries,'issues':issues}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('app',type=Path);parser.add_argument('--report',type=Path)
    args=parser.parse_args();result=audit(args.app)
    if args.report:args.report.write_text(json.dumps(result,indent=2))
    print(json.dumps({'mach_o_count':result['mach_o_count'],'issues':result['issues']},indent=2))
    if result['issues']:raise SystemExit(1)
if __name__=='__main__':main()
