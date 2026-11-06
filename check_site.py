#!/usr/bin/env python3
"""Checks the built site for broken links and assets.

Every href and src in the HTML files: a site path must exist (a directory
needs an index.html) and a #fragment must be an id on the target page.
With --external, links into the guard-spec repositories on github.com and
raw.githubusercontent.com are fetched too (other hosts are not).

  python3 check_site.py              # internal links, offline
  python3 check_site.py --external   # also the links into the main repository
"""
import argparse
import concurrent.futures
import html
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
SKIP_DIRS = {".git", ".cache", "src", "node_modules", ".venv"}


def pages():
    for p in sorted(ROOT.rglob("*.html")):
        if not SKIP_DIRS.intersection(p.relative_to(ROOT).parts):
            yield p


def ids(path, cache={}):
    if path not in cache:
        cache[path] = set(re.findall(r'\bid="([^"]+)"', path.read_text()))
    return cache[path]


def target(page, url):
    path = urllib.parse.unquote(url)
    base = ROOT if path.startswith("/") else page.parent
    t = (base / path.lstrip("/")).resolve()
    if t.is_dir() or path.endswith("/"):
        t = t / "index.html"
    return t


def check_external(urls):
    def fetch(u):
        req = urllib.request.Request(u, method="GET", headers={"User-Agent": "guardspec-site-check"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return u, r.status
        except urllib.error.HTTPError as e:
            return u, e.code
        except Exception as e:  # noqa: BLE001
            return u, str(e)
    bad = []
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        for u, status in ex.map(fetch, sorted(urls)):
            if status != 200:
                bad.append(f"{u}: {status}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--external", action="store_true")
    args = ap.parse_args()
    bad, external, count = [], set(), 0
    for page in pages():
        text = page.read_text()
        for attr, raw in re.findall(r'\b(href|src)="([^"]*)"', text):
            url = html.unescape(raw)
            count += 1
            if re.match(r"^(mailto|tel|data):", url):
                continue
            if re.match(r"^https?://", url):
                host = urllib.parse.urlsplit(url).netloc
                if (host == "github.com" and "/guard-spec/" in url) or host == "raw.githubusercontent.com":
                    external.add(url.split("#")[0])
                continue
            path, _, frag = url.partition("#")
            frag = urllib.parse.unquote(frag)
            t = target(page, path) if path else page
            rel = page.relative_to(ROOT)
            if not t.exists():
                bad.append(f"{rel}: {attr}={url} (no file)")
            elif frag and t.suffix == ".html" and frag not in ids(t):
                bad.append(f"{rel}: {attr}={url} (no id)")
    if args.external:
        print(f"fetching {len(external)} links into the repositories")
        bad += check_external(external)
    print(f"{count} links in {len(list(pages()))} pages; broken: {len(bad)}")
    for b in bad:
        print("  " + b)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
