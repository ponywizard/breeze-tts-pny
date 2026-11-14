#!/usr/bin/env python3
"""Rebuild a pinned game-mod release and publish its verified assets on GitHub."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'ponywizard/breeze-tts-pny'
API = 'https://api.github.com/repos/' + REPOSITORY
SDK_FILES = ('project.godot', 'world/modding/mod_loader.gd', 'world/modding/bundled_mods.gd',
             'tools/build/packs.gd', 'tools/modding/build_mod.gd')


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        redirected = super().redirect_request(request, fp, code, message, headers, url)
        if redirected and urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(request.full_url).netloc:
            redirected.remove_header('Authorization')
        return redirected


HTTP = urllib.request.build_opener(Redirects())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + '.pending')
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'breeze-tts-pny-release'})
        with HTTP.open(request, timeout=120) as response, temporary.open('wb') as output:
            shutil.copyfileobj(response, output)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def config():
    metadata = json.loads((ROOT / 'release/mod.json').read_text())
    manifest = json.loads((ROOT / 'mods/breeze_tts_pny/mod.json').read_text())
    if metadata['version'] != manifest['version'] or metadata['game_version'] != manifest['game_version']:
        raise ValueError('Release metadata differs from the mod manifest')
    if metadata['tag'] != 'mod-v' + manifest['version']:
        raise ValueError('Unexpected mod release tag')
    return metadata


def source_commit():
    commit = os.environ.get('GITHUB_SHA') or subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Expected an exact release source commit')
    return commit


def assets(metadata):
    folder = ROOT / 'dist' / metadata['tag']
    names = ['release-manifest.json', 'SHA256SUMS']
    for platform in ('linux-x86_64', 'windows-x86_64'):
        names.extend(f'breeze_tts_pny-{metadata["version"]}-{platform}' + suffix
                     for suffix in ('.pck', '.build.json'))
    return [folder / name for name in sorted(names)]


def prepare(metadata):
    work = ROOT / 'build/release-mod'
    upstream = metadata['upstream']
    source = work / 'source'
    for name in SDK_FILES:
        url = f'https://raw.githubusercontent.com/{upstream["repository"]}/{upstream["commit"]}/{name}'
        download(url, source / name)
    (source / 'upstream-source.json').write_text(json.dumps(
        {'tag': upstream['tag'], 'commit': upstream['commit']}, indent=2) + '\n')
    engine_info = metadata['engine']
    archive = work / 'godot.zip'
    if not archive.exists() or sha(archive) != engine_info['sha256']:
        download(engine_info['url'], archive)
    if sha(archive) != engine_info['sha256']:
        raise ValueError('Godot archive checksum mismatch')
    engine = work / engine_info['filename']
    with zipfile.ZipFile(archive) as bundle:
        engine.write_bytes(bundle.read(engine_info['filename']))
    engine.chmod(0o755)
    folder = ROOT / 'dist' / metadata['tag']
    folder.mkdir(parents=True, exist_ok=True)
    for platform in ('linux-x86_64', 'windows-x86_64'):
        subprocess.run([sys.executable, str(ROOT / 'scripts/build.py'), '--game-source', str(source),
                        '--engine', str(engine), '--platform', platform], cwd=ROOT, check=True)
        pack = ROOT / 'dist' / f'breeze_tts_pny-{metadata["version"]}-{platform}.pck'
        if sha(pack) != metadata['pack_sha256']:
            raise ValueError(f'{platform} pack differs from the validated candidate')
        for path in (pack, pack.with_suffix('.build.json')):
            shutil.copy2(path, folder / path.name)
    rows = {path.name: {'sha256': sha(path), 'bytes': path.stat().st_size}
            for path in assets(metadata) if path.suffix in ('.pck', '.json') and path.name != 'release-manifest.json'}
    receipt = {'schema': 1, 'version': metadata['version'], 'tag': metadata['tag'],
               'game_version': metadata['game_version'], 'source_commit': source_commit(),
               'upstream': upstream, 'files': rows,
               'validation': {'linux_official_release': True, 'forced_ponese_profiles': 23,
                              'wav_and_pcm': True, 'real_director_stock_and_watch_party': True,
                              'windows_playtested': False}}
    (folder / 'release-manifest.json').write_text(json.dumps(receipt, indent=2) + '\n')
    (folder / 'SHA256SUMS').write_text(''.join(f'{sha(path)}  {path.name}\n'
        for path in assets(metadata) if path.name != 'SHA256SUMS'))
    subprocess.run([sys.executable, str(ROOT / 'scripts/audit_release.py'),
                    *map(str, assets(metadata)), '--report', str(work / 'audit.json')], cwd=ROOT, check=True)
    print('Prepared verified release assets:', folder, flush=True)


def request(url, method='GET', *, payload=None, raw=None, content_type=None):
    if urllib.parse.urlsplit(url).hostname not in ('api.github.com', 'uploads.github.com'):
        raise ValueError('Release API request is outside GitHub')
    token = os.environ.get('GH_TOKEN')
    if not token:
        raise ValueError('Publishing requires GH_TOKEN; the release workflow supplies github.token')
    body = json.dumps(payload).encode() if payload is not None else raw
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'breeze-tts-pny-release'}
    if body is not None:
        headers['Content-Type'] = content_type or 'application/json'
    call = urllib.request.Request(url, headers=headers, data=body, method=method)
    with HTTP.open(call, timeout=120) as response:
        return json.load(response)


def verify_assets(release, paths):
    remote = {asset['name']: asset for asset in release['assets']}
    if set(remote) != {path.name for path in paths}:
        raise ValueError('Release asset inventory differs from the prepared files')
    for path in paths:
        asset = remote[path.name]
        if asset['size'] != path.stat().st_size or asset.get('digest') != 'sha256:' + sha(path):
            raise ValueError('Uploaded asset checksum mismatch: ' + path.name)


def publish(metadata):
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise ValueError('Publish from this repository release workflow')
    paths = assets(metadata)
    receipt = json.loads((paths[0].parent / 'release-manifest.json').read_text())
    commit = source_commit()
    if receipt['source_commit'] != commit:
        raise ValueError('Prepared assets belong to a different source commit')
    for platform in ('linux-x86_64', 'windows-x86_64'):
        path = paths[0].parent / f'breeze_tts_pny-{metadata["version"]}-{platform}.pck'
        if sha(path) != metadata['pack_sha256']:
            raise ValueError('Prepared pack differs from the validated candidate')
    existing = [release for release in request(API + '/releases?per_page=100')
                if release['tag_name'] == metadata['tag']]
    if len(existing) > 1:
        raise ValueError('Multiple releases use the intended tag')
    if existing:
        release = existing[0]
        if release['target_commitish'] != commit:
            raise ValueError('An existing release uses a different source commit')
        if not release['draft']:
            verify_assets(release, paths)
            print('Already published:', release['html_url'], flush=True)
            return
    else:
        release = request(API + '/releases', 'POST', payload={
            'tag_name': metadata['tag'], 'target_commitish': commit, 'name': metadata['name'],
            'body': metadata['notes'], 'draft': True, 'prerelease': False, 'make_latest': 'true'})
    upload = release['upload_url'].split('{', 1)[0]
    remote = {asset['name']: asset for asset in release['assets']}
    for path in paths:
        if path.name in remote:
            asset = remote[path.name]
            if asset['size'] != path.stat().st_size or asset.get('digest') != 'sha256:' + sha(path):
                raise ValueError('Existing draft contains different asset: ' + path.name)
            continue
        request(upload + '?' + urllib.parse.urlencode({'name': path.name}), 'POST',
                raw=path.read_bytes(), content_type='application/octet-stream')
        print('Uploaded:', path.name, flush=True)
    release = request(API + '/releases/' + str(release['id']))
    verify_assets(release, paths)
    release = request(API + '/releases/' + str(release['id']), 'PATCH', payload={
        'draft': False, 'prerelease': False, 'make_latest': 'true'})
    if release['draft']:
        raise ValueError('Release is still a draft')
    verify_assets(release, paths)
    tag = request(API + '/git/ref/tags/' + metadata['tag'])
    if tag['object']['type'] != 'commit' or tag['object']['sha'] != commit:
        raise ValueError('Published tag does not point to the release source commit')
    print('Published:', release['html_url'], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'publish'))
    args = parser.parse_args()
    metadata = config()
    (prepare if args.action == 'prepare' else publish)(metadata)


if __name__ == '__main__':
    main()
