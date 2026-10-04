"""Fixed runner sent as command bytes to a controlled sandbox, never run on host."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def digest(path):
    with open(path, 'rb') as stream:
        result = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
        return result.hexdigest()


def unpack(path, target):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(
                name.startswith('/') or '\\' in name or '..' in Path(name).parts
                or (item.external_attr >> 16) & 0o170000 == 0o120000
                for name, item in zip(names, archive.infolist())):
            raise ValueError('Unsafe grading archive')
        archive.extractall(target)


def main():
    plan = json.loads(base64.b64decode(sys.argv[1]))
    root = Path(plan['remote'])
    hashes = {name: digest(root / name) for name in plan['inputs']}
    if hashes != plan['inputs']:
        raise ValueError('Grading input hash mismatch')
    # Identity and scoring occur in this execution, without environment setup.
    identity = {}
    for name, check in plan['identity_checks'].items():
        args = [part.format(**plan['environment_paths']) for part in check['argv']]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError('Environment identity check failed: ' + name)
        output = result.stdout.strip()
        if check.get('prefix'):
            if not output.startswith(check['prefix']):
                raise ValueError('Environment identity output invalid: ' + name)
            output = output[len(check['prefix']):].split()[0].rstrip(',)')
        identity[name] = output
    if identity != plan['identity']:
        raise ValueError('Environment identity mismatch')
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('CS_') and key not in ('PYTHONPATH', 'PYTHONHOME')}
    env['CS_SCORER_VERSION'] = plan['scorer_version']
    if plan['environment_paths'].get('lean_bin'):
        env['PATH'] = plan['environment_paths']['lean_bin'] + ':' + env.get('PATH', '')
    if plan['environment_paths'].get('project_root'):
        project = Path(plan['environment_paths']['project_root'])
        if any(digest(project / name) != value for name, value in plan['project_files'].items()):
            raise ValueError('Declared public project hash mismatch')
        env['CS_LEAN_PROJECT'] = str(project)
    with tempfile.TemporaryDirectory(prefix='cs-verified-score-') as folder:
        folder = Path(folder)
        scorer = folder / 'scorer'
        unpack(root / 'scorer.zip', scorer)
        if any(digest(scorer / name) != value
               for name, value in plan['scorer_files'].items() if not name.startswith('@')):
            raise ValueError('Scorer source hash mismatch')
        if plan['public_resource']:
            public = folder / 'public'
            unpack(root / 'public_resource.zip', public)
            env[plan['public_resource']['environment_variable']] = str(
                folder / plan['public_resource']['directory'])
        invoke = ('import runpy,sys;sys.path.insert(0,sys.argv[1]);'
                  'sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name="__main__")')
        result = subprocess.run([sys.executable, '-I', '-c', invoke, str(scorer), str(scorer / plan['entrypoint']),
                                 str(root / 'science_package.zip')],
                                env=env, capture_output=True, text=True,
                                timeout=plan['score_timeout'])
        if result.stderr:
            sys.stderr.write(result.stderr[-4000:])
        if result.returncode:
            raise ValueError('Fixed scorer failed with exit ' + str(result.returncode))
        science = json.loads(result.stdout)
        print(json.dumps({'schema_version': 1, 'inputs': hashes,
                          'environment_identity': identity, 'science': science},
                         ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
