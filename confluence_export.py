#!/usr/bin/env python3
"""
Confluence Export Tool with SSO Support

Export Confluence pages using browser session cookies (SSO compatible).
Supports Azure AD, Okta, SAML, and other SSO providers.

Usage:
    python confluence_export.py --site confluence.example.com --page 123456 --html

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

import myModules


class ConfluenceExporter:
    """Export Confluence pages with hierarchical structure and concurrent processing."""

    def __init__(self, site: str, session: requests.Session):
        self.site = site.replace("https://", "").replace("http://", "")
        self.session = session
        self.user_name = ""  # Empty string for session-based auth
        self.api_token = session  # Session object acts as auth token

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
            response = myModules.get_body_export_view(
                self.site, page_id, self.user_name, self.api_token
            )
            
            # Check response status before parsing JSON
            if response.status_code != 200:
                print(f"{indent}✗ Failed to fetch page {page_id}: HTTP {response.status_code}")
                print(f"{indent}  Response content (first 200 chars): {response.text[:200]}")
                if response.status_code == 429:
                    print(f"{indent}  Rate limited - reduce --workers or add delays")
                return []
            
            try:
                page_body = response.json()
            except Exception as e:
                print(f"{indent}✗ Invalid JSON response for page {page_id}: {e}")
                print(f"{indent}  Status code: {response.status_code}")
                print(f"{indent}  Content-Type: {response.headers.get('Content-Type', 'unknown')}")
                print(f"{indent}  Response content (first 500 chars): {response.text[:500]}")
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

            # Fetch child pages
            children_url = (
                f"https://{self.site}/rest/api/content/{page_id}/child/page?limit=250"
            )
            try:
                # Use make_request for retry logic
                children_response = myModules.make_request(
                    children_url, self.user_name, self.api_token, timeout=30
                )
            except Exception as e:
                print(f"{indent}✗ Network error fetching children for page {page_id}: {e}")
                return pages

            if children_response.status_code == 200 and children_response.content:
                try:
                    children_data = children_response.json()
                except Exception as e:
                    print(f"{indent}✗ Failed to parse children JSON for page {page_id}: {e}")
                    print(f"{indent}  Status code: {children_response.status_code}")
                    print(f"{indent}  Content-Type: {children_response.headers.get('Content-Type', 'unknown')}")
                    print(f"{indent}  Response content (first 500 chars): {children_response.text[:500]}")
                    return pages
                
                child_pages = children_data.get("results", [])

                if child_pages:
                    print(f"{indent}│  ({len(child_pages)} children)")

                    # Process all children concurrently
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = []
                        for child in child_pages:
                            child_id = child["id"]
                            future = executor.submit(
                                fetch_children, child_id, level + 1
                            )
                            futures.append((child_id, future))

                        # Collect results and set parent IDs
                        for child_id, future in futures:
                            child_pages_list = future.result()
                            for cp in child_pages_list:
                                if cp["level"] == level + 1 and cp["parent_id"] is None:
                                    cp["parent_id"] = page_id
                            pages.extend(child_pages_list)
            else:
                if children_response.status_code != 200:
                    print(f"{indent}✗ Failed to fetch children for page {page_id}: HTTP {children_response.status_code}")
                    if children_response.status_code == 429:
                        print(f"{indent}  Rate limited - reduce --workers or add delays")

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
            page_labels = myModules.get_page_labels(
                self.site, page_id, self.user_name, self.api_token
            )
            page_parent = myModules.get_page_parent(
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


def get_browser_session(domain: str) -> requests.Session:
    """
    Extract authenticated session from browser cookies.

    Tries Chrome, Firefox, Safari, and Edge in order.

    Args:
        domain: Confluence domain

    Returns:
        Authenticated requests.Session

    Raises:
        Exception: If cookies cannot be loaded from any browser
    """
    session = requests.Session()

    for browser_name, browser_func in [
        ("Chrome", browser_cookie3.chrome),
        ("Firefox", browser_cookie3.firefox),
        ("Safari", browser_cookie3.safari),
        ("Edge", browser_cookie3.edge),
    ]:
        try:
            cookies = browser_func(domain_name=domain)
            session.cookies.update(cookies)
            cookie_count = len([c for c in session.cookies if domain in c.domain])
            print(f"✓ Loaded session from {browser_name} ({cookie_count} cookies for {domain})")
            if cookie_count == 0:
                print(f"  WARNING: No cookies found for domain {domain}")
                continue
            return session
        except Exception:
            continue

    raise Exception(
        "Could not load cookies from any browser. Make sure you're logged into Confluence."
    )


def test_authentication(session: requests.Session, domain: str) -> bool:
    """Test if session is authenticated.

    Args:
        session: Requests session with cookies
        domain: Confluence domain

    Returns:
        True if authenticated, False otherwise
    """
    test_url = f"https://{domain}/rest/api/space"
    try:
        # Use make_request for retry logic
        response = myModules.make_request(test_url, "", session, timeout=10)
        if response.status_code == 200:
            # Also verify we get valid JSON, not an HTML login page
            try:
                response.json()
                return True
            except:
                print(f"WARNING: Got HTTP 200 but invalid JSON - likely redirected to login page")
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
        description="Export Confluence pages with SSO authentication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export single page with children
  %(prog)s --site confluence.example.com --page 123456 --html
        """,
    )

    parser.add_argument(
        "--site",
        "-S",
        type=str,
        required=True,
        help="Confluence site (e.g., confluence.example.com)",
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

    args = parser.parse_args()

    # Validate required arguments
    if not args.page:
        parser.error("--page is required")

    # Get authenticated session
    print(f"Confluence Export Tool - SSO Mode")
    print(f"Site: {args.site}")
    print("=" * 70)
    print()

    domain = args.site.replace("https://", "").replace("http://", "")

    try:
        session = get_browser_session(domain)
    except Exception as e:
        print(f"ERROR: {e}")
        print(
            "\nMake sure you're logged into Confluence in your browser (Chrome, Firefox, Safari, or Edge)"
        )
        sys.exit(1)

    # Test authentication
    if not test_authentication(session, domain):
        print(
            "ERROR: Authentication failed. Please login to Confluence in your browser and try again."
        )
        sys.exit(1)

    print("✓ Authentication successful")
    print()

    # Create exporter
    exporter = ConfluenceExporter(domain, session)

    # Export single page and children
    pages = exporter.get_page_tree(args.page, max_workers=args.workers)

    # Build folder structure
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

    print("\n✓ Export complete!")


if __name__ == "__main__":
    main()
