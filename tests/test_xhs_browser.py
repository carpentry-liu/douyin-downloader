"""可选真实浏览器契约测试；拦截全部请求，绝不读取真实账号或平台数据。"""
import json
import os
import unittest

from douyin_local import DownloadError
from douyin_local.xiaohongshu import XhsReader, canonical, identify
from test_xiaohongshu import AUTHOR, FIRST, SECOND, note_state, profile_state


@unittest.skipUnless(os.environ.get('RUN_BROWSER_TESTS') == '1', 'set RUN_BROWSER_TESTS=1; requires Edge/Chrome')
class BrowserContractTests(unittest.TestCase):
    def test_real_page_initial_state_scroll_response_and_note_identity(self):
        state = profile_state()
        second = {'id': SECOND, 'xsecToken': 'fixture-secret', 'noteCard': {
            'title': '第二篇', 'user': {'userId': AUTHOR}}}
        api = f'https://www.xiaohongshu.com/api/sns/web/v1/user_posted?user_id={AUTHOR}'
        html = ('<html><head><title>生成主页</title></head><body style="height:3000px">测试主页'
                '<script>window.__INITIAL_STATE__=' + json.dumps(state) + ';'
                'window.addEventListener("wheel",()=>fetch(' + json.dumps(api) + '), {once:true});</script></body></html>')

        def route(request):
            url = request.request.url
            if '/api/sns/' in url:
                request.fulfill(json={'data': {'notes': [second], 'has_more': False}})
            elif '/user/profile/' in url:
                request.fulfill(content_type='text/html; charset=utf-8', body=html)
            elif '/explore/' in url:
                request.fulfill(content_type='text/html; charset=utf-8', body='<body>笔记<script>window.__INITIAL_STATE__=' +
                                json.dumps(note_state()) + '</script></body>')
            else:
                request.abort()

        with XhsReader() as reader:
            reader.context.route('**/*', route)
            profile, entries, scope = reader.profile(identify(canonical('profile', AUTHOR)), 2)
            self.assertEqual(profile['author'], '测试作者')
            self.assertEqual([entry['id'] for entry in entries], [FIRST, SECOND])
            self.assertTrue(scope['complete'])
            note = reader.note(identify(entries[0]['url']), AUTHOR)
            self.assertEqual(note['id'], FIRST)
            self.assertIn('User-Agent', note['headers'])

    def test_real_browser_risk_page_cannot_be_success(self):
        with XhsReader() as reader:
            reader.context.route('**/*', lambda route: route.fulfill(content_type='text/html; charset=utf-8',
                                  body='<title>安全限制</title><body>IP存在风险 300012</body>'))
            with self.assertRaisesRegex(DownloadError, '300012'):
                reader.profile(identify(canonical('profile', AUTHOR)), 20)


if __name__ == '__main__':
    unittest.main()
