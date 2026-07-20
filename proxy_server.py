import http.server
import urllib.request
import urllib.parse
import json
import ssl
import sys
import time
import hashlib

PORT = 8080

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

MIXIN_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

_cache = {'buvid': None, 'wbi': None, 'wbi_ts': 0}


def _http_get(url, cookie=None):
    ctx = ssl.create_default_context()
    headers = {'User-Agent': UA, 'Referer': 'https://www.bilibili.com/'}
    if cookie:
        headers['Cookie'] = cookie
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        return resp.read(), resp


def get_buvid():
    if _cache['buvid']:
        return _cache['buvid']
    try:
        body, _ = _http_get('https://api.bilibili.com/x/frontend/finger/spi')
        data = json.loads(body)
        b3 = data['data']['b_3']
        b4 = data['data']['b_4']
        _cache['buvid'] = f'buvid3={b3}; buvid4={b4}'
    except Exception:
        _cache['buvid'] = ''
    return _cache['buvid']


def get_wbi_keys():
    now = time.time()
    if _cache['wbi'] and now - _cache['wbi_ts'] < 3600:
        return _cache['wbi']
    body, _ = _http_get('https://api.bilibili.com/x/web-interface/nav', cookie=get_buvid())
    data = json.loads(body)
    img_url = data['data']['wbi_img']['img_url']
    sub_url = data['data']['wbi_img']['sub_url']
    img_key = img_url.rsplit('/', 1)[-1].split('.')[0]
    sub_key = sub_url.rsplit('/', 1)[-1].split('.')[0]
    raw = img_key + sub_key
    mixin = ''.join(raw[i] for i in MIXIN_ENC_TAB)[:32]
    _cache['wbi'] = mixin
    _cache['wbi_ts'] = now
    return mixin


def wbi_sign(params, mixin_key):
    params = dict(params)
    params['wts'] = str(int(time.time()))
    items = sorted(params.items())
    query = urllib.parse.urlencode(items)
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return query + '&w_rid=' + w_rid


def fetch_space_videos(mid, pn=1, ps=30):
    mixin = get_wbi_keys()
    params = {
        'mid': mid,
        'ps': str(ps),
        'pn': str(pn),
        'order': 'pubdate',
        'platform': 'web',
        'web_location': '1550101',
    }
    signed = wbi_sign(params, mixin)
    url = 'https://api.bilibili.com/x/space/wbi/arc/search?' + signed
    body, _ = _http_get(url, cookie=get_buvid())
    return json.loads(body)

class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = parsed.query

        # 抓取 B站用户视频（服务端 WBI 签名 + buvid cookie）：/api/bili-videos?mid=...
        if path == '/api/bili-videos':
            q = urllib.parse.parse_qs(qs)
            mid = (q.get('mid') or [''])[0]
            pn = (q.get('pn') or ['1'])[0]
            ps = (q.get('ps') or ['30'])[0]
            try:
                if not mid.isdigit():
                    raise ValueError('无效的 UID')
                data = fetch_space_videos(mid, int(pn), int(ps))
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode('utf-8'))
            except Exception as e:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'code': -1, 'message': str(e)}).encode('utf-8'))
            return

        # 代理 B站 API 请求：/proxy/bili/...
        if path.startswith('/proxy/bili/'):
            target_path = path[len('/proxy/bili/'):]
            url = 'https://api.bilibili.com/' + target_path
            if qs:
                url += '?' + qs
            
            try:
                ctx = ssl.create_default_context()
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://www.bilibili.com/',
                })
                with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                    body = resp.read()
                    self.send_response(200)
                    self.send_header('Content-Type', resp.headers.get('Content-Type', 'application/json'))
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            return

        # 代理 B站 空间页：/proxy/space/...
        if path.startswith('/proxy/space/'):
            target_path = path[len('/proxy/space/'):]
            url = 'https://space.bilibili.com/' + target_path
            if qs:
                url += '?' + qs
            
            try:
                ctx = ssl.create_default_context()
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://www.bilibili.com/',
                })
                with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                    body = resp.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(('Error: ' + str(e)).encode())
            return

        # 默认：静态文件
        super().do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', PORT), ProxyHandler)
    print(f'=== CGOI 排行榜代理服务器 ===')
    print(f'地址: http://localhost:{PORT}')
    print(f'按 Ctrl+C 停止')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
        print('\n服务器已停止')
