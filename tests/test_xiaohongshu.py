"""小红书契约与归档测试：全部数据和媒体由测试生成。"""
from copy import deepcopy
import csv
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from playwright.sync_api import Error as BrowserError

from douyin_local import DownloadError
from douyin_local.albums import load_album
from douyin_local.compose import run_ffmpeg
from douyin_local.download import validate_video
from douyin_local.service import download_text
from douyin_local.sharing import extract_urls
from douyin_local.xhs_service import archive_note, process_xhs
from douyin_local.xiaohongshu import (XhsReader, access_error, canonical, check_url, identify,
                                     normalize_note, normalize_profile, note_urls, profile_entries)

AUTHOR = '600000000000000000000001'
FIRST = '600000000000000000000002'
SECOND = '600000000000000000000003'
OTHER = '600000000000000000000009'


def note_state(identity=FIRST, base='https://media.example.invalid', kind='normal'):
    return {'note': {'noteDetailMap': {identity: {'note': {
        'noteId': identity, 'type': kind, 'title': '生成笔记', 'desc': '两行正文\n测试记录',
        'user': {'userId': AUTHOR, 'nickname': '测试作者'}, 'time': 1700000000000,
        'tagList': None, 'interactInfo': {'likedCount': '1.2万'},
        'imageList': [{'urlDefault': base + '/image.png?fixture_signature=private'}],
        'video': {'media': {'stream': {'h264': [{'masterUrl': base + '/video.mp4?fixture_signature=private',
                                               'width': 160, 'height': 120, 'videoCodec': 'h264'}]}}}
    }}}}}


def profile_state():
    return {'user': {'userPageData': {'basicInfo': {'nickname': '测试作者', 'userId': AUTHOR, 'desc': '简介'},
                                    'interactions': [{'type': 'fans', 'count': '7.9万'}]},
                     'notes': [[{'id': FIRST, 'xsecToken': 'fixture-secret', 'noteCard': {
                         'displayTitle': '=formula', 'type': 'normal', 'user': {'userId': AUTHOR}}}]]}}


class ParserTests(unittest.TestCase):
    def test_mixed_share_input_and_strict_hosts(self):
        self.assertEqual(extract_urls('文案 https://v.douyin.com/a\\_b/ ' + canonical('profile', AUTHOR) +
                                     ' https://xhslink.cn/o/test https://example.com/'),
                         ['https://v.douyin.com/a_b/', canonical('profile', AUTHOR), 'https://xhslink.cn/o/test'])
        for url in ('https://www.xiaohongshu.com.evil.invalid/explore/' + FIRST,
                    'https://user@www.xiaohongshu.com/explore/' + FIRST,
                    'https://xhslink.cn:bad/a', 'file:///tmp/a'):
            with self.assertRaises(DownloadError):
                check_url(url)

    def test_routes_keep_access_context_only_in_memory(self):
        for route in ('explore/' + FIRST, 'discovery/item/' + FIRST, 'user/profile/' + AUTHOR + '/' + FIRST):
            target = identify('https://www.xiaohongshu.com/' + route + '?xsec_token=test&tracking=discard')
            self.assertEqual(target['id'], FIRST)
            self.assertEqual(target['kind'], 'note')
            self.assertIn('xsec_token=test', target['url'])
            self.assertNotIn('tracking', target['url'])
        self.assertIsNone(identify('https://xhslink.cn/o/a'))

    def test_exact_note_identity_and_missing_values(self):
        note = normalize_note(note_state(), FIRST)
        self.assertEqual(note['interactions']['likedCount'], '1.2万')
        self.assertIsNone(note['interactions']['commentCount'])
        self.assertEqual(note['tags'], [])
        self.assertEqual(note['audio_urls'], [])
        self.assertEqual(note['formats'][0]['vcodec'], 'h264')
        self.assertEqual(note['source_url'], canonical('note', FIRST))
        with self.assertRaises(DownloadError):
            normalize_note(note_state(), SECOND)
        for state in (None, [], {}, {'note': None}):
            with self.assertRaises(DownloadError):
                normalize_note(state, FIRST)
        self.assertEqual(note_urls(['file:///secret', 'http://[', 'https://user:secret@host/a']), [])

    def test_profile_refs_identity_and_unknown_stats(self):
        state = profile_state()
        state['user']['userPageData'] = {'__v_isRef': True, '_value': state['user']['userPageData']}
        profile = normalize_profile(state, AUTHOR)
        self.assertEqual(profile['followers'], '7.9万')
        self.assertIsNone(profile['following'])
        with self.assertRaises(DownloadError):
            normalize_profile(state, OTHER)
        state['user']['userPageData']['_value']['interactions'] = None
        self.assertIsNone(normalize_profile(state, AUTHOR)['followers'])

    def test_profile_cards_do_not_include_known_other_authors(self):
        items = profile_state()['user']['notes'][0]
        items += [{'id': SECOND, 'noteCard': {'user': {'userId': OTHER}}}, {'id': 'invalid'}]
        entries = profile_entries(items, AUTHOR)
        self.assertEqual([entry['id'] for entry in entries], [FIRST])
        self.assertIn('xsec_token=fixture-secret', entries[0]['url'])

    def test_restrictions_are_distinct_from_empty_profiles(self):
        self.assertIn('300012', access_error('https://www.xiaohongshu.com/website-login/error', '安全限制', '300012'))
        self.assertIn('要求登录', access_error('https://www.xiaohongshu.com/login', '', ''))
        self.assertIsNone(access_error(canonical('profile', AUTHOR), '正常', ''))
        with self.assertRaises(DownloadError):
            normalize_profile({}, AUTHOR)

    def test_browser_refuses_previous_page_and_other_note_author(self):
        reader = XhsReader()
        reader.page = MagicMock()
        reader.page.url = canonical('note', SECOND)
        with patch.object(reader, 'guard'), patch.object(reader, 'state', return_value=note_state()):
            with self.assertRaisesRegex(DownloadError, '旧页面'):
                reader.navigate(identify(canonical('note', FIRST)))
        with patch.object(reader, 'navigate', return_value=({'author_id': OTHER}, {})):
            with self.assertRaisesRegex(DownloadError, '作者'):
                reader.note(identify(canonical('note', FIRST)), AUTHOR)

    def test_transient_navigation_waits_for_final_access_error(self):
        reader = XhsReader()
        reader.page = MagicMock()
        with patch.object(reader, 'guard', side_effect=[BrowserError('context destroyed'),
                                                       DownloadError('安全限制（300012）')]):
            with self.assertRaisesRegex(DownloadError, '300012'):
                reader.navigate(identify(canonical('note', FIRST)))
        reader.page.wait_for_timeout.assert_called_once_with(300)


class SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = tempfile.TemporaryDirectory()
        root = Path(cls.media.name)
        run_ffmpeg(['-f', 'lavfi', '-i', 'testsrc2=s=160x120:r=30', '-f', 'lavfi', '-i', 'sine=frequency=440',
                    '-t', '0.4', '-c:v', 'libx264', '-c:a', 'aac', str(root / 'video.mp4')])
        run_ffmpeg(['-f', 'lavfi', '-i', 'color=c=blue:s=160x120', '-frames:v', '1', str(root / 'image.png')])
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
        self.temp = tempfile.TemporaryDirectory(prefix='xhs-测试-')
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name).resolve() / 'output'

    def note(self, identity=FIRST, kind='normal'):
        note = normalize_note(note_state(identity, f'http://127.0.0.1:{self.server.server_port}', kind), identity)
        note['headers'] = {}
        return note

    def check_private_urls_absent(self, folder):
        for path in folder.rglob('*'):
            if path.suffix in {'.json', '.txt', '.csv'}:
                content = path.read_text(encoding='utf-8-sig')
                self.assertNotIn('fixture-secret', content)
                self.assertNotIn('fixture_signature', content)
                self.assertNotIn('127.0.0.1', content)

    def test_video_cover_text_and_verified_mp4_share_one_folder(self):
        result = archive_note(self.note(kind='video'), self.output, log=lambda _: None)
        folder = Path(result['folder'])
        self.assertEqual(folder.parent, self.output)
        self.assertEqual(Path(result['path']).parent, folder)
        self.assertTrue(validate_video(Path(result['path']))['full_decode_verified'])
        self.assertTrue((folder / '封面.png').is_file())
        meta = json.loads((folder / '笔记信息.json').read_text(encoding='utf-8'))
        self.assertTrue(meta['media_complete'])
        self.assertEqual(result['record']['source_url'], canonical('note', FIRST))
        self.check_private_urls_absent(folder)

    def test_album_compose_and_repeated_fresh_folder(self):
        result = archive_note(self.note(), self.output, log=lambda _: None)
        repeated = archive_note(self.note(), self.output, make_video=False, log=lambda _: None)
        folder = Path(result['folder'])
        self.assertNotEqual(result['folder'], repeated['folder'])
        self.assertEqual(load_album(folder)['platform'], 'xiaohongshu')
        self.assertTrue(validate_video(Path(result['path']))['full_decode_verified'])
        self.assertIsNone(result['record']['audio_codec'])
        self.assertEqual(result['record']['duration_seconds'], 5)
        self.check_private_urls_absent(folder)

    def test_read_only_never_requests_media(self):
        with patch('douyin_local.xhs_service.save_video') as video, patch('douyin_local.xhs_service.save_album') as album:
            result = archive_note(self.note(), self.output, read_only=True, log=lambda _: None)
            video.assert_not_called()
            album.assert_not_called()
        folder = Path(result['folder'])
        self.assertEqual({path.name for path in folder.iterdir()}, {'笔记正文.txt', '笔记信息.json'})
        self.assertIsNone(result['record']['media_complete'])
        self.check_private_urls_absent(folder)

    def test_failure_keeps_text_without_success_metadata(self):
        with patch('douyin_local.xhs_service.save_album', side_effect=DownloadError('fixture media failed')):
            with self.assertRaises(DownloadError):
                archive_note(self.note(), self.output, log=lambda _: None)
        folder = next(self.output.iterdir())
        self.assertIn('两行正文', (folder / '笔记正文.txt').read_text(encoding='utf-8'))
        self.assertFalse(json.loads((folder / '笔记信息.json').read_text(encoding='utf-8'))['media_complete'])

    def reader(self):
        mock = MagicMock()
        entries = profile_entries(profile_state()['user']['notes'][0], AUTHOR)
        entries.append({'id': SECOND, 'url': canonical('note', SECOND), 'title': '第二篇', 'kind': 'normal'})
        mock.profile.return_value = (normalize_profile(profile_state(), AUTHOR), entries,
                                     {'limit': 2, 'collected': 2, 'has_more': None, 'complete': False})
        mock.note.side_effect = lambda target, **kwargs: self.note(target['id'])
        return mock

    def test_profile_download_nested_folders_and_safe_index(self):
        reader = self.reader()
        with patch('douyin_local.xhs_service.XhsReader') as factory:
            factory.return_value.__enter__.return_value = reader
            results = download_text(canonical('profile', AUTHOR), self.output, make_video=False,
                                    profile_limit=2, log=lambda _: None)
        self.assertTrue(results[0]['success'])
        folder = Path(results[0]['folder'])
        subfolders = [path for path in folder.iterdir() if path.is_dir()]
        self.assertEqual(len(subfolders), 2)
        self.assertEqual({load_album(path)['id'] for path in subfolders}, {FIRST, SECOND})
        with (folder / '笔记列表.csv').open(encoding='utf-8-sig', newline='') as source:
            rows = list(csv.reader(source))
        self.assertEqual(rows[1][1], "'=formula")
        self.assertFalse(results[0]['record']['scope']['complete'])
        reader.note.assert_called_with(identify(canonical('note', SECOND)), author_id=AUTHOR)
        self.check_private_urls_absent(folder)

    def test_profile_read_and_restriction_partial_report(self):
        reader = self.reader()
        with patch('douyin_local.xhs_service.XhsReader') as factory:
            factory.return_value.__enter__.return_value = reader
            result = process_xhs(canonical('profile', AUTHOR), self.output, read_only=True, log=lambda _: None)
            reader.note.assert_not_called()
            self.assertTrue(result['success'])
            reader.profile.return_value = deepcopy(self.reader().profile.return_value)
            reader.note.side_effect = DownloadError('小红书安全限制（300012）')
            failed = download_text(canonical('profile', AUTHOR), self.output, log=lambda _: None)[0]
        self.assertFalse(failed['success'])
        self.assertEqual(reader.note.call_count, 1)
        self.assertEqual(len(failed['record']['downloads']), 1)
        self.assertTrue((Path(failed['folder']) / '主页信息.json').is_file())
        self.check_private_urls_absent(Path(failed['folder']))


if __name__ == '__main__':
    unittest.main()
