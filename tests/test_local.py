import copy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import imageio_ffmpeg

from douyin_local import DownloadError
from douyin_local.download import find_existing, safe_name, save_video, validate_video
from douyin_local.links import DouyinRedirect, check_url, extract_url, resolve_id, video_id_from_url
from douyin_local.resolver import find_item, item_to_info, resolve_info


VIDEO_ID = "7000000000000000001"


class LinkTests(unittest.TestCase):
    def test_mixed_share_text_and_markdown(self):
        text = "刘某 9/9&#x20;22:17\n7.48 复制打开抖音 [https://v.douyin.com/Example/](https://v.douyin.com/Example/) :3pm"
        self.assertEqual(extract_url(text), "https://v.douyin.com/Example/")

    def test_skips_unrelated_url(self):
        self.assertEqual(extract_url("https://example.com https://v.douyin.com/Example/。"), "https://v.douyin.com/Example/")

    def test_domain_spoof_credentials_and_ports(self):
        for url in ["https://douyin.com.evil.test/video/1", "file:///tmp/video.mp4",
                    "https://evil@www.douyin.com/video/1", "http://127.0.0.1/", "https://douyin.com:123/"]:
            with self.subTest(url=url), self.assertRaises(DownloadError):
                check_url(url)

    def test_redirect_rejects_unrelated_host(self):
        with self.assertRaises(DownloadError):
            DouyinRedirect().redirect_request(None, None, 302, "", {}, "http://127.0.0.1/")

    def test_canonical_share_and_modal_ids(self):
        for url in [f"https://www.douyin.com/video/{VIDEO_ID}",
                    f"https://www.iesdouyin.com/share/video/{VIDEO_ID}/",
                    f"https://www.douyin.com/?modal_id={VIDEO_ID}"]:
            self.assertEqual(video_id_from_url(url), VIDEO_ID)
            self.assertEqual(resolve_id(url), VIDEO_ID)

    def test_non_video_input_is_rejected(self):
        for text in ["没有链接", "https://example.com/video", ""]:
            with self.assertRaises(DownloadError):
                extract_url(text)
        with self.assertRaises(DownloadError):
            resolve_id("https://www.douyin.com/note/7000000000000000001")


class ResolverTests(unittest.TestCase):
    def item(self):
        return {"aweme_id": VIDEO_ID, "desc": "作品", "author": {"nickname": "测试作者"},
                "video": {"duration": 1000, "play_addr": {"width": 320, "height": 180,
                          "data_size": 4096, "url_list": ["https://media.example/video.mp4"]}}}

    def test_exact_identity_ignores_ad_and_recommendation(self):
        wanted = self.item()
        other = {**wanted, "aweme_id": "7000000000000000002"}
        self.assertIs(find_item({"ad": other, "data": [wanted]}, VIDEO_ID), wanted)
        self.assertIsNone(find_item({"aweme_detail": other}, VIDEO_ID))
        with self.assertRaises(DownloadError):
            item_to_info(other, VIDEO_ID)

    def test_missing_media_does_not_use_download_watermark_or_recommendation(self):
        item = self.item()
        item["video"] = {"download_addr": {"url_list": ["https://media.example/watermark.mp4"]}}
        with self.assertRaises(DownloadError):
            item_to_info(item, VIDEO_ID)

    def test_album_is_rejected(self):
        item = self.item()
        item["images"] = [{"url_list": ["https://media.example/image.jpeg"]}]
        with self.assertRaises(DownloadError):
            item_to_info(item, VIDEO_ID)

    def test_duplicate_formats_keep_detailed_bitrate(self):
        item = self.item()
        item["video"]["bit_rate"] = [{"play_addr": copy.deepcopy(item["video"]["play_addr"]), "bit_rate": 800000, "is_h265": 0}]
        info = item_to_info(item, VIDEO_ID)
        self.assertEqual(len(info["formats"]), 1)
        self.assertEqual(info["formats"][0]["tbr"], 800)
        self.assertEqual(info["duration"], 1)

    def test_auto_falls_back_but_explicit_engine_reports_failure(self):
        with patch("douyin_local.resolver.direct_info", side_effect=DownloadError("Cookie")), patch("douyin_local.resolver.browser_info", return_value={"id": VIDEO_ID}) as browser:
            result, engine = resolve_info(VIDEO_ID, log=lambda _: None)
            self.assertEqual((result["id"], engine), (VIDEO_ID, "browser"))
            with self.assertRaises(DownloadError):
                resolve_info(VIDEO_ID, engine="yt-dlp", log=lambda _: None)
            self.assertEqual(browser.call_count, 1)

    def test_windows_names(self):
        self.assertEqual(safe_name("CON"), "_CON")
        self.assertNotIn("/", safe_name("../a:b/c?"))
        self.assertEqual(safe_name("   "), "video")


class SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class MediaIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.media = cls.root / "source.mp4"
        result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i",
                                 "color=c=blue:s=320x180:r=25", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                                 "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(cls.media)], capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", "replace"))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SilentHandler, directory=str(cls.root)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def test_real_transport_decode_record_skip_and_tamper(self):
        info = {"id": VIDEO_ID, "title": "测试视频", "uploader": "测试作者", "duration": 1,
                "formats": [{"format_id": "test", "url": f"http://127.0.0.1:{self.server.server_port}/source.mp4?secret=not-for-record",
                             "ext": "mp4", "width": 320, "height": 180, "vcodec": "h264", "filesize": self.media.stat().st_size}]}
        output = self.root / "output"
        path, record = save_video(info, output, "test", log=lambda _: None)
        self.assertTrue(record["full_decode_verified"])
        self.assertEqual((record["width"], record["height"]), (320, 180))
        self.assertEqual(record["audio_codec"], "aac")
        self.assertEqual(find_existing(output, VIDEO_ID)[0], path)
        saved = path.with_suffix(".json").read_text(encoding="utf-8")
        self.assertNotIn("secret", saved)
        self.assertNotIn("127.0.0.1", saved)
        self.assertEqual(json.loads(saved)["file"], path.name)
        with self.assertRaises(DownloadError):
            save_video(info, output, "test", log=lambda _: None)
        before = path.read_bytes()
        path.write_bytes(before[:-1] + bytes([before[-1] ^ 1]))
        self.assertIsNone(find_existing(output, VIDEO_ID))

    def test_html_and_truncated_mp4_are_rejected(self):
        html = self.root / "error.mp4"
        html.write_bytes(b"<html>login required</html>" * 100)
        with self.assertRaises(DownloadError):
            validate_video(html)
        broken = self.root / "broken.mp4"
        broken.write_bytes(self.media.read_bytes()[:1200])
        with self.assertRaises(DownloadError):
            validate_video(broken)

    def test_wrong_length_or_preview_duration_rejected(self):
        with self.assertRaises(DownloadError):
            validate_video(self.media, expected_size=100)
        with self.assertRaises(DownloadError):
            validate_video(self.media, expected_duration=34.1)


if __name__ == "__main__":
    unittest.main()
