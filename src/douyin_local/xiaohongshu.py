"""小红书公开页面适配；不读取账号资料、不生成接口签名。"""
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from playwright.sync_api import Error as BrowserError, sync_playwright

from . import DownloadError
from .links import USER_AGENT
from .posts import launch_browser

HOSTS = {'www.xiaohongshu.com', 'xiaohongshu.com', 'xhslink.com', 'xhslink.cn'}
ID = r'[0-9a-fA-F]{24}'
BASE = 'https://www.xiaohongshu.com'


def check_url(url):
    try:
        parts = urlsplit(url)
        valid = (parts.scheme in {'http', 'https'} and parts.hostname in HOSTS and
                 not parts.username and not parts.password and parts.port in {None, 80, 443})
    except ValueError:
        valid = False
    if not valid:
        raise DownloadError('请提供小红书主页、笔记或 xhslink 分享链接。')
    return url


def is_xhs(url):
    try:
        check_url(url)
        return True
    except DownloadError:
        return False


def canonical(kind, identity):
    if kind not in {'profile', 'note'} or not re.fullmatch(ID, identity):
        raise DownloadError('小红书作品或作者 ID 无效。')
    return f"{BASE}/{'user/profile' if kind == 'profile' else 'explore'}/{identity.lower()}"


def identify(url):
    check_url(url)
    parts = urlsplit(url)
    if parts.hostname not in {'www.xiaohongshu.com', 'xiaohongshu.com'}:
        return None
    profile = re.fullmatch(rf'/user/profile/({ID})/?', parts.path)
    note = re.fullmatch(rf'/(?:explore|discovery/item)/({ID})/?', parts.path)
    nested = re.fullmatch(rf'/user/profile/{ID}/({ID})/?', parts.path)
    match = profile or note or nested
    if not match:
        return None
    kind, identity = ('profile' if profile else 'note'), match.group(1).lower()
    # 只保留访问页面所需的分享上下文；后续仅持久化 canonical。
    query = parse_qs(parts.query)
    context = {key: query[key][0] for key in ('xsec_token', 'xsec_source') if query.get(key)}
    return {'kind': kind, 'id': identity, 'url': canonical(kind, identity) + ('?' + urlencode(context) if context else '')}


def resolve(url, timeout=20):
    direct = identify(url)
    if direct:
        return direct
    if urlsplit(url).hostname not in {'xhslink.com', 'xhslink.cn'}:
        raise DownloadError('该小红书链接不是主页或单篇笔记。')

    class Redirect(HTTPRedirectHandler):
        target = None

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            check_url(newurl)
            self.target = identify(newurl)
            if self.target:
                return None  # 已找到目标，不继续 HTTP 跳转至登录页。
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    redirect = Redirect()
    try:
        with build_opener(redirect).open(Request(url, headers={'User-Agent': USER_AGENT}), timeout=timeout) as response:
            target = identify(response.url)
    except HTTPError as error:
        if redirect.target and error.code in {301, 302, 303, 307, 308}:
            return redirect.target
        raise DownloadError('小红书分享链接未能访问，请重新复制完整分享文案。') from None
    except (OSError, URLError):
        raise DownloadError('小红书短链访问失败，请检查网络。') from None
    if not target:
        raise DownloadError('小红书短链没有指向可识别的主页或笔记。')
    return target


def unwrap(value):
    if isinstance(value, dict) and value.get('__v_isRef') is True:
        return value.get('_value', value.get('value'))
    return value


def mapping(value):
    value = unwrap(value)
    return value if isinstance(value, dict) else {}


def note_urls(value):
    urls = []
    if isinstance(value, str):
        urls = [value]
    elif isinstance(value, list):
        urls = [url for item in value for url in note_urls(item)]
    valid = []
    for url in urls:
        try:
            parts = urlsplit(url)
            if parts.scheme in {'https', 'http'} and parts.hostname and not parts.username and not parts.password:
                valid.append(url)
        except ValueError:
            continue
    return list(dict.fromkeys(valid))


def normalize_note(state, identity):
    data = mapping(mapping(mapping(state).get('note')).get('noteDetailMap'))
    entry = data.get(identity, {}) if isinstance(data, dict) else {}
    note = unwrap(entry.get('note', {})) if isinstance(entry, dict) else {}
    if not isinstance(note, dict) or str(note.get('noteId', note.get('id', ''))).lower() != identity:
        raise DownloadError('未取得该小红书笔记的完整内容；请检查分享链接或在浏览器确认可访问。')
    user = mapping(note.get('user'))
    images = []
    for index, item in enumerate(note.get('imageList') or [], 1):
        if not isinstance(item, dict):
            continue
        urls = note_urls(item.get('urlDefault')) + note_urls(item.get('urlPre'))
        for option in item.get('infoList') or []:
            if isinstance(option, dict):
                urls += note_urls(option.get('url'))
        if urls:
            images.append({'index': index, 'urls': list(dict.fromkeys(urls)), 'video': None})
    video = mapping(note.get('video'))
    streams = mapping(mapping(video.get('media')).get('stream'))
    formats = []
    for codec, variants in streams.items():
        for index, variant in enumerate(variants if isinstance(variants, list) else []):
            if not isinstance(variant, dict):
                continue
            for url_index, url in enumerate(note_urls(variant.get('masterUrl')) + note_urls(variant.get('backupUrls'))):
                formats.append({'format_id': f'{codec}-{index}-{url_index}', 'url': url, 'ext': 'mp4',
                                'vcodec': variant.get('videoCodec') or codec, 'width': variant.get('width'),
                                'height': variant.get('height'), 'filesize': variant.get('size') or None,
                                'tbr': variant.get('avgBitrate', 0) / 1000 if isinstance(variant.get('avgBitrate'), (int, float)) else None})
    kind = 'video' if note.get('type') == 'video' else 'album'
    return {'platform': 'xiaohongshu', 'id': identity, 'kind': kind, 'title': note.get('title') or identity,
            'description': note.get('desc') or '', 'author': user.get('nickname'), 'author_id': user.get('userId'),
            'source_url': canonical('note', identity), 'published_at': note.get('time'),
            'tags': [tag['name'] for tag in (note.get('tagList') or []) if isinstance(tag, dict) and isinstance(tag.get('name'), str)],
            'interactions': {key: mapping(note.get('interactInfo')).get(key) for key in
                             ('likedCount', 'collectedCount', 'commentCount', 'shareCount')},
            'images': images, 'audio_urls': [], 'formats': formats}


def normalize_profile(state, identity):
    user = mapping(mapping(state).get('user'))
    data = mapping(user.get('userPageData'))
    basic = mapping(data.get('basicInfo'))
    if not basic.get('nickname'):
        raise DownloadError('未取得小红书主页资料；该页面可能要求登录或验证。')
    actual_id = basic.get('userId') or data.get('userId')
    if actual_id and str(actual_id).lower() != identity:
        raise DownloadError('主页作者 ID 不匹配，已停止读取。')
    stats = {item.get('type'): item.get('count') for item in (data.get('interactions') or []) if isinstance(item, dict)}
    return {'platform': 'xiaohongshu', 'id': identity, 'author': basic['nickname'], 'description': basic.get('desc'),
            'red_id': basic.get('redId'), 'source_url': canonical('profile', identity),
            'followers': stats.get('fans'), 'following': stats.get('follows'), 'likes_and_collects': stats.get('interaction')}


def profile_entries(items, author_id):
    found = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        card = mapping(item.get('noteCard') or item.get('note_card') or item)
        identity = item.get('id') or item.get('noteId') or card.get('noteId')
        user = mapping(card.get('user'))
        if not isinstance(identity, str) or not re.fullmatch(ID, identity):
            continue
        if user.get('userId') and str(user['userId']).lower() != author_id:
            continue
        token = item.get('xsecToken') or item.get('xsec_token') or card.get('xsecToken')
        url = canonical('note', identity)
        if token:
            url += '?' + urlencode({'xsec_token': token, 'xsec_source': 'pc_user'})
        found.append({'id': identity.lower(), 'title': card.get('displayTitle') or card.get('title') or '',
                      'kind': card.get('type'), 'url': url})
    return found


def access_error(url, title, body):
    path = urlsplit(url).path
    if path.startswith('/website-login/error') or title == '安全限制':
        return '小红书限制了当前网络访问：IP 存在风险（300012）。请先在浏览器确认主页可正常访问。' if '300012' in body else '小红书返回安全限制，请在浏览器查看平台提示。'
    if path.startswith('/login') or path.startswith('/website-login'):
        return '小红书要求登录或验证；当前工具使用独立匿名浏览器，未读取账号会话。'
    return None


class XhsReader:
    def __enter__(self):
        self.playwright = sync_playwright().start()
        try:
            self.browser = launch_browser(self.playwright)
            self.context = self.browser.new_context(locale='zh-CN', viewport={'width': 1280, 'height': 900})
            self.page = self.context.new_page()
            self.headers = {'User-Agent': self.page.evaluate('navigator.userAgent'), 'Referer': BASE + '/'}
        except Exception:
            try:
                if hasattr(self, 'browser'):
                    self.browser.close()
            finally:
                self.playwright.stop()
            raise
        return self

    def __exit__(self, *args):
        try:
            self.browser.close()
        finally:
            self.playwright.stop()

    def state(self):
        return self.page.evaluate('() => JSON.parse(JSON.stringify(window.__INITIAL_STATE__ || {}))')

    def guard(self):
        error = access_error(self.page.url, self.page.title(), self.page.locator('body').inner_text(timeout=3000))
        if error:
            raise DownloadError(error)

    def navigate(self, target):
        try:
            try:
                self.page.goto(target['url'], wait_until='domcontentloaded', timeout=40000)
            except BrowserError:
                pass
            last_error = None
            for _ in range(30):
                try:
                    self.guard()
                    current = identify(self.page.url) if is_xhs(self.page.url) else None
                except BrowserError:
                    # 页面连续跳转会销毁执行上下文，等待下一次稳定快照。
                    self.page.wait_for_timeout(300)
                    continue
                if not current or (current['kind'], current['id']) != (target['kind'], target['id']):
                    last_error = DownloadError('浏览器未打开目标小红书页面，已停止读取以免使用旧页面内容。')
                    self.page.wait_for_timeout(300)
                    continue
                try:
                    state = self.state()
                    parsed = normalize_profile(state, target['id']) if target['kind'] == 'profile' else normalize_note(state, target['id'])
                    return parsed, state
                except DownloadError as error:
                    last_error = error
                except BrowserError:
                    last_error = DownloadError('小红书页面跳转尚未完成，请检查网络后重试。')
                self.page.wait_for_timeout(300)
            raise last_error or DownloadError('小红书页面未返回内容。')
        except BrowserError:
            raise DownloadError('小红书页面读取失败，请先在浏览器确认该链接可访问。') from None

    def note(self, target, author_id=None):
        note, _ = self.navigate(target)
        if author_id and str(note.get('author_id') or '').lower() != author_id:
            raise DownloadError('笔记作者与主页不一致，停止下载以免误收其他内容。')
        note['headers'] = self.headers
        return note

    def profile(self, target, limit):
        if not 1 <= limit <= 200:
            raise DownloadError('主页笔记上限应为 1 到 200。')
        identity = target['id']
        collected = {}
        has_more = None

        def receive(response):
            nonlocal has_more
            parts = urlsplit(response.url)
            if (parts.hostname or '').endswith('.xiaohongshu.com') and parts.path == '/api/sns/web/v1/user_posted':
                if parse_qs(parts.query).get('user_id') != [identity] or response.status != 200:
                    return
                try:
                    data = response.json().get('data') or {}
                    for entry in profile_entries(data.get('notes'), identity):
                        collected.setdefault(entry['id'], entry)
                    if isinstance(data.get('has_more'), bool):
                        has_more = data['has_more']
                except (ValueError, TypeError, AttributeError, BrowserError):
                    pass

        self.page.on('response', receive)
        try:
            profile, state = self.navigate(target)
            stagnant = 0
            for _ in range(min(40, limit + 2)):
                before = len(collected)
                user = mapping(state.get('user'))
                groups = unwrap(user.get('notes', []))
                items = unwrap(groups[0]) if isinstance(groups, list) and groups and isinstance(unwrap(groups[0]), list) else groups
                for entry in profile_entries(items, identity):
                    collected.setdefault(entry['id'], entry)
                # 页面卡片有时只有链接携带 ID；限制在主页发布列表区域。
                links = self.page.locator('.feeds-tab-container section.note-item a[href], .user-page .feeds-container section.note-item a[href]').evaluate_all(
                    '(nodes) => nodes.map(a => ({url: a.href, title: a.closest("section")?.innerText || ""}))')
                for link in links:
                    try:
                        note_target = identify(link['url'])
                    except DownloadError:
                        continue
                    if note_target and note_target['kind'] == 'note':
                        collected.setdefault(note_target['id'], {**note_target, 'title': link['title'][:300]})
                if len(collected) >= limit or has_more is False:
                    break
                stagnant = stagnant + 1 if len(collected) == before else 0
                if stagnant >= 3:
                    break
                self.page.mouse.wheel(0, 1400)
                self.page.wait_for_timeout(1000)
                self.guard()
                state = self.state()
            entries = list(collected.values())[:limit]
            return profile, entries, {'limit': limit, 'collected': len(entries), 'has_more': has_more,
                                      'complete': has_more is False and len(collected) <= limit}
        except BrowserError:
            raise DownloadError('小红书主页列表加载未完成，请在浏览器确认访问状态。') from None
        finally:
            self.page.remove_listener('response', receive)
