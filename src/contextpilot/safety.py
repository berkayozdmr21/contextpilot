"""Conservative discovery boundaries; content remains untrusted project data."""
import fnmatch
import os
import re
import stat
import subprocess
from pathlib import Path

SKIP_DIRS = {'.git', '.contextpilot', '.tools', '.venv', 'venv', 'node_modules',
             'vendor', '__pycache__', 'bin', 'obj', 'dist', 'build', 'coverage', '.next'}
EXTENSIONS = {'.py', '.js', '.jsx', '.ts', '.tsx', '.cs', '.go', '.rs', '.java',
              '.kt', '.dart', '.php', '.rb', '.c', '.cpp', '.h', '.html', '.css',
              '.scss', '.sql', '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.sh', '.ps1'}
PRIVATE = re.compile(r'(?i)(^|[._-])(secret|credentials?|passwords?|tokens?)([._-]|$)')
SECRETS = [
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?(?:-----END [^-]+-----|$)'),
    re.compile(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b'),
    re.compile(r'(?im)((?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[\x22\x27]?)[^\s\x22\x27,;]{6,}'),
    re.compile(r'(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]{12,}'),
]

def redact(text):
    for pattern in SECRETS:
        text = pattern.sub(lambda m: (m.group(1) if m.lastindex else '') + '[REDACTED]' + '\n' * m.group(0).count('\n'), text)
    return text

def rules(root):
    p = root / '.contextpilotignore'
    if p.is_symlink() or not p.is_file():
        return []
    return [s.strip() for s in p.read_text(encoding='utf-8').splitlines()
            if s.strip() and not s.lstrip().startswith('#')]

def allowed(relative, ignores):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or any(s in SKIP_DIRS for s in p.parts):
        return False
    name = p.name.lower()
    if name.startswith('.env') or PRIVATE.search(name) or name.endswith(('.pem', '.key', '.pfx', '.lock')):
        return False
    if name in {'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'poetry.lock'}:
        return False
    if p.suffix.lower() not in EXTENSIONS and name not in {'dockerfile', 'makefile', 'license'}:
        return False
    return not any(fnmatch.fnmatchcase(relative, r) or fnmatch.fnmatchcase('/' + relative, r)
                   or any(fnmatch.fnmatchcase(part, r.rstrip('/')) for part in p.parts)
                   for r in ignores)

def safe_file(root, relative):
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        return None
    p = root / relative
    current = root
    for part in Path(relative).parts:
        current = current / part
        try:
            attrs=getattr(current.lstat(),'st_file_attributes',0)
            if current.is_symlink() or attrs & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024):
                return None
        except OSError:
            return None
    try:
        p.resolve().relative_to(root.resolve())
        return p if p.is_file() else None
    except (OSError, ValueError):
        return None

def discover(root, max_files=5000):
    ignores = rules(root)
    try:
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
        if result.returncode:
            raise OSError('Not a Git worktree')
        paths = sorted(set(result.stdout.decode('utf-8').split('\0')) - {''})
        mode = 'git'
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        paths = []
        for directory, folders, files in os.walk(root, followlinks=False):
            folders[:] = sorted(d for d in folders if d not in SKIP_DIRS and not (Path(directory) / d).is_symlink())
            for name in sorted(files):
                paths.append((Path(directory) / name).relative_to(root).as_posix())
                if len(paths) > max_files * 10:
                    raise ValueError('Directory scan too large. Use a narrower repository root.')
        mode = 'filesystem'
    selected = [p for p in paths if allowed(p, ignores) and safe_file(root, p)]
    return selected[:max_files], mode, len(selected) > max_files

def state_dir(root):
    p = root / '.contextpilot'
    if p.is_symlink() or (p.exists() and not p.is_dir()):
        raise ValueError('.contextpilot must be a real local directory.')
    p.mkdir(exist_ok=True)
    ignore = p / '.gitignore'
    if ignore.is_symlink():
        raise ValueError('Unsafe cache ignore file.')
    if not ignore.exists():
        ignore.write_text('*\n', encoding='utf-8')
    return p

def state_file(root, name):
    p = state_dir(root) / name
    if p.is_symlink():
        raise ValueError('Unsafe state file.')
    return p
