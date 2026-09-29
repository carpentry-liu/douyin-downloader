"""小红书内容归档；精选元数据可离线阅读，媒体签名只留内存。"""
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from . import DownloadError
from .albums import download_asset, save_album
from .compose import compose_album
from .download import create_download_folder, save_video
from .xiaohongshu import XhsReader, canonical, identify, resolve


def write_json(path, data):
    # 所有路径位于本次新建目录，以 x 模式避免静默覆盖。
    with path.open('x', encoding='utf-8') as target:
        json.dump(data, target, ensure_ascii=False, indent=2)
        target.write('\n')


def archive_note(note, output, make_video=True, read_only=False, log=print):
    folder = create_download_folder(output, note.get('author'))
    log(f"本次笔记目录：{folder}")
    metadata = {key: note.get(key) for key in ('platform', 'id', 'title', 'description', 'author', 'author_id',
                                              'source_url', 'published_at', 'tags', 'interactions')}
    metadata['read_at'] = datetime.now(timezone.utc).isoformat()
    metadata['mode'] = 'read' if read_only else 'download'
    metadata['media_complete'] = None if read_only else False
    try:
        if read_only:
            return {'kind': 'xhs_note', 'path': str(folder / '笔记正文.txt'), 'folder': str(folder), 'record': metadata}
        if note['kind'] == 'video':
            if not note['formats']:
                raise DownloadError('小红书笔记没有可下载的视频地址；已保存读取到的正文。')
            info = {'id': note['id'], 'platform': 'xiaohongshu', 'title': note['title'], 'uploader': note.get('author'),
                    'webpage_url': note['source_url'], 'formats': note['formats'], 'http_headers': note['headers']}
            path, record = save_video(info, folder, 'xiaohongshu', log)
            if note['images']:
                metadata['cover'] = download_asset('image', '封面', note['images'][0]['urls'], folder, note['headers'])
        else:
            if not note['images']:
                raise DownloadError('小红书笔记没有可下载的图片；已保存读取到的正文。')
            _, record = save_album(note, folder, log, in_place=True)
            path = folder
            if make_video:
                path, record = compose_album(folder, folder, log)
        metadata['media_complete'] = True
        return {'kind': 'xhs_note', 'path': str(path), 'folder': str(folder), 'record': record}
    finally:
        # 媒体处理后写入，不影响素材下载器的空目录约束；失败也保留已读取正文。
        with (folder / '笔记正文.txt').open('x', encoding='utf-8') as target:
            target.write(f"{note['title']}\n作者：{note.get('author') or '未知作者'}\n{note['source_url']}\n\n{note.get('description') or ''}\n")
        write_json(folder / '笔记信息.json', metadata)


def csv_cell(value):
    value = '' if value is None else str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value


def process_xhs(url, output, make_video=True, log=print, profile_limit=20, read_only=False):
    if not 1 <= profile_limit <= 200:
        raise DownloadError('主页笔记上限应为 1 到 200。')
    log('正在识别小红书链接…')
    target = resolve(url)
    with XhsReader() as reader:
        if target['kind'] == 'note':
            return archive_note(reader.note(target), output, make_video, read_only, log)
        log(f'读取作者主页，最多 {profile_limit} 篇（含可能的置顶，不代表全部历史）…')
        profile, entries, scope = reader.profile(target, profile_limit)
        folder = create_download_folder(output, profile['author'])
        log(f"主页：{profile['author']}，本次读取 {len(entries)} 篇，目录：{folder}")
        public_entries = [{key: entry.get(key) for key in ('id', 'title', 'kind')} |
                          {'source_url': canonical('note', entry['id'])} for entry in entries]
        profile.update(read_at=datetime.now(timezone.utc).isoformat(), scope=scope, notes=public_entries)
        with (folder / '笔记列表.csv').open('x', encoding='utf-8-sig', newline='') as target_file:
            writer = csv.writer(target_file)
            writer.writerow(['笔记ID', '标题', '类型', '网页链接'])
            for entry in public_entries:
                writer.writerow([csv_cell(entry.get(key)) for key in ('id', 'title', 'kind', 'source_url')])
        with (folder / '主页摘要.txt').open('x', encoding='utf-8') as target_file:
            target_file.write(f"{profile['author']}\n{profile['source_url']}\n{profile.get('description') or ''}\n\n"
                              f"粉丝（页面显示）：{profile.get('followers') if profile.get('followers') is not None else '未返回'}\n"
                              f"本次读取 {len(entries)} 篇，上限 {profile_limit}，不代表全部历史。\n")
            for index, entry in enumerate(public_entries, 1):
                target_file.write(f"\n{index}. {entry['title']}\n{entry['source_url']}\n")
        results = []
        if not read_only:
            for index, entry in enumerate(entries, 1):
                log(f"主页笔记 {index}/{len(entries)}：{entry.get('title') or entry['id']}")
                try:
                    note = reader.note(identify(entry['url']), author_id=profile['id'])
                    result = archive_note(note, folder, make_video, False, log)
                    results.append({'id': entry['id'], 'success': True, 'folder': Path(result['folder']).name})
                except Exception as error:
                    message = str(error) if isinstance(error, DownloadError) else '笔记处理失败，请检查网络或本地保存目录。'
                    results.append({'id': entry['id'], 'success': False, 'error': message})
                    log(f'该篇未完成：{message}')
                    if isinstance(error, DownloadError) and any(word in message for word in ('300012', '安全限制', '要求登录')):
                        log('平台限制了后续访问，已停止本次主页下载。')
                        break
        good = sum(result['success'] for result in results)
        success = read_only or (bool(entries) and len(results) == len(entries) and good == len(entries))
        profile['downloads'] = results
        profile['mode'] = 'read' if read_only else 'download'
        profile['success'] = success
        write_json(folder / '主页信息.json', profile)
        message = f"主页列表已保存：读取 {len(entries)} 篇" if read_only else f"主页列表已保存，笔记下载成功 {good}/{len(entries)} 篇"
        log(message)
        return {'success': success, 'kind': 'xhs_profile', 'path': str(folder / '主页摘要.txt'), 'folder': str(folder),
                'message': message, 'record': profile}
