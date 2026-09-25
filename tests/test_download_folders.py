"""每次下载独立目录，覆盖实际传输、合成及所有下载入口。"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from douyin_local import DownloadError
from douyin_local.albums import load_album
from douyin_local.cli import main as cli_main
from douyin_local.compose import run_ffmpeg
from douyin_local.download import create_download_folder, sha256, validate_video
from douyin_local.resolver import item_to_info
from douyin_local.service import download_one, download_text

VIDEO = '7000000000000000001'
ALBUM = '7000000000000000002'
FIXED_TIME = datetime(2026, 9, 25, 15, 30, 8)


class SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class DownloadFolderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = tempfile.TemporaryDirectory()
        root = Path(cls.media.name)
        run_ffmpeg(['-f', 'lavfi', '-i', 'testsrc2=s=160x120:r=30', '-f', 'lavfi', '-i',
                    'sine=frequency=440', '-t', '0.4', '-c:v', 'libx264', '-c:a', 'aac', str(root / 'video.mp4')])
        run_ffmpeg(['-f', 'lavfi', '-i', 'color=c=blue:s=160x120', '-frames:v', '1', str(root / 'image.png')])
        run_ffmpeg(['-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '0.8', str(root / 'audio.mp3')])
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SilentHandler, directory=str(root)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.media.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='douyin-folders-中文-')
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name).resolve() / 'downloads'
        clock = patch('douyin_local.download.datetime', wraps=datetime)
        clock.start().now.return_value = FIXED_TIME
        self.addCleanup(clock.stop)

    def post(self, post_id, _route='video'):
        url = f'http://127.0.0.1:{self.server.server_port}'
        video = {'duration': 400, 'play_addr': {'url_list': [url + '/video.mp4'], 'width': 160, 'height': 120,
                                              'data_size': (Path(self.media.name) / 'video.mp4').stat().st_size}}
        return {'id': post_id, 'kind': 'video' if post_id == VIDEO else 'album', 'author': '测试作者',
                'title': '生成夹具', 'video': video, 'headers': {},
                'source_url': f'https://www.douyin.com/note/{post_id}', 'audio_urls': [url + '/audio.mp3'],
                'images': [{'index': 1, 'urls': [url + '/image.png'], 'video': video}]}

    def test_batch_and_repeat_put_all_files_in_fresh_per_link_folders(self):
        urls = f'https://www.douyin.com/video/{VIDEO} https://www.douyin.com/note/{ALBUM}'
        self.output.mkdir()
        legacy = self.output / f'{VIDEO}_旧记录.json'
        legacy.write_text('old local record', encoding='utf-8')
        with patch('douyin_local.service.read_post', side_effect=self.post):
            results = download_text(urls, self.output, log=lambda _: None)
            repeated = download_one(f'https://www.douyin.com/video/{VIDEO}', self.output, log=lambda _: None)
        self.assertTrue(all(item['success'] for item in results))
        folders = [Path(item['folder']) for item in [*results, repeated]]
        self.assertEqual([folder.name for folder in folders], ['2026-09-25_15-30-08_测试作者',
                         '2026-09-25_15-30-08_测试作者_2', '2026-09-25_15-30-08_测试作者_3'])
        for item, folder in zip([*results, repeated], folders):
            self.assertEqual(folder.parent, self.output)
            self.assertEqual(Path(item['path']).parent, folder)
            self.assertTrue(validate_video(Path(item['path']))['full_decode_verified'])
            self.assertTrue(all(path.is_file() for path in folder.iterdir()))
        self.assertEqual(len(list(folders[0].iterdir())), 2)
        album = load_album(folders[1])
        self.assertEqual({item['type'] for item in album['files']}, {'image', 'video', 'audio'})
        expected = {item['file'] for item in album['files']} | {'作品信息.json', Path(results[1]['path']).name,
                    Path(results[1]['path']).with_suffix('.json').name}
        self.assertEqual({path.name for path in folders[1].iterdir()}, expected)
        self.assertTrue(results[1]['record']['full_background_audio_used'])
        self.assertEqual(legacy.read_text(encoding='utf-8'), 'old local record')
        self.assertEqual(set(self.output.iterdir()), {legacy, *folders})

    def test_originals_only_can_be_repeated_without_reusing_old_album(self):
        with patch('douyin_local.service.read_post', side_effect=self.post):
            first = download_one(f'https://www.douyin.com/note/{ALBUM}', self.output, False, lambda _: None)
            second = download_one(f'https://www.douyin.com/note/{ALBUM}', self.output, False, lambda _: None)
        self.assertNotEqual(first['folder'], second['folder'])
        for result in (first, second):
            folder = Path(result['folder'])
            self.assertEqual(result['path'], str(folder))
            self.assertEqual(len(list(folder.iterdir())), 4)
            self.assertEqual(load_album(folder)['id'], ALBUM)

    def test_legacy_cli_downloads_create_folders_but_info_does_not(self):
        post = self.post(VIDEO)
        info = item_to_info({'aweme_id': VIDEO, 'author': {'nickname': post['author']},
                             'desc': post['title'], 'video': post['video']}, VIDEO)
        args = [f'https://www.douyin.com/video/{VIDEO}', '--output', str(self.output)]
        with patch('douyin_local.cli.resolve_info', return_value=(info, 'test')), redirect_stdout(StringIO()):
            self.assertEqual(cli_main([*args, '--info']), 0)
            self.assertFalse(self.output.exists())
            self.assertEqual(cli_main(args), 0)
            self.assertEqual(cli_main(args), 0)
        folders = list(self.output.iterdir())
        self.assertEqual(len(folders), 2)
        for folder in folders:
            self.assertTrue(folder.is_dir())
            self.assertEqual(len(list(folder.glob('*.mp4'))), 1)
            record_path = next(folder.glob('*.json'))
            record = json.loads(record_path.read_text(encoding='utf-8'))
            self.assertEqual(record['sha256'], sha256(folder / record['file']))

    def test_safe_names_missing_author_and_concurrent_collisions(self):
        for author in (None, '  ', '../a:b/c?*', 'CON', '长' * 200):
            folder = create_download_folder(self.output, author)
            self.assertEqual(folder.parent, self.output)
            self.assertNotRegex(folder.name, r'[<>:"/\\|?*]')
            self.assertLessEqual(len(folder.name), 55)
        self.assertTrue((self.output / '2026-09-25_15-30-08_未知作者').is_dir())
        collision = self.output / '2026-09-25_15-30-08_并发作者'
        collision.write_text('existing file', encoding='utf-8')
        with ThreadPoolExecutor(max_workers=4) as pool:
            folders = list(pool.map(lambda _: create_download_folder(self.output, '并发作者'), range(12)))
        self.assertEqual(len(set(folders)), 12)
        self.assertTrue(all(folder.is_dir() for folder in folders))
        self.assertEqual(collision.read_text(encoding='utf-8'), 'existing file')

    def test_failed_parse_does_not_create_an_unknown_success_directory(self):
        with patch('douyin_local.service.read_post', side_effect=DownloadError('fixture unavailable')):
            results = download_text(f'https://www.douyin.com/video/{VIDEO}', self.output, log=lambda _: None)
        self.assertFalse(results[0]['success'])
        self.assertFalse(self.output.exists())

    def test_failed_composition_keeps_all_originals_in_its_own_folder(self):
        with patch('douyin_local.service.read_post', side_effect=self.post), \
                patch('douyin_local.service.compose_album', side_effect=DownloadError('fixture composition failed')):
            results = download_text(f'https://www.douyin.com/note/{ALBUM}', self.output, log=lambda _: None)
        self.assertFalse(results[0]['success'])
        folders = list(self.output.iterdir())
        self.assertEqual(len(folders), 1)
        self.assertEqual(load_album(folders[0])['id'], ALBUM)
        self.assertEqual(len(list(folders[0].iterdir())), 4)
