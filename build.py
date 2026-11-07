#!/usr/bin/env python3
"""Builds the site: the landing page and the documentation.

Landing page: index.html (English) and vi/index.html (Vietnamese) from src/.
src/template.html holds the page; {{key}} comes from src/<lang>.json and
{{icon:name}} inlines src/icons/<name>.svg (Lucide, ISC), and {{release_*}}
comes from src/release.json (the current release: badge, What's new).

Documentation: docs/ and vi/docs/ from the Markdown of the main repository
(guard-spec/guard-spec) at the commit or tag pinned in src/docs.json. The
Markdown is fetched from raw.githubusercontent.com (cached in .cache/), or
read from a local checkout with --source. Nothing is copied by hand: change
the docs in the main repository, then move the pin here. Needs mistune
(requirements.txt).

Run it after any change and commit the output: GitHub Pages serves the files
as they are.

  python3 build.py                     # landing page and docs at the pinned ref
  python3 build.py --source ../guard-spec   # docs from a local checkout (preview)
  python3 build.py --ref <sha-or-tag>  # docs at another ref (then update src/docs.json)
  python3 build.py --landing-only
"""
import argparse
import html
import json
import pathlib
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
LANGS = {"en": ("index.html", ""), "vi": ("vi/index.html", "../")}
# Absolute URL for canonical links and the link preview image; must match CNAME.
SITE_URL = "https://guardspec.io"
DOCS_OUT = {"en": ROOT / "docs", "vi": ROOT / "vi" / "docs"}
DOCS_PREFIX = {"en": "/docs/", "vi": "/vi/docs/"}
# Mermaid diagrams (```mermaid blocks) render in the browser; only pages
# that have one load it. Pinned by version and SRI hash.
MERMAID = ('<script src="https://cdn.jsdelivr.net/npm/mermaid@11.17.2/dist/mermaid.min.js" '
           'integrity="sha384-EOXBFmc3gx5mb+vn0vPvvGqACToJD24hhacX5Yx+8NUUQrHIle/Qi5Bg9o3zKwW2" '
           'crossorigin="anonymous"></script>\n'
           '<script>mermaid.initialize({startOnLoad: true, securityLevel: "strict", '
           'theme: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "neutral"});</script>')


def icon(name):
    svg = (SRC / "icons" / f"{name}.svg").read_text()
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
    svg = re.sub(r'\s*class="[^"]*"', "", svg)
    svg = svg.replace("<svg", '<svg class="ic" aria-hidden="true"', 1)
    return " ".join(svg.split())


def fill(template, values):
    out = re.sub(r"\{\{icon:([a-z0-9-]+)\}\}", lambda m: icon(m.group(1)), template)
    return re.sub(r"\{\{([a-z0-9_]+)\}\}", lambda m: values[m.group(1)], out)


def release_values(release, lang):
    """The release_* placeholders of the landing page, from src/release.json."""
    esc = html.escape
    highlights = "\n".join(
        f'      <li class="card"><h3>{esc(h["title"])}</h3><p>{h["text"]}</p></li>'
        for h in release["highlights"][lang])
    previous = "\n".join(
        f'      <li><a href="{esc(r["url"])}">{esc(r["version"])}</a>'
        f'<time datetime="{esc(r["date"])}">{esc(r["date"])}</time>'
        f'<span>{r["summary"][lang]}</span></li>'
        for r in release["previous"])
    return {
        "release_version": esc(release["version"]),
        "release_date": esc(release["date"]),
        "release_url": esc(release["url"]),
        "release_changelog": esc(release["changelog_url"]),
        "release_status": esc(release["status"][lang]),
        "release_tagline": esc(release["tagline"][lang]),
        "release_upgrade": release["upgrade"][lang],
        "release_highlights": highlights,
        "release_previous": previous,
    }


def build_landing():
    template = (SRC / "template.html").read_text()
    strings = {lang: json.loads((SRC / f"{lang}.json").read_text()) for lang in LANGS}
    release = json.loads((SRC / "release.json").read_text())
    keys = set(re.findall(r"\{\{([a-z0-9_]+)\}\}", template))
    for lang, s in strings.items():
        extra = {"lang", "root", "lang_path", "en_active", "vi_active", "site_url"} | set(release_values(release, lang))
        missing = keys - set(s) - extra
        if missing:
            sys.exit(f"{lang}.json is missing: {', '.join(sorted(missing))}")
    for lang, (out, root) in LANGS.items():
        values = dict(strings[lang], lang=lang, root=root, site_url=SITE_URL,
                      lang_path="" if lang == "en" else "vi/",
                      en_active="on" if lang == "en" else "",
                      vi_active="on" if lang == "vi" else "", **release_values(release, lang))
        path = ROOT / out
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fill(template, values))
        print(f"wrote {out}")
    return strings


# ---------------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------------

class Source:
    """Reads files of the main repository at one ref."""

    def __init__(self, repo, ref, checkout=None):
        self.repo, self.ref, self.checkout = repo, ref, checkout
        self.cache = ROOT / ".cache" / "docs" / re.sub(r"[^A-Za-z0-9._-]", "_", ref)
        self.files = {}

    def read(self, path):
        if path in self.files:
            return self.files[path]
        text = None
        if self.checkout:
            p = self.checkout / path
            text = p.read_text() if p.is_file() else None
        else:
            cached = self.cache / path
            missing = self.cache / (path + ".missing")
            if cached.is_file():
                text = cached.read_text()
            elif not missing.exists():
                url = f"https://raw.githubusercontent.com/{self.repo}/{self.ref}/{path}"
                try:
                    with urllib.request.urlopen(url, timeout=30) as r:
                        text = r.read().decode("utf-8")
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_text(text)
                except urllib.error.HTTPError as e:
                    if e.code != 404:
                        raise
                    missing.parent.mkdir(parents=True, exist_ok=True)
                    missing.touch()
        self.files[path] = text
        return text

    def blob(self, path):
        return f"https://github.com/{self.repo}/blob/{self.ref}/{path}"

    def raw(self, path):
        return f"https://raw.githubusercontent.com/{self.repo}/{self.ref}/{path}"


def gh_slug(text):
    """GitHub's heading anchor: lower case, punctuation dropped, spaces to -."""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def md_heading_text(line):
    text = re.sub(r"`([^`]*)`", r"\1", line)
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)


def split_sections(text):
    """Top-level (##) sections of a Markdown file: {title: (body, [anchors])}.

    Anchors are GitHub's for the whole file (duplicates numbered), so a link
    to README.md#x can be sent to the page that holds x."""
    sections, current, seen, fence = {}, None, {}, False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        m = None if fence else re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            s = gh_slug(md_heading_text(m.group(2)))
            n = seen.get(s, 0)
            seen[s] = n + 1
            anchor = s if n == 0 else f"{s}-{n}"
            if len(m.group(1)) <= 2:
                current = m.group(2).strip() if len(m.group(1)) == 2 else None
                if current is not None:
                    sections[current] = ["", [anchor]]
                continue
            if current is not None:
                sections[current][1].append(anchor)
        if current is not None:
            sections[current][0] += line
    return {k: (v[0], v[1]) for k, v in sections.items()}


def strip_title(text):
    """Drops leading HTML comments (license headers) and the first # heading."""
    text = re.sub(r"\A(\s*<!--.*?-->\s*)+", "", text, flags=re.S)
    return re.sub(r"\A\s*#\s+[^\n]*\n", "", text)


def resolve(base, target):
    """Repository path of target relative to the file base (posix)."""
    parts = base.split("/")[:-1]
    for p in target.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            if parts:
                parts.pop()
        else:
            parts.append(p)
    return "/".join(parts)


def render_markdown(text):
    import mistune
    md = mistune.create_markdown(escape=False, plugins=["table", "strikethrough", "task_lists", "url"])
    return md(text)


def postprocess(body, page_file, src, links, tops, page_url, shift=0):
    """Heading ids, link and image rewriting, mermaid blocks, wide tables.

    shift moves headings up: a README section starts at ###, which becomes
    h2 under the page's h1."""
    seen = {}

    def heading(m):
        level, attrs, inner = max(2, int(m.group(1)) - shift), m.group(2), m.group(3)
        s = gh_slug(inner)
        n = seen.get(s, 0)
        seen[s] = n + 1
        hid = s if n == 0 else f"{s}-{n}"
        return (f'<h{level} id="{hid}"{attrs}>{inner}'
                f'<a class="anchor" href="#{hid}" aria-hidden="true">#</a></h{level}>')

    body = re.sub(r"<h([1-6])([^>]*)>(.*?)</h\1>", heading, body, flags=re.S)

    def link(m):
        attr, url = m.group(1), html.unescape(m.group(2))
        if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I) or url.startswith("//"):
            return m.group(0)
        if url.startswith("/") and attr == "href":
            return m.group(0)   # a site path (notes in docs.json)
        target, _, frag = url.partition("#")
        frag = urllib.parse.unquote(frag)
        path = resolve(page_file, target) if target else page_file
        if attr == "src":
            return f'{attr}="{html.escape(src.raw(path))}"'
        dest = links.get((path, frag)) or links.get((path, None))
        if dest and (path, frag) in tops:
            frag = ""   # the section itself: its heading is the page title
        if dest:
            if dest == page_url:
                new = f"#{frag}" if frag else page_url
            else:
                new = dest + (f"#{frag}" if frag else "")
        else:
            new = src.blob(path) + (f"#{urllib.parse.quote(frag)}" if frag else "")
        return f'{attr}="{html.escape(new)}"'

    body = re.sub(r'\b(href|src)="([^"]*)"', link, body)
    has_mermaid = 'class="language-mermaid"' in body
    body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                  r'<pre class="mermaid">\1</pre>', body, flags=re.S)
    body = re.sub(r"<table>", '<div class="table"><table>', body)
    body = re.sub(r"</table>", "</table></div>", body)
    return body, has_mermaid


def build_docs(strings, ref=None, checkout=None):
    conf = json.loads((SRC / "docs.json").read_text())
    ref = ref or conf["ref"]
    src = Source(conf["repo"], ref, checkout)
    ui = conf["ui"]
    template = (SRC / "docs.html").read_text()

    # Which source each page uses, per language; missing pages are skipped.
    built, skipped = {}, []
    for page in conf["pages"]:
        for lang in ("en", "vi"):
            for cand in page.get(lang, []):
                text = src.read(cand["file"])
                if text is None:
                    continue
                if "section" in cand:
                    sections = split_sections(text)
                    if cand["section"] not in sections:
                        continue
                    body, anchors = sections[cand["section"]]
                else:
                    body, anchors = strip_title(text), None
                built[(page["slug"], lang)] = dict(cand, body=body, anchors=anchors)
                break
            else:
                if lang == "en" or page.get("vi"):
                    skipped.append(f"{page['slug']} ({lang}): " +
                                   ", ".join(c["file"] for c in page.get(lang, [])))

    def url(slug, lang):
        return DOCS_PREFIX[lang] + (slug + "/" if slug else "")

    # Where links into the main repository go: a whole file, or the README
    # section that holds an anchor.
    links, tops = {}, set()
    for (slug, lang), b in built.items():
        if b["anchors"] is None:
            links.setdefault((b["file"], None), url(slug, lang))
        else:
            for a in b["anchors"]:
                links[(b["file"], a)] = url(slug, lang)
            tops.add((b["file"], b["anchors"][0]))

    pages = [p for p in conf["pages"] if (p["slug"], "en") in built]
    for lang, out in DOCS_OUT.items():
        if out.exists():
            shutil.rmtree(out)

    def sidebar(lang, current):
        items = []
        for p in pages:
            own = (p["slug"], lang) in built
            href = url(p["slug"], lang if own else "en")
            label = html.escape(p["title"][lang])
            if not own and lang != "en":
                label += f' <span class="en">{ui[lang]["english"]}</span>'
            cls = ["child"] if p.get("parent") else []
            if p["slug"] == current:
                cls.append("on")
            items.append(f'<li class="{" ".join(cls)}"><a href="{href}">{label}</a></li>')
        return f'<ul>{"".join(items)}</ul>'

    def page_html(lang, slug, title, description, content, source, scripts=""):
        own = {l: (slug, l) in built or slug == "" for l in ("en", "vi")}
        alternates = "\n".join(
            f'<link rel="alternate" hreflang="{l}" href="{SITE_URL}{url(slug, l)}">'
            for l in ("en", "vi") if own[l])
        values = dict(
            lang=lang, title=html.escape(title), description=html.escape(description),
            site_url=SITE_URL, path=url(slug, lang), alternates=alternates,
            home="/" if lang == "en" else "/vi/", docs_home=DOCS_PREFIX[lang],
            docs_label=ui[lang]["docs"], nav_label=ui[lang]["nav_label"],
            en_href=url(slug, "en"), vi_href=url(slug if own["vi"] else "", "vi"),
            en_active="on" if lang == "en" else "", vi_active="on" if lang == "vi" else "",
            sidebar=sidebar(lang, slug), content=content, source=source,
            foot_security=strings[lang]["foot_security"], foot_contrib=strings[lang]["foot_contrib"],
            foot_credit=strings[lang]["foot_credit"], scripts=scripts)
        return fill(template, values)

    def write(lang, slug, text):
        path = DOCS_OUT[lang] / slug / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    count = 0
    for (slug, lang), b in built.items():
        page = next(p for p in conf["pages"] if p["slug"] == slug)
        title = page["title"][lang]
        body_html, mermaid = postprocess(render_markdown(b["body"]), b["file"], src, links, tops, url(slug, lang),
                                     shift=1 if b.get("section") else 0)
        note = f'<p class="doc-note">{b["note"]}</p>' if b.get("note") else ""
        content = f"<h1>{html.escape(title)}</h1>\n{note}\n{body_html}"
        anchor = ""
        if b.get("section"):
            anchor = "#" + b["anchors"][0]
        source = (f'{ui[lang]["source"]}: <a href="{src.blob(b["file"])}{anchor}">'
                  f'{html.escape(b["file"])}{anchor}</a> @ <code>{html.escape(ref[:12])}</code>')
        first = re.sub(r"<[^>]+>", "", body_html)
        description = " ".join(first.split())[:155]
        write(lang, slug, page_html(lang, slug, title, description, content, source,
                                    MERMAID if mermaid else ""))
        count += 1

    # Index pages: the top-level sections with a line each.
    for lang in ("en", "vi"):
        cards = []
        for p in pages:
            if p.get("parent"):
                continue
            own = (p["slug"], lang) in built
            label = html.escape(p["title"][lang])
            if not own and lang != "en":
                label += f' <span class="en">{ui[lang]["english"]}</span>'
            cards.append(f'<a class="card doc-card" href="{url(p["slug"], lang if own else "en")}">'
                         f'<h3>{label}</h3><p>{html.escape(ui[lang]["intro"].get(p["slug"], ""))}</p></a>')
        ref_link = f'<a href="https://github.com/{conf["repo"]}/tree/{ref}"><code>{html.escape(ref[:12])}</code></a>'
        content = (f'<h1>{html.escape(ui[lang]["home_title"])}</h1>\n'
                   f'<p class="lead-doc">{html.escape(ui[lang]["home_lead"])} {ref_link}.</p>\n'
                   f'<div class="doc-cards">{"".join(cards)}</div>')
        write(lang, "", page_html(lang, "", ui[lang]["home_title"], ui[lang]["home_lead"], content,
                                  f'{ui[lang]["source"]}: <a href="https://github.com/{conf["repo"]}">{conf["repo"]}</a>'))
        count += 1

    print(f"wrote {count} docs pages from {conf['repo']}@{ref}")
    if skipped:
        print("skipped (no source at this ref):")
        for s in skipped:
            print(f"  - {s}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", type=pathlib.Path, help="read the docs from this checkout of guard-spec/guard-spec")
    ap.add_argument("--ref", help="build the docs at this commit or tag instead of the one in src/docs.json")
    ap.add_argument("--landing-only", action="store_true", help="skip the docs")
    args = ap.parse_args()
    strings = build_landing()
    if not args.landing_only:
        try:
            import mistune  # noqa: F401
        except ImportError:
            sys.exit("the docs need mistune: pip install --require-hashes -r requirements.txt")
        build_docs(strings, ref=args.ref, checkout=args.source.resolve() if args.source else None)


if __name__ == "__main__":
    main()
