"""在已安装 requirements-build.txt 的 Windows 环境生成免安装 EXE。"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description='构建 Windows 单文件成品')
    parser.add_argument('--name', default='DouyinLocal', help='成品名称，不含 .exe；可与正在运行的旧版并存')
    args = parser.parse_args()
    if not args.name or any(char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for char in args.name):
        parser.error('--name 仅允许英文字母、数字、短横线和下划线')
    if sys.platform != 'win32':
        raise SystemExit('请在 Windows 上构建 Windows 发行包。')
    licenses = ROOT / 'build' / 'portable-licenses'
    licenses.mkdir(parents=True, exist_ok=True)
    versions = {}
    for name in ('yt-dlp', 'playwright', 'imageio-ffmpeg', 'greenlet', 'pyee', 'typing_extensions', 'pyinstaller'):
        dist = importlib.metadata.distribution(name)
        versions[name] = dist.version
        for item in dist.files or []:
            if '.dist-info/' in str(item).replace('\\', '/') and any(word in item.name.upper() for word in ('LICENSE', 'COPYING', 'NOTICE')):
                shutil.copyfile(dist.locate_file(item), licenses / (name + '-' + item.name))
    for name, source in [('Python-LICENSE.txt', Path(sys.base_prefix) / 'LICENSE.txt'),
                         ('Tcl-license.txt', Path(sys.base_prefix) / 'tcl' / 'tcl8.6' / 'license.terms'),
                         ('Tk-license.txt', Path(sys.base_prefix) / 'tcl' / 'tk8.6' / 'license.terms')]:
        if source.is_file():
            shutil.copyfile(source, licenses / name)
    shutil.copyfile(ROOT / 'THIRD_PARTY.md', licenses / 'THIRD_PARTY.md')
    shutil.copyfile(ROOT / 'LICENSE', licenses / 'DouyinLocal-MIT.txt')
    shutil.copyfile(ROOT / 'docs' / 'third-party' / 'FFmpeg-GPLv3.txt', licenses / 'FFmpeg-GPLv3.txt')
    (licenses / 'versions.json').write_text(json.dumps(versions, indent=2) + '\n', encoding='utf-8')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
               '--name', args.name, '--paths', str(ROOT / 'src'), '--specpath', str(ROOT / 'build'),
               '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build' / 'pyinstaller'),
               '--collect-all', 'playwright', '--collect-all', 'imageio_ffmpeg', '--collect-all', 'yt_dlp',
               '--add-data', f'{licenses};licenses', str(ROOT / 'scripts' / 'portable_entry.py')]
    subprocess.run(command, cwd=ROOT, check=True)
    target = ROOT / 'dist' / (args.name + '.exe')
    with target.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    report = {'file': target.name, 'version': version, 'bytes': target.stat().st_size, 'sha256': digest,
              'python': sys.version.split()[0], 'dependencies': versions}
    (target.parent / 'release.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (target.parent / '使用说明.txt').write_text(
        '抖音素材助手 · Windows 本地版\n\n'
        f'双击 {target.name} 即可运行，不需要安装 Python。可以把这个 EXE 单独复制到其他可写目录。\n'
        '联网下载：粘贴抖音分享文案或链接，可一次粘贴多条，再点开始下载。需要网络及本机 Edge/Chrome。\n'
        '默认保存在 EXE 旁的 downloads 文件夹，也可在窗口中选择保存位置。\n'
        '每条链接每次下载新建「时间戳_作者昵称」目录；视频、原图、原声、实况、合成版和记录全部放在其中。\n'
        '图文和实况会保存原图片、原声、实况片段，并默认生成带原声的完整 MP4。\n'
        '离线处理：选择含「作品信息.json」及完整素材的目录，生成播放版；也可校验已有 MP4。\n'
        '无网络时程序能够启动和处理已有素材；新的抖音内容必须联网才能获取。\n'
        '首次启动需解包内置组件，请等待数秒。请将 EXE 放在可写目录，或另选保存位置。\n'
        '本次为本机使用构建，未包含浏览器、用户视频、Cookie 或登录资料。\n', encoding='utf-8-sig')
    shutil.copytree(licenses, target.parent / 'third-party-licenses', dirs_exist_ok=True)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
