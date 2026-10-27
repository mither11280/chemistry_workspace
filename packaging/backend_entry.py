"""Frozen helper entry: argv establishes resource/user roots before importing the server."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--resources',type=Path,required=True)
    parser.add_argument('--user-root',type=Path)
    parser.add_argument('--instance-id',default='')
    parser.add_argument('--parent-pid',type=int)
    parser.add_argument('--runtime-info',action='store_true')
    args=parser.parse_args()
    if args.runtime_info:
        import fitz,PIL,sqlite3
        from PIL import features
        print(json.dumps({'frozen':getattr(sys,'frozen',False),'executable':sys.executable,'prefix':sys.prefix,'python':sys.version,'pymupdf':fitz.VersionBind,'pillow':PIL.__version__,'webp':features.check('webp'),'sqlite':sqlite3.sqlite_version,'sys_path':sys.path}));return
    os.environ['QUESTION_BANK_RESOURCES']=str(args.resources.resolve())
    if args.user_root:os.environ['QUESTION_BANK_HOME']=str(args.user_root.expanduser().resolve())
    os.environ['QUESTION_BANK_INSTANCE']=args.instance_id
    if args.parent_pid:
        def watch_parent():
            while True:
                time.sleep(1)
                try:os.kill(args.parent_pid,0)
                except ProcessLookupError:os.kill(os.getpid(),signal.SIGTERM);return
                if os.getppid()!=args.parent_pid:os.kill(os.getpid(),signal.SIGTERM);return
        threading.Thread(target=watch_parent,daemon=True).start()
    import server
    server.main()
if __name__=='__main__':main()
