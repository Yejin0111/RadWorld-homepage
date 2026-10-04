"""Local preview server that makes the browser revalidate every file on each load.

Usage:
  python3 tools/serve.py            # http://127.0.0.1:8000/
  python3 tools/serve.py 8766
  python3 tools/serve.py 8767 --token SECRET   # private review link: open /?k=SECRET once

python3 -m http.server sends no Cache-Control header, so browsers keep CSS and JavaScript by
heuristic and, after an edit, can pair the new index.html with the old stylesheet and scripts.

With --token every request needs a cookie that the link /?k=SECRET sets, so a tunnel to this
server (for example cloudflared) can be shared with reviewers without making the page public.
"""
import argparse
import functools
import hmac
import http.cookies
import http.server
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COOKIE = "rw_review"


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    token = None

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        if self.token:
            self.send_header("X-Robots-Tag", "noindex, nofollow")
        super().end_headers()

    def allowed(self):
        """True to serve the file. Otherwise a redirect or an error has been sent."""
        if not self.token:
            return True
        key = self.token.encode()
        jar = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        if COOKIE in jar and hmac.compare_digest(jar[COOKIE].value.encode(), key):
            return True
        url = urllib.parse.urlsplit(self.path)
        if hmac.compare_digest(urllib.parse.parse_qs(url.query).get("k", [""])[0].encode(), key):
            self.send_response(303)
            self.send_header("Set-Cookie", f"{COOKIE}={self.token}; Path=/; Max-Age=1209600; HttpOnly; Secure; SameSite=Lax")
            self.send_header("Location", url.path or "/")
            self.end_headers()
            return False
        self.send_error(403, "Private preview. Open the link with its key.")
        return False

    def do_GET(self):
        if self.allowed():
            super().do_GET()

    def do_HEAD(self):
        if self.allowed():
            super().do_HEAD()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", nargs="?", type=int, default=8000)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--token", help="require /?k=TOKEN once (then a cookie) for every request")
    args = ap.parse_args()
    NoCacheHandler.token = args.token
    handler = functools.partial(NoCacheHandler, directory=str(ROOT))
    with http.server.ThreadingHTTPServer((args.bind, args.port), handler) as httpd:
        print(f"Serving {ROOT} at http://{args.bind}:{args.port}/", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
