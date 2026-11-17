"""Content-addressed downloads and bounded, regular-file-only bundles."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
import time
import urllib.request

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('JSON file too large: ' + str(path))
    return json.loads(path.read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def relative(root, name):
    if not isinstance(name, str) or '\\' in name or '\x00' in name:
        raise ValueError('Expected a relative bundle path')
    parts = PurePosixPath(name)
    if parts.is_absolute() or not parts.parts or any(p in ('.', '..') or ':' in p for p in parts.parts):
        raise ValueError('Unsafe bundle path: ' + name)
    root = Path(root).resolve()
    result = root.joinpath(*parts.parts)
    if not result.resolve().is_relative_to(root) or result.is_symlink():
        raise ValueError('Bundle path escapes its directory: ' + name)
    return result


def verify_files(root, inventory):
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError('Missing file inventory')
    for name, digest in inventory.items():
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid SHA-256 for ' + name)
        path = relative(root, name)
        if not path.is_file() or sha(path) != digest:
            raise ValueError('Missing or changed asset: ' + name)


def acquire(source, destination, digest, max_bytes=5 * 1024**3, *, progress=None, cancelled=None):
    """Copy or download atomically; never install an unverified partial file."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('A pinned SHA-256 is required')
    if destination.is_file():
        if progress: progress('verifying', 0, destination.stat().st_size)
        if sha(destination) == digest:
            if progress: progress('cached', destination.stat().st_size, destination.stat().st_size)
            return destination
    temporary = destination.with_name(destination.name + '.partial')
    try:
        if str(source).startswith('https://'):
            stream = OPENER.open(str(source), timeout=60)
        elif '://' in str(source):
            raise ValueError('Downloads require HTTPS')
        else:
            stream = Path(source).open('rb')
        size = getattr(stream, 'headers', {}).get('Content-Length')
        try: expected = int(size) if size is not None else os.fstat(stream.fileno()).st_size
        except (AttributeError, OSError, ValueError): expected = None
        total, next_report = 0, 0.0
        phase = 'downloading' if str(source).startswith('https://') else 'copying'
        with stream, temporary.open('wb') as output:
            while chunk := stream.read(1024 * 1024):
                if cancelled and cancelled.is_set():
                    raise InterruptedError('Download cancelled')
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError('Asset exceeds size limit')
                output.write(chunk)
                if progress and time.monotonic() >= next_report:
                    progress(phase, total, expected)
                    next_report = time.monotonic() + 1
        if progress: progress('verifying', total, total)
        if sha(temporary) != digest:
            raise ValueError('Asset checksum mismatch for ' + destination.name)
        if cancelled and cancelled.is_set():
            raise InterruptedError('Download cancelled')
        temporary.replace(destination)
        if progress: progress('ready', total, total)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def unpack(archive, destination, max_bytes=512 * 1024**2):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Bundle destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.unpack-', dir=destination.parent))
    try:
        with tarfile.open(archive, 'r:gz') as bundle:
            total, seen = 0, set()
            for index, member in enumerate(bundle):
                if index >= 4096 or not member.isfile():
                    raise ValueError('Only bounded regular-file bundles are supported')
                path = relative(staging, member.name)
                if member.name in seen:
                    raise ValueError('Duplicate bundle member')
                seen.add(member.name)
                total += member.size
                if total > max_bytes or member.size < 0:
                    raise ValueError('Bundle exceeds extraction limit')
                path.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, path.open('xb') as target:
                    shutil.copyfileobj(source, target)
                path.chmod(0o644)
        staging.rename(destination)
    finally:
        if staging.exists(): shutil.rmtree(staging)
