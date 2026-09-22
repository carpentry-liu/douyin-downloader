import json
from pathlib import Path
import socket
import tempfile
import unittest
from urllib.parse import quote
from unittest.mock import patch

from douyin_local import DownloadError
from douyin_local.albums import load_album, local_file, extension_for
from douyin_local.compose import compose_album, run_ffmpeg
from douyin_local.download import sha256, validate_video
from douyin_local.posts import extract_urls, identify, parse_flight, normalize_post
from douyin_local.selftest import block_network
from douyin_local.service import default_output

POST = "1234567890123456789"


class PostTests(unittest.TestCase):
    def test_multiple_share_links_and_note_routes(self):
        self.assertEqual(extract_urls('分享 [https://v.douyin.com/a\\_b/](https://v.douyin.com/a_b/) https://v.douyin.com/c/ https://example.com/a'),
                         ['https://v.douyin.com/a_b/', 'https://v.douyin.com/c/'])
        self.assertEqual(identify(f'https://www.douyin.com/note/{POST}'), (POST, 'note'))
        self.assertEqual(identify(f'https://www.iesdouyin.com/share/slides/{POST}/'), (POST, 'note'))

    def test_flight_encoded_raw_exact_identity(self):
        target = {'awemeId': POST, 'images': [{'urlList': ['https://example.com/i.jpg']}]}
        payload = {'recommend': {'awemeId': '9999999999999999999', 'video': {}}, 'item': target}
        for chunk in (quote(json.dumps(payload)), '7:' + json.dumps(['$', payload]) + '\n'):
            document = '<script>self.__pace_f.push(' + json.dumps([1, chunk]) + ')</script>'
            self.assertEqual(parse_flight(document, POST), target)
            self.assertIsNone(parse_flight(document, '8888888888888888888'))
        self.assertIsNone(parse_flight('self.__pace_f.push(executeCode())', POST))

    def test_album_music_is_not_independent_video_and_live_is_retained(self):
        post = normalize_post({'awemeId': POST, 'authorInfo': {'nickname': 'fixture'},
                              'video': {'playAddr': [{'src': 'https://example.com/music.mp3'}]},
                              'music': {'playUrl': {'urlList': ['https://example.com/music.mp3']}},
                              'images': [{'urlList': ['https://example.com/i.jpg'], 'width': 81, 'height': 61,
                                          'video': {'playAddr': [{'src': 'https://example.com/live.mp4'}], 'duration': 3000}}]}, POST)
        self.assertEqual(post['kind'], 'album')
        self.assertEqual(post['author'], 'fixture')
        self.assertEqual(post['images'][0]['video']['duration'], 3000)
        self.assertEqual(post['audio_urls'], ['https://example.com/music.mp3'])
        with self.assertRaises(DownloadError):
            normalize_post({'awemeId': 'other', 'video': {}}, POST)

    def test_media_magic_rejects_error_html(self):
        with self.assertRaises(DownloadError):
            extension_for(b'<html>error</html>', 'image')
        self.assertEqual(extension_for(b'RIFF0000WEBP', 'image'), '.webp')

    def test_frozen_default_is_beside_executable(self):
        with patch('sys.frozen', True, create=True), patch('sys.executable', str(Path('portable/app.exe').resolve())):
            self.assertEqual(default_output(), Path('portable/downloads').resolve())


class OfflineTests(unittest.TestCase):
    def test_malformed_manifest_reports_actionable_error(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for value in ([], None, {'id': POST, 'files': [None]}, {'id': POST, 'files': [{'type': 'playlist'}]}):
                (folder / '作品信息.json').write_text(json.dumps(value), encoding='utf-8')
                with self.assertRaisesRegex(DownloadError, '作品信息.json'):
                    load_album(folder)

    def test_external_network_blocked_and_restored(self):
        original = socket.socket.connect
        with block_network():
            with self.assertRaises(OSError):
                socket.getaddrinfo('www.douyin.com', 443)
            with self.assertRaises(OSError):
                socket.create_connection(('127.0.0.1', 8888))
            with socket.socket() as sock:
                with self.assertRaises(OSError):
                    sock.connect(('8.8.8.8', 443))
            # Windows asyncio 的本机 socketpair 必须可用。
            first, second = socket.socketpair()
            first.close()
            second.close()
        self.assertIs(socket.socket.connect, original)

    def test_manifest_rejects_escape_and_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for name in ('../outside', 'C:\\outside', 'a/../../outside', 'x:stream'):
                with self.assertRaises(DownloadError):
                    local_file(folder, name)
            (folder / '01.jpg').write_bytes(b'fixture')
            manifest = {'id': POST, 'files': [{'file': '01.jpg', 'bytes': 7, 'sha256': 'wrong'}]}
            (folder / '作品信息.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaises(DownloadError):
                load_album(folder)

    def test_mixed_live_and_still_compose_offline_preserves_originals(self):
        with tempfile.TemporaryDirectory(prefix="douyin-fixture-'中文-") as temp:
            root = Path(temp)
            folder = root / 'album'
            folder.mkdir()
            run_ffmpeg(['-f', 'lavfi', '-i', 'color=c=red:s=82x62,format=rgb24,crop=81:61', '-frames:v', '1', str(folder / '01.png')])
            run_ffmpeg(['-f', 'lavfi', '-i', 'color=c=green:s=80x60', '-frames:v', '1', str(folder / '02.png')])
            run_ffmpeg(['-f', 'lavfi', '-i', 'testsrc2=s=80x60:r=30', '-t', '0.3', '-c:v', 'libx264', str(folder / '02_实况.mp4')])
            run_ffmpeg(['-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '0.8', str(folder / '原声.mp3')])
            files = []
            for name, kind, width, height in [('01.png', 'image', 81, 61), ('02.png', 'image', 80, 60),
                                               ('02_实况.mp4', 'video', 80, 60), ('原声.mp3', 'audio', None, None)]:
                path = folder / name
                files.append({'file': name, 'type': kind, 'width': width, 'height': height,
                              'bytes': path.stat().st_size, 'sha256': sha256(path)})
            manifest = {'id': POST, 'author': 'fixture', 'files': files}
            (folder / '作品信息.json').write_text(json.dumps(manifest), encoding='utf-8')
            with block_network():
                path, record = compose_album(folder, root / 'out', log=lambda _: None)
                self.assertEqual((record['width'], record['height']), (82, 62))
                self.assertEqual(record['media_order'], ['01.png', '02_实况.mp4'])
                self.assertTrue(record['full_background_audio_used'])
                self.assertEqual(record['audio_codec'], 'aac')
                self.assertLess(abs(record['duration_seconds'] - 0.8), 0.1)
                self.assertTrue(validate_video(path)['full_decode_verified'])
                self.assertEqual(compose_album(folder, root / 'out', log=lambda _: None)[0], path)
                self.assertEqual(load_album(folder), manifest)
                path.write_bytes(b'changed')
                with self.assertRaises(DownloadError):
                    compose_album(folder, root / 'out', log=lambda _: None)
                # 无原声图文仍能离线生成静音播放版。
                manifest['files'] = [files[0]]
                (folder / '作品信息.json').write_text(json.dumps(manifest), encoding='utf-8')
                _, silent = compose_album(folder, root / 'silent', log=lambda _: None)
                self.assertIsNone(silent['audio_codec'])
                self.assertEqual(silent['duration_seconds'], 5)


if __name__ == '__main__':
    unittest.main()
