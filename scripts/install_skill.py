"""Install only this skill; never edits Codex config or existing skill contents."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

def install(destination):
    root = Path(__file__).resolve().parents[1]
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Destination already exists. Keep the existing install; choose a new destination for a staged update.')
    if destination.name != 'contextpilot':
        raise ValueError('Destination folder must be named contextpilot.')
    source = root / 'skills/contextpilot'
    destination.mkdir(parents=True)
    for p in source.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            target=destination/p.relative_to(source); target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,target)
    target = destination/'scripts/contextpilot'
    target.mkdir()
    for p in (root/'src/contextpilot').glob('*.py'):
        shutil.copyfile(p,target/p.name)
    manifest = {p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in destination.rglob('*') if p.is_file()}
    (destination/'installation.json').write_text(json.dumps({'version':'0.1.0','files':manifest},indent=2),encoding='utf-8')
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    home=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
    parser.add_argument('--destination',default=str(home/'skills/contextpilot'))
    args=parser.parse_args()
    try: print(install(args.destination))
    except (ValueError,OSError) as e: parser.exit(2,str(e)+'\n')
