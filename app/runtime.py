"""Read-only application resources and durable, version-independent user storage."""
from dataclasses import dataclass
import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys
from bank.format import read_json, write_json

APP_ID='com.mither.chemistry-workspace'
APP_FOLDER='ChemistryWorkspace'

@dataclass(frozen=True)
class RuntimePaths:
    resources: Path
    home: Path
    frozen: bool

    @classmethod
    def discover(cls):
        frozen=bool(getattr(sys,'frozen',False))
        resources=Path(os.environ.get('QUESTION_BANK_RESOURCES',os.environ.get('QUESTION_BANK_ROOT',Path(__file__).resolve().parents[1]))).resolve()
        if os.environ.get('QUESTION_BANK_HOME'):home=Path(os.environ['QUESTION_BANK_HOME']).expanduser().resolve()
        elif frozen:home=Path.home()/'Library/Application Support'/APP_FOLDER
        else:home=Path(os.environ.get('QUESTION_BANK_ROOT',resources)).resolve()
        return cls(resources,home,frozen)

    @property
    def build(self):
        path=self.resources/'build-info.json'
        return read_json(path) if path.exists() else {'version':'development','distribution':'development'}

    def prepare(self):
        from bank.teaching.generation import prepare
        prepare(self.home,self.resources)
        (self.home/'data').mkdir(parents=True,exist_ok=True)
        (self.home/'exports').mkdir(exist_ok=True)
        previous=self.home/'data/install-state.json'
        if previous.exists() and read_json(previous).get('version')!=self.build['version']:
            stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            backup=self.home/'data/backups'/('app-upgrade-'+stamp);backup.mkdir(parents=True)
            for db in (self.home/'data').glob('*.sqlite3'):
                with sqlite3.connect(db) as src,sqlite3.connect(backup/db.name) as dst:src.backup(dst)
            for path in (self.home/'data').glob('*.local.json'):
                (backup/path.name).write_bytes(path.read_bytes())
            write_json(backup/'previous-install.json',read_json(previous))
            return backup
        return None

    def mark_ready(self):
        write_json(self.home/'data/install-state.json',self.build)

    def seed_sources(self,store):
        """Copy immutable packaged exam assets once, never replace a user's file."""
        bundled=self.resources/'bundled-sources';new_ids=set();report=[]
        if bundled.exists():
            for source in store.catalog.manifest['sources']:
                candidate=bundled/source['filename']
                if not candidate.exists():continue
                target=self.home/source['path']
                if target.exists():continue
                try:
                    result=store.import_file(candidate,extract=False);new_ids.update(result['source_ids']);report.append(result)
                except ValueError as error:report.append({'filename':source['filename'],'error':str(error)})
        store.ensure_local_content()
        if report:write_json(self.home/'data/bundled-sources-report.json',report)
        return report
