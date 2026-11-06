# guard-spec.github.io

The Guard Spec website, served by GitHub Pages. The project itself lives in
[guard-spec/guard-spec](https://github.com/guard-spec/guard-spec).

## Layout

| Path | What it is |
|---|---|
| `src/template.html` | The landing page. `{{key}}` is replaced from `src/<lang>.json`, `{{icon:name}}` by `src/icons/<name>.svg` |
| `src/en.json`, `src/vi.json` | English and Vietnamese text; both must have every key |
| `src/docs.json` | The documentation: the pinned ref of the main repository, every page and its Markdown source, the docs UI text |
| `src/docs.html` | The documentation page template |
| `src/icons/` | Lucide icons 0.468.0 (ISC), inlined at build time |
| `src/og.html` | Source of the link preview image `assets/og.png` |
| `assets/` | Stylesheet, logo, diagrams and admin UI screenshots |
| `index.html`, `vi/index.html`, `docs/`, `vi/docs/` | Generated; commit them, Pages serves them as they are |
| `build.py` | Builds all of the above |
| `check_site.py` | Checks every link and asset in the built pages |

## Editing

```bash
python3 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.txt
.venv/bin/python build.py      # regenerate the landing page and the docs
python3 check_site.py          # broken links or assets (--external: also the links into the main repo)
./render-og.sh                 # only after changing src/og.html
python3 -m http.server 8000    # preview at http://localhost:8000
```

`python3 build.py --landing-only` needs nothing but Python.

The diagrams and screenshots in `assets/` are copies of `docs/images/` in the
main repository; copy them again when those change.

## Documentation (guardspec.io/docs)

The docs are the Markdown of
[guard-spec/guard-spec](https://github.com/guard-spec/guard-spec), rendered
here; nothing is copied or edited by hand. Change a page in the main
repository, not here.

- **Pinned source.** `ref` in `src/docs.json` is a commit (or tag) of the
  main repository. `build.py` fetches the files it needs from
  `raw.githubusercontent.com` at that ref (cached in `.cache/`), renders them
  with [mistune](https://github.com/lepture/mistune) (BSD-3-Clause, pinned by
  hash in `requirements.txt`, build time only) and writes static pages. The
  site stays static: no JavaScript is needed to read it.
- **Pages.** Each page in `src/docs.json` names its source per language: a
  whole file, or one `##` section of `README.md` / `README.vi.md`. The first
  candidate that exists at the ref is used, so a page can fall back (Upgrade
  shows `CHANGELOG.md` until `docs/upgrade.md` exists). A page with no source
  at the ref is skipped and `build.py` lists it.
- **Vietnamese.** A page with a Vietnamese source is built under `/vi/docs/`;
  the others appear in the Vietnamese navigation as links to the English page,
  labelled "(tiếng Anh)".
- **Links.** Links between documents go to the matching docs page when there
  is one (including anchors inside README sections), otherwise to the file on
  GitHub at the pinned ref; images load from the pinned ref.
- **Diagrams.** Pages with a ```` ```mermaid ```` block load Mermaid 11.17.2
  (MIT) from jsDelivr, pinned by version and SRI hash; other pages load no
  script.
- **Updating.** Set `ref` to a newer commit of the main repository, run
  `build.py`, check with `check_site.py`, commit. To preview unmerged docs:
  `build.py --source ../guard-spec` (do not commit that output).

CI (`.github/workflows/check.yml`) rebuilds from the pinned ref, fails if
the committed pages differ, and runs `check_site.py --external`.

## Custom domain

The site is served at https://guardspec.io (`CNAME`). `SITE_URL` in
`build.py` must match it. The domain is verified for the `guard-spec`
organization; **Enforce HTTPS** is on.

## License

Apache-2.0, like Guard Spec. Lucide icons are ISC; see [NOTICE](NOTICE).
