"""成品验收：在独立目录、清理 Python/PATH 的子进程中验证实际 EXE。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from douyin_local.compose import run_ffmpeg
from douyin_local.download import sha256

ROOT = Path(__file__).resolve().parents[1]


def create_fixture(folder):
    folder.mkdir(parents=True)
    specs = [('01.png', 'image', ['-f', 'lavfi', '-i', 'color=c=blue:s=160x120', '-frames:v', '1']),
             ('02.png', 'image', ['-f', 'lavfi', '-i', 'color=c=green:s=160x120', '-frames:v', '1']),
             ('02_live.mp4', 'video', ['-f', 'lavfi', '-i', 'testsrc2=s=160x120:r=30', '-t', '0.4', '-c:v', 'libx264']),
             ('audio.mp3', 'audio', ['-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '2'])]
    files = []
    for name, kind, args in specs:
        path = folder / name
        run_ffmpeg([*args, str(path)])
        record = {'file': name, 'type': kind, 'bytes': path.stat().st_size, 'sha256': sha256(path)}
        if kind != 'audio':
            record.update(width=160, height=120)
        files.append(record)
    manifest = {'id': '1234567890123456789', 'author': 'generated-fixture', 'files': files}
    (folder / '作品信息.json').write_text(json.dumps(manifest), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='隔离目录验收，不依赖个人下载文件')
    parser.add_argument('--online-url', help='可选：用户自行提供的真实分享链接，联网验收')
    args = parser.parse_args()
    release = json.loads((ROOT / 'dist' / 'release.json').read_text(encoding='utf-8'))
    artifact = ROOT / 'dist' / release['file']
    with artifact.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != release['sha256']:
            raise RuntimeError('EXE does not match release.json')
    base = ROOT / '.local' / 'portable-acceptance'
    base.mkdir(parents=True, exist_ok=True)
    acceptance = Path(tempfile.mkdtemp(prefix=release['sha256'][:12] + '-', dir=base))
    standalone = acceptance / '便携程序'
    standalone.mkdir(parents=True, exist_ok=True)
    exe = standalone / 'DouyinLocal.exe'
    shutil.copyfile(artifact, exe)
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'IMAGEIO_FFMPEG_EXE', 'PLAYWRIGHT_NODEJS_PATH'):
        env.pop(key, None)
    system_root = os.environ['SystemRoot']
    env['PATH'] = str(Path(system_root) / 'System32') + ';' + system_root
    env['PYTHONNOUSERSITE'] = '1'
    reports = {}

    def run(name, args, expected=0):
        report = acceptance / (name + '.json')
        result = subprocess.run([str(exe), *args, '--report', str(report)], cwd=standalone, env=env,
                                timeout=360, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode != expected:
            raise RuntimeError(f'{name} exit={result.returncode}; inspect {report}')
        reports[name] = json.loads(report.read_text(encoding='utf-8'))
        if reports[name]['success'] != (expected == 0):
            raise RuntimeError(f'{name} unexpected result')
        print(f'{name}: PASS', flush=True)

    run('selftest', ['--self-test'])
    if not reports['selftest']['frozen'] or not reports['selftest']['ffmpeg_decode']:
        raise RuntimeError('The bundled runtime was not verified')
    fixture = acceptance / 'fixture'
    create_fixture(fixture)
    run('offline-compose', ['--compose', str(fixture),
                            '--offline', '--output', str(acceptance / 'offline-output')])
    run('offline-verify', ['--verify', reports['offline-compose']['path'], '--offline'])
    run('offline-download-rejected', ['--download', 'https://www.douyin.com/video/1234567890123456789', '--offline'], expected=1)
    run('offline-read-rejected', ['--read', 'https://www.xiaohongshu.com/explore/600000000000000000000001', '--offline'], expected=1)
    if args.online_url:
        run('online', ['--download', args.online_url, '--originals-only', '--output', str(acceptance / 'online-output')])
    (acceptance / 'summary.json').write_text(json.dumps({'success': True, 'checks': list(reports),
                                                       'exe': str(exe), 'cwd': str(standalone), 'path': env['PATH']},
                                                      ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
