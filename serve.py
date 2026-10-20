"""Run the crafting calculator locally with live prices and the CP tracker.

  python serve.py            # then open http://localhost:8642

Serves app/, forwards /api/* to aion2.exchange (current asks for any server), and runs the
Combat Power tracker (/cp): a reading on start and every 30 minutes while this runs, plus
/local/character endpoints. Rebuilds app/data.json (snapshot prices, sale speeds) every 12 hours. The published copy uses the price snapshot in
data.json and has no tracker. Python stdlib only.
"""
import http.server, json, socketserver, sys, threading, urllib.parse, urllib.request, webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cp_tracker  # noqa: E402
from hosting import wrap_page  # noqa: E402

PORT = 8642
APP = Path(__file__).parent / 'app'
UPSTREAM = 'https://aion2.exchange'
TRACK_EVERY = 30 * 60
_lock = threading.Lock()


def take_reading():
    with _lock:
        return cp_tracker.record()


REFRESH_EVERY = 12 * 3600


def data_loop(stop):
    """Rebuild app/data.json (snapshot prices, sale speeds) when it is older than 12 hours."""
    import subprocess, time
    data = APP / 'data.json'
    while not stop.is_set():
        age = time.time() - data.stat().st_mtime if data.exists() else REFRESH_EVERY
        if age >= REFRESH_EVERY - 60:
            try:
                subprocess.run([sys.executable, str(Path(__file__).parent / 'build_data.py')], timeout=1800,
                               capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except Exception as e:
                print(f'Data refresh failed: {e}')
            age = 0
        stop.wait(max(60, REFRESH_EVERY - age))


def tracker_loop(stop):
    while not stop.is_set():
        try:
            take_reading()
        except Exception as e:  # API down or no character set: try again next round
            print(f'CP reading failed: {e}')
        stop.wait(TRACK_EVERY)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(APP), **kw)

    def _send(self, status, body, ctype='application/json'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode('utf8')
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _character(self, path, query):
        try:
            if path == '/local/character/set':
                name = (query.get('name') or [''])[0].strip()
                region = (query.get('region') or ['nae'])[0]
                if not name:
                    return self._send(400, {'error': 'Enter a character name.'})
                cfg = cp_tracker.find(name, region)
                cp_tracker.CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding='utf8')
                cp_tracker.HISTORY.unlink(missing_ok=True)  # a new character starts a new history
                take_reading()
            elif path == '/local/character/refresh':
                take_reading()
            cfg, hist = cp_tracker.load()
            return self._send(200, {'character': cfg, 'history': hist, 'every': TRACK_EVERY})
        except SystemExit as e:  # find() reports "no character named …" this way
            return self._send(404, {'error': str(e)})
        except Exception as e:
            return self._send(502, {'error': f'Could not reach the AION 2 character service: {e}'})

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path in ('/', '/index.html'):
            # index.html is written as a page body (no doctype/head); wrap it like the publisher does
            page = (APP / 'index.html').read_text(encoding='utf8')
            return self._send(200, wrap_page('<script>window.FORGE_LOCAL = true</script>' + page), 'text/html; charset=utf-8')
        if url.path in ('/cp', '/cp/'):  # the Combat Power tracker page (a complete document)
            return self._send(200, (APP / 'cp.html').read_text(encoding='utf8'), 'text/html; charset=utf-8')
        if url.path.startswith('/local/character'):
            return self._character(url.path, urllib.parse.parse_qs(url.query))
        if not url.path.startswith('/api/'):
            return super().do_GET()
        try:
            req = urllib.request.Request(UPSTREAM + self.path, headers={'User-Agent': 'Mozilla/5.0 (personal crafting calculator)'})
            with urllib.request.urlopen(req, timeout=30) as r:
                body, status = r.read(), r.status
        except urllib.error.HTTPError as e:
            body, status = e.read(), e.code
        except Exception as e:  # network down: tell the page, it falls back to the snapshot
            body, status = str(e).encode(), 502
        self._send(status, body)

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    if sys.stdout:  # None under pythonw (the silent startup launch)
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    url = f'http://localhost:{PORT}'
    try:
        httpd = socketserver.ThreadingTCPServer(('127.0.0.1', PORT), Handler)
    except OSError:  # already running (another window): just show it
        print(f'Daeva Forge Beta is already running; opening {url}')
        if '--no-browser' not in sys.argv:
            webbrowser.open(url)
        sys.exit(0)
    stop = threading.Event()
    threading.Thread(target=tracker_loop, args=(stop,), daemon=True).start()
    threading.Thread(target=data_loop, args=(stop,), daemon=True).start()
    with httpd:
        print(f'Daeva Forge Beta on {url} (Ctrl+C to stop). CP readings every {TRACK_EVERY // 60} min while running.')
        if '--no-browser' not in sys.argv:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            stop.set()
