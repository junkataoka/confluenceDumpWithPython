#!/usr/bin/env python3
"""
Confluence Export Tool

Export a Confluence page tree (Cloud or Server/Data Center) to HTML/RST.
Authenticates with an API token (CONFLUENCE_EMAIL + CONFLUENCE_API_TOKEN) or,
if no token is set, with browser session cookies (SSO compatible).

Usage:
    python confluence_export.py --site confluence.example.com --page 123456 --html
    python confluence_export.py --site mysite.atlassian.net --page 123456 --html

Requirements:
    Python 3.8+ with: browser_cookie3, requests, beautifulsoup4, pypandoc, Pillow

"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

try:
    import browser_cookie3
    import requests
except ImportError as e:
    print(f"ERROR: Missing required module: {e}")
    print(
        "Install with: pip install browser-cookie3 requests beautifulsoup4 pypandoc Pillow"
    )
    sys.exit(1)

import confluence_api
import myModules


class ConfluenceExporter:
    """Export Confluence pages with hierarchical structure and concurrent processing."""

    def __init__(self, site: str, session: requests.Session):
        self.site = site
        self.base_url = confluence_api.build_base_url(site)
        self.session = session
        self.user_name = ""  # Empty string for session-based auth
        self.api_token = session  # Session object acts as auth token

    def _get_child_pages(self, page_id: str, indent: str = "") -> List[Dict[str, Any]]:
        """Return all direct child pages of a page, following pagination."""
        children: List[Dict[str, Any]] = []
        url = f"{self.base_url}/rest/api/content/{page_id}/child/page?limit=100"
        while url:
            try:
                response = confluence_api.make_request(
                    url, self.user_name, self.api_token, timeout=30
                )
            except Exception as e:
                print(
                    f"{indent}✗ Network error fetching children for page {page_id}: {e}"
                )
                break
            if response.status_code != 200:
                print(
                    f"{indent}✗ Failed to fetch children for page {page_id}: "
                    f"HTTP {response.status_code}"
                )
                if response.status_code == 429:
                    print(f"{indent}  Rate limited - reduce --workers")
                break
            try:
                data = response.json()
            except ValueError:
                print(
                    f"{indent}✗ Non-JSON children response for page {page_id} "
                    f"({response.headers.get('Content-Type', 'unknown')}): "
                    f"{response.text[:200]}"
                )
                break
            children.extend(data.get("results", []))
            next_link = data.get("_links", {}).get("next")
            url = f"{self.base_url}{next_link}" if next_link else None
        return children

    def get_page_tree(
        self, root_page_id: str, max_workers: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Recursively fetch page tree starting from root page.

        Args:
            root_page_id: ID of the root page
            max_workers: Number of concurrent workers for fetching

        Returns:
            List of page dictionaries with id, title, body, level, parent_id
        """

        def fetch_children(page_id: str, level: int = 0) -> List[Dict[str, Any]]:
            """Fetch page and all its children recursively."""
            pages = []
            indent = "  " * level

            # Fetch page content
            response = confluence_api.get_body_export_view(
                self.site, page_id, self.user_name, self.api_token
            )

            # Check response status before parsing JSON
            if response.status_code != 200:
                print(
                    f"{indent}✗ Failed to fetch page {page_id}: HTTP {response.status_code}"
                )
                print(
                    f"{indent}  Response content (first 200 chars): {response.text[:200]}"
                )
                if response.status_code == 429:
                    print(f"{indent}  Rate limited - reduce --workers or add delays")
                return []

            try:
                page_body = response.json()
            except Exception as e:
                print(f"{indent}✗ Invalid JSON response for page {page_id}: {e}")
                print(f"{indent}  Status code: {response.status_code}")
                print(
                    f"{indent}  Content-Type: {response.headers.get('Content-Type', 'unknown')}"
                )
                print(
                    f"{indent}  Response content (first 500 chars): {response.text[:500]}"
                )
                return []

            page_title = page_body["title"]
            print(f"{indent}├─ {page_title} (ID: {page_id})")

            pages.append(
                {
                    "id": page_id,
                    "title": page_title,
                    "body": page_body,
                    "level": level,
                    "parent_id": None,
                }
            )

            child_pages = self._get_child_pages(page_id, indent)
            if child_pages:
                print(f"{indent}│  ({len(child_pages)} children)")

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [
                        executor.submit(fetch_children, child["id"], level + 1)
                        for child in child_pages
                    ]
                    for future in futures:
                        child_pages_list = future.result()
                        for cp in child_pages_list:
                            if cp["level"] == level + 1 and cp["parent_id"] is None:
                                cp["parent_id"] = page_id
                        pages.extend(child_pages_list)

            return pages

        print("Fetching page tree...")
        start_time = time.time()
        all_pages = fetch_children(root_page_id)
        elapsed = time.time() - start_time

        print(f"\n✓ Fetched {len(all_pages)} pages in {elapsed:.2f}s")
        return all_pages

    def build_folder_structure(self, pages: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Build hierarchical folder paths for pages based on parent-child relationships.

        Args:
            pages: List of page dictionaries

        Returns:
            Dictionary mapping page_id -> relative folder path
        """
        page_paths = {}

        def get_path(page_id: str) -> str:
            """Recursively build path for a page."""
            if page_id in page_paths:
                return page_paths[page_id]

            page = next((p for p in pages if p["id"] == page_id), None)
            if not page or page["parent_id"] is None:
                page_paths[page_id] = ""
                return ""

            parent_path = get_path(page["parent_id"])

            # Sanitize title for folder name
            clean_title = (
                page["title"]
                .replace("/", "-")
                .replace(",", "")
                .replace("&", "And")
                .replace(":", "-")
                .replace(" ", "_")
            )
            page_folder = f"{page['id']}-{clean_title}"

            page_paths[page_id] = (
                os.path.join(parent_path, page_folder) if parent_path else page_folder
            )
            return page_paths[page_id]

        # Build paths for all pages
        for page in pages:
            get_path(page["id"])

        return page_paths

    def export_pages(
        self,
        pages: List[Dict[str, Any]],
        page_paths: Dict[str, str],
        base_dir: str,
        sphinx: bool,
        html_output: bool,
        rst_output: bool,
        max_workers: int = 5,
    ):
        """
        Export all pages concurrently to HTML/RST with proper folder structure.

        Args:
            pages: List of page dictionaries
            page_paths: Mapping of page_id to folder path
            base_dir: Base output directory
            sphinx: Sphinx compatibility mode
            html_output: Export HTML files
            rst_output: Export RST files
            max_workers: Number of concurrent workers
        """

        def export_single(page: Dict[str, Any], page_num: int):
            """Export a single page to HTML/RST."""
            page_body = page["body"]
            page_html = page_body["body"]["export_view"]["value"]

            # Sanitize title for filename
            page_title = (
                page_body["title"]
                .replace("/", "-")
                .replace(",", "")
                .replace("&", "And")
                .replace(":", "-")
                .replace(" ", "_")
            )
            page_id = page["id"]

            # Determine output folder based on hierarchy
            if page["level"] == 0:
                # Root page goes in base directory
                page_outdir = base_dir
            else:
                # Child pages go in nested folders
                parent_path = page_paths.get(page["parent_id"], "")
                page_outdir = (
                    os.path.join(base_dir, parent_path) if parent_path else base_dir
                )
                os.makedirs(page_outdir, exist_ok=True)

            print(f"[{page_num}/{len(pages)}] {page['title']}")

            # Fetch page metadata
            page_labels = confluence_api.get_page_labels(
                self.site, page_id, self.user_name, self.api_token
            )
            page_parent = confluence_api.get_page_parent(
                self.site, page_id, self.user_name, self.api_token
            )

            # Export to HTML/RST
            myModules.dump_html(
                self.site,
                page_html,
                page_title,
                page_id,
                base_dir,
                page_outdir,
                page_labels,
                page_parent,
                self.user_name,
                self.api_token,
                sphinx,
                arg_html_output=html_output,
                arg_rst_output=rst_output,
            )

        print("\nExporting pages...")
        start_time = time.time()

        # Export all pages concurrently
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for idx, page in enumerate(pages, 1):
                future = executor.submit(export_single, page, idx)
                futures.append(future)

            # Wait for all exports to complete
            for future in futures:
                future.result()

        elapsed = time.time() - start_time
        print(f"\n✓ Exported {len(pages)} pages in {elapsed:.2f}s")


BROWSERS = {
    "chrome": browser_cookie3.chrome,
    "edge": browser_cookie3.edge,
    "firefox": browser_cookie3.firefox,
    "safari": browser_cookie3.safari,
}


def _cookie_matches(cookie_domain: str, host: str) -> bool:
    cookie_domain = cookie_domain.lstrip(".")
    return host == cookie_domain or host.endswith("." + cookie_domain)


def get_browser_session(host: str, browser: str = "auto") -> requests.Session:
    """
    Extract authenticated session from browser cookies.

    Args:
        host: Confluence host name (e.g. confluence.example.com or x.atlassian.net)
        browser: Browser name from BROWSERS, or "auto" to try all of them

    Returns:
        requests.Session carrying the browser's cookies for the host

    Raises:
        Exception: If cookies cannot be loaded from any browser
    """
    # Atlassian Cloud session cookies are set on the parent ".atlassian.net"
    # domain, which browser_cookie3's substring filter would miss for the full host.
    lookup_domain = "atlassian.net" if host.endswith(".atlassian.net") else host
    names = list(BROWSERS) if browser == "auto" else [browser]

    for name in names:
        try:
            jar = BROWSERS[name](domain_name=lookup_domain)
        except Exception as e:
            print(f"  {name}: could not read cookies ({e})")
            continue
        session = requests.Session()
        for cookie in jar:
            if _cookie_matches(cookie.domain, host):
                session.cookies.set_cookie(cookie)
        if len(session.cookies) == 0:
            print(f"  {name}: no cookies for {host}")
            continue
        print(f"✓ Loaded {len(session.cookies)} cookies for {host} from {name}")
        return session

    raise Exception(
        "Could not load cookies from any browser. Make sure you're logged into Confluence."
    )


def get_token_session(email: str, token: str) -> requests.Session:
    """Session using an API token (Cloud: email + API token; Server/DC: PAT)."""
    session = requests.Session()
    if email:
        session.auth = (email, token)
    else:
        session.headers["Authorization"] = f"Bearer {token}"
    return session


def test_authentication(session: requests.Session, site: str) -> bool:
    """Test if session is authenticated.

    Args:
        session: Requests session with cookies or token auth
        site: Confluence site

    Returns:
        True if authenticated, False otherwise
    """
    test_url = f"{confluence_api.build_base_url(site)}/rest/api/space?limit=1"
    try:
        response = confluence_api.make_request(test_url, "", session, timeout=10)
        if response.status_code == 200:
            # Also verify we get valid JSON, not an HTML login page
            try:
                response.json()
                return True
            except ValueError:
                print(
                    "WARNING: Got HTTP 200 but invalid JSON - likely redirected to login page"
                )
                print(f"Response content (first 200 chars): {response.text[:200]}")
                return False
        else:
            print(f"Authentication test failed: HTTP {response.status_code}")
            print(f"Response content (first 200 chars): {response.text[:200]}")
            return False
    except Exception as e:
        print(f"Authentication test error: {e}")
        return False


def main():
    """Main entry point for the Confluence export tool."""
    parser = argparse.ArgumentParser(
        description="Export Confluence pages (Cloud or Server/DC) to HTML/RST",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export single page with children (Server/DC, browser SSO cookies)
  %(prog)s --site confluence.example.com --page 123456 --html

  # Atlassian Cloud with an API token, fixing internal links afterwards
  CONFLUENCE_EMAIL=me@example.com CONFLUENCE_API_TOKEN=... \\
  %(prog)s --site mysite.atlassian.net --page 123456 --html --fix-links
        """,
    )

    parser.add_argument(
        "--site",
        "-S",
        type=str,
        required=True,
        help="Confluence site or any URL on it (e.g. confluence.example.com, mysite.atlassian.net)",
    )
    parser.add_argument("--page", "-p", type=str, help="Page ID")
    parser.add_argument(
        "--outdir",
        "-o",
        type=str,
        default="output",
        help="Output directory (default: output)",
    )
    parser.add_argument(
        "--sphinx", "-x", action="store_true", help="Sphinx compatible folder structure"
    )
    parser.add_argument(
        "--html", action="store_true", help="Include HTML files in export"
    )
    parser.add_argument(
        "--no-rst",
        action="store_false",
        dest="rst",
        default=True,
        help="Disable RST file generation",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Number of concurrent workers (default: 2, reduce if you hit rate limits)",
    )
    parser.add_argument(
        "--browser",
        choices=["auto", *BROWSERS],
        default="auto",
        help="Browser to read SSO cookies from (default: auto = try all)",
    )
    parser.add_argument(
        "--fix-links",
        action="store_true",
        help="Rewrite internal Confluence links to relative file paths after export",
    )

    args = parser.parse_args()

    # Validate required arguments
    if not args.page:
        parser.error("--page is required")
    if args.fix_links and not args.html:
        parser.error("--fix-links requires --html (page IDs are read from HTML files)")

    site = args.site
    host = confluence_api.get_host(site)
    print("Confluence Export Tool")
    print(f"Site: {confluence_api.build_base_url(site)}")
    print("=" * 70)
    print()

    # Token auth (env vars) takes precedence over browser cookies
    api_token = os.environ.get("CONFLUENCE_API_TOKEN")
    if api_token:
        email = os.environ.get("CONFLUENCE_EMAIL", "")
        print(f"Using API token auth{f' for {email}' if email else ' (Bearer PAT)'}")
        session = get_token_session(email, api_token)
    else:
        try:
            session = get_browser_session(host, args.browser)
        except Exception as e:
            print(f"ERROR: {e}")
            print(
                "\nLog into Confluence in your browser, or set CONFLUENCE_EMAIL and "
                "CONFLUENCE_API_TOKEN."
            )
            sys.exit(1)

    if not test_authentication(session, site):
        print("ERROR: Authentication failed.")
        sys.exit(1)

    print("✓ Authentication successful")
    print()

    exporter = ConfluenceExporter(site, session)
    pages = exporter.get_page_tree(args.page, max_workers=args.workers)
    if not pages:
        print(f"ERROR: Could not fetch page {args.page}")
        sys.exit(1)

    page_paths = exporter.build_folder_structure(pages)

    # Create base directory
    root_title = (
        pages[0]["title"]
        .replace("/", "-")
        .replace(",", "")
        .replace("&", "And")
        .replace(":", "-")
    )
    base_dir = os.path.join(args.outdir, f"{args.page}-{root_title}")
    myModules.mk_outdirs(base_dir)

    print(f"\nOutput: {base_dir}")

    # Export all pages
    exporter.export_pages(
        pages,
        page_paths,
        base_dir,
        args.sphinx,
        args.html,
        args.rst,
        max_workers=args.workers,
    )

    if args.fix_links:
        from fix_confluence_links import ConfluenceLinkFixer

        print("\nFixing internal links...")
        fixer = ConfluenceLinkFixer(base_dir)
        fixer.scan_files()
        fixer.process_all_files()
        fixer.print_summary()

    print("\n✓ Export complete!")


if __name__ == "__main__":
    main()
