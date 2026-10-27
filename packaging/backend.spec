# PyInstaller COLLECT is onedir; BUNDLE gives the nested helper valid macOS code/resource placement.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata
root=Path(SPECPATH).parent
binaries=[];datas=[];hidden=[]
for package in ['pymupdf','PIL','jsonschema_specifications']:
    d,b,h=collect_all(package);datas+=d;binaries+=b;hidden+=h
for package in ['jsonschema','referencing','rpds-py','attrs','jsonschema-specifications']:
    datas+=copy_metadata(package)
a=Analysis([str(root/'packaging/backend_entry.py')],pathex=[str(root/'app')],binaries=binaries,datas=datas,
           hiddenimports=hidden+['PIL._webp','sqlite3','_sqlite3','jsonschema','referencing','rpds'],
           excludes=['tkinter','test','unittest','numpy','matplotlib','torch','IPython'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='QuestionBackend',console=True,debug=False,
        target_arch='arm64',codesign_identity=os.environ.get('CODESIGN_IDENTITY') or None,
        entitlements_file=str(root/'packaging/backend.entitlements.plist'))
collection=COLLECT(exe,a.binaries,a.datas,name='QuestionBackend')
app=BUNDLE(collection,name='QuestionBackend.app',bundle_identifier='com.mither.chemistry-workspace.backend',
           info_plist={'LSUIElement':True,'LSMinimumSystemVersion':'13.0','CFBundleShortVersionString':os.environ.get('APP_VERSION','0.2.0')})
