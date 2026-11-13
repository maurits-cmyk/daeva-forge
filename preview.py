"""Serve dist/ the way Cloudflare does, to test a build before pushing: clean addresses (/profit, /item/<name>
serve the .html file) and the headers in dist/_headers (the content security policy included).

  python preview.py [port]     # default 8650

Copy a price file or two into dist/prices/ first (index.json and e.g. 12101.json from daevaforge.com).
"""
import functools, http.server, sys
from pathlib import Path

DIST = Path(__file__).parent / 'dist'


def site_headers():
    """The '/*' block of dist/_headers (the only block we write)."""
    f = DIST / '_headers'
    return [tuple(x.strip() for x in line.split(':', 1)) for line in f.read_text(encoding='utf8').splitlines()
            if line.startswith(' ') and ':' in line] if f.exists() else []


class Handler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.path.split('?', 1)[0]
        if path != '/' and not Path(path).suffix and (DIST / (path.lstrip('/') + '.html')).is_file():
            self.path = path + '.html' + self.path[len(path):]
        return super().send_head()

    def do_POST(self):  # /api/hit and /api/feedback live in the Worker; answer like it does, without storing anything
        self.send_response(204 if self.path.startswith('/api/hit') else 503)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def end_headers(self):
        for k, v in site_headers():
            self.send_header(k, v)
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8650
    http.server.ThreadingHTTPServer(('127.0.0.1', port), functools.partial(Handler, directory=str(DIST))).serve_forever()
