"""真实 Tk 实例测试：任务状态、离线边界与键盘路径。"""
import os
import gc
import time
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.name == "nt", "Windows native desktop tests")
class DesktopTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from douyin_local.desktop import Desktop
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Desktop(self.root, offline=True)
        self.root.update()

    def tearDown(self):
        self.app.close()
        # Tk 引用必须在主线程释放，避免下一测试的工作线程触发循环 GC。
        self.app = None
        self.root = None
        gc.collect()

    def finish(self):
        deadline = time.monotonic() + 3
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.app.busy)

    def test_offline_gui_and_shortcut_cannot_start_network_download(self):
        self.assertEqual(self.app.page, "local")
        self.assertEqual(self.app.download_button.cget("state"), "disabled")
        self.assertEqual(self.app.read_button.cget("state"), "disabled")
        self.app.input.insert("1.0", "https://www.douyin.com/video/1234567890123456789")
        self.app.show_page("download")
        with patch("douyin_local.desktop.download_text") as service:
            self.app.download()
            self.app.download(read_only=True)
            self.app.shortcut()
            service.assert_not_called()
        self.assertFalse(self.app.busy)

    def test_worker_restores_controls_and_preserves_offline_restriction(self):
        def task(log):
            log("fixture result")
            return "success", "完成", "fixture verified"
        self.app.start("处理中", task)
        self.assertEqual(self.app.output_entry.cget("state"), "disabled")
        self.finish()
        self.assertEqual(self.app.output_entry.cget("state"), "normal")
        self.assertEqual(self.app.download_button.cget("state"), "disabled")
        self.assertIn("完成", self.app.status_label.cget("text"))

    def test_worker_failure_restores_ui_and_is_not_success(self):
        from douyin_local import DownloadError
        def task(log):
            raise DownloadError("fixture rejected")
        self.app.start("处理中", task)
        self.finish()
        self.assertIn("未能完成", self.app.status_label.cget("text"))
        self.assertEqual(self.app.status_detail.cget("text"), "fixture rejected")

    def test_empty_output_does_not_start_composition(self):
        self.app.folder.set("local-fixture")
        self.app.output.set("  ")
        with patch("douyin_local.desktop.compose_album") as compose:
            self.app.compose()
            compose.assert_not_called()
        self.assertFalse(self.app.busy)
        self.assertIn("保存位置", self.app.status_label.cget("text"))

    def test_xhs_limit_validation_and_read_mode_reach_service(self):
        self.app.offline = False
        self.app.set_controls(False)
        self.app.input.insert('1.0', 'https://www.xiaohongshu.com/user/profile/600000000000000000000001')
        with patch('douyin_local.desktop.download_text', return_value=[{'success': True}]) as service:
            self.app.profile_limit.set('0')
            self.app.download(read_only=True)
            service.assert_not_called()
            self.assertFalse(self.app.busy)
            self.app.profile_limit.set('5')
            self.app.download(read_only=True)
            self.finish()
            self.assertTrue(service.call_args.kwargs['read_only'])
            self.assertEqual(service.call_args.kwargs['profile_limit'], 5)
            self.assertIn('内容已读取', self.app.status_label.cget('text'))
