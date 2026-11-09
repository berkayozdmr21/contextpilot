import argparse
import json
import sys
from pathlib import Path
from . import __version__
from .engine import scan, rank, pack
from .logs import digest_log
from .memory import checkpoint, recall, snapshot, changes
from .report import html_report
from .safety import state_file

def emit_json(data):
    print(json.dumps(data,ensure_ascii=False,indent=2))

def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(prog='contextpilot', description='Local context preparation. No API key or quota modification.')
    parser.add_argument('--version',action='version',version=__version__)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('scan','search','pack','checkpoint','recall','snapshot','changes','report'):
        p=sub.add_parser(name)
        p.add_argument('--root',default='.',help='Repository root (default: current directory)')
        if name in ('search','pack'):
            p.add_argument('query')
        if name=='pack':
            p.add_argument('--max-chars',type=int,default=12000)
            p.add_argument('--max-files',type=int,default=8)
            p.add_argument('--json',action='store_true',help='Return context and report together')
        if name=='checkpoint':
            p.add_argument('--task',required=True)
            p.add_argument('--done',default='')
            p.add_argument('--next',dest='next_steps',required=True)
        if name=='report':
            p.add_argument('--html',help='Write a self-contained HTML report to this path')
    p=sub.add_parser('digest')
    p.add_argument('file',help='Log file path, or - for stdin')
    p.add_argument('--max-chars',type=int,default=6000)
    p.add_argument('--json',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.command=='digest':
            if args.file=='-':
                raw=sys.stdin.buffer.read(16_000_001)
            else:
                with open(args.file,'rb') as stream:
                    raw=stream.read(16_000_001)
            if len(raw)>16_000_000:
                raise ValueError('Log exceeds 16 MB; split it first.')
            text=raw.decode('utf-8-sig',errors='replace')
            output,report=digest_log(text,args.max_chars)
            if args.json: emit_json({'context':output,'report':report})
            else:
                print(output,end='')
                print(json.dumps(report),file=sys.stderr)
            return 0
        root=Path(args.root).resolve()
        if not root.is_dir():
            raise ValueError('Repository root is not a directory.')
        if args.command=='scan':
            data=scan(root); data['eligibleFiles']=len(data.pop('files')); emit_json(data)
        elif args.command=='search':
            emit_json(rank(scan(root),args.query)[:20])
        elif args.command=='pack':
            output,report=pack(root,args.query,args.max_chars,args.max_files)
            if args.json: emit_json({'context':output,'report':report})
            else:
                print(output,end='')
                print(json.dumps({k:v for k,v in report.items() if k!='selected'}),file=sys.stderr)
        elif args.command=='checkpoint': emit_json(checkpoint(root,args.task,args.done,args.next_steps))
        elif args.command=='recall': print(recall(root))
        elif args.command=='snapshot': emit_json(snapshot(root))
        elif args.command=='changes': emit_json(changes(root))
        elif args.command=='report':
            data=json.loads(state_file(root,'last-report.json').read_text(encoding='utf-8'))
            if args.html:
                target=Path(args.html)
                if target.exists(): raise ValueError('Report target already exists; choose a new filename.')
                target.write_text(html_report(data),encoding='utf-8')
                print(str(target.resolve()))
            else: emit_json(data)
        return 0
    except (OSError, ValueError, KeyError) as e:
        print('contextpilot: '+str(e),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
