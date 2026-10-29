# Confluence Export Tool

Export a Confluence page and all of its children to HTML and/or RST (Sphinx compatible),
including images, attachments, and emoticons, preserving the page hierarchy as folders.

Works with **Atlassian Cloud** (`*.atlassian.net`) and **Server / Data Center**.

## Features

- **Cloud and Server/DC** – Cloud's `/wiki` context path is handled automatically
- **Two auth modes** – API token (recommended for Cloud) or browser SSO cookies (Azure AD, Okta, SAML…)
- **Hierarchical export** – parent → child → grandchild folders
- **Concurrent processing** with retry/backoff on rate limiting (HTTP 429)
- **Complete content** – images, attachments, emoticons, CSS
- **Internal link fixing** – rewrite Confluence page links to relative file paths

## Setup

Requires Python 3.10+ and [Pandoc](https://pandoc.org/) (for RST output).

```bash
pip install -r requirements.txt

brew install pandoc              # macOS
sudo apt-get install pandoc      # Ubuntu/Debian
choco install pandoc             # Windows
```

## Authentication

### Option 1: API token (Atlassian Cloud, or PAT on Server/DC)

```bash
# Cloud: create a token at https://id.atlassian.com/manage-profile/security/api-tokens
export CONFLUENCE_EMAIL=you@example.com
export CONFLUENCE_API_TOKEN=your-api-token

# Server/DC Personal Access Token: set only the token (sent as a Bearer token)
export CONFLUENCE_API_TOKEN=your-pat
```

If `CONFLUENCE_API_TOKEN` is set it is always used.

### Option 2: Browser session cookies (SSO)

If no token is set, the tool reads your session cookies from a browser where you are
logged into Confluence. Use `--browser chrome|edge|firefox|safari` to pick one
(default `auto` tries all). On macOS, your terminal may need **Full Disk Access**
(System Settings → Privacy & Security) and Keychain access to read browser cookies.

## Usage

```bash
# Atlassian Cloud (the site may also be any URL on the site)
python confluence_export.py --site mysite.atlassian.net --page 123456 --html

# Server / Data Center
python confluence_export.py --site confluence.example.com --page 123456 --html

# Export and rewrite internal links to local files
python confluence_export.py --site mysite.atlassian.net --page 123456 --html --fix-links
```

### Options

```
Required:
  --site, -S     Confluence site or any URL on it (mysite.atlassian.net, confluence.example.com)
  --page, -p     Root page ID (exported with all descendants)

Optional:
  --outdir, -o   Output directory (default: output)
  --sphinx, -x   Sphinx compatible folder structure
  --html         Keep HTML files in the export
  --no-rst       Disable RST file generation
  --workers      Concurrent workers (default: 2; lower it if you hit rate limits)
  --browser      Browser for SSO cookies: auto, chrome, edge, firefox, safari (default: auto)
  --fix-links    Rewrite internal page links to relative paths (requires --html)
```

### Finding a page ID

- Cloud: `https://mysite.atlassian.net/wiki/spaces/KEY/pages/123456/Title` → `123456`
- Server/DC: `.../pages/viewpage.action?pageId=123456`, or **••• → Page Information**

## Output structure

```
output/123456-Page_Title/
├── _images/                    # All images (shared, not duplicated)
├── _static/                    # CSS
├── Page_Title.html             # Root page
├── Page_Title.rst
├── Child_Page.html             # Children of the root page
├── Child_Page.rst
└── 234567-Child_Page/          # Children of Child_Page
    ├── Grandchild.html         # Uses ../_images/...
    └── Grandchild.rst
```

Each page is written to its parent's folder; a page's own children go in a
`<id>-<title>/` subfolder next to it.

Page ID, labels, and parent ID are stored in HTML `<meta>` tags and RST fields.

## Fixing internal links

Links between exported pages still point at Confluence after export. Fix them either
with `--fix-links` during export, or afterwards:

```bash
python fix_confluence_links.py --dry-run "output/123456-Page_Title"   # preview
python fix_confluence_links.py "output/123456-Page_Title"             # apply
```

The fixer maps page IDs (from the HTML `<meta name="ConfluencePageID">` tags, so the
export must include `--html`) to files and rewrites these link forms in HTML and RST:

- `/spaces/KEY/pages/ID/...` and `/wiki/spaces/KEY/pages/ID/...`
- absolute Cloud URLs, e.g. `https://mysite.atlassian.net/wiki/spaces/KEY/pages/ID`
- `viewpage.action?pageId=ID`

Links to pages outside the export are left unchanged and reported as missing.

## Project layout

| File | Purpose |
|---|---|
| `confluence_export.py` | CLI entry point: auth, page-tree fetch, concurrent export |
| `confluence_api.py` | REST API helpers (URLs, retries, labels, attachments) |
| `confluence_download.py` | File download with fallback strategies |
| `myModules.py` | HTML processing, asset download, HTML/RST writing |
| `fix_confluence_links.py` | Internal link rewriting (also used by `--fix-links`) |
| `styles/` | CSS bundled into exports |
| `tools/` | Ad-hoc diagnostic scripts for cookie/API debugging |
| `tests/` | Unit tests: `python -m unittest discover -s tests` |

## Troubleshooting

- **Authentication failed / HTTP 401/403** – token wrong or expired; for cookies, open a
  Confluence page in the browser first, then rerun.
- **Could not load cookies** – log in, try another `--browser`, grant Full Disk Access, or
  use an API token instead.
- **HTTP 429** – lower `--workers`; requests are retried with exponential backoff.
- **Images broken in HTML** – open files in place; paths are relative to `_images/`.
- **Long attachment filenames / old Server emoticons** may fail to download.

## Authors

Original: @dernorberto. SSO and Cloud support: modified 2025–2026.

## License

MIT – see [LICENSE.txt](LICENSE.txt).
