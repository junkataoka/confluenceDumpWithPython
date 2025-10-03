#!/usr/bin/env python3
"""
Confluence Export Tool with SSO Support

A tool to export Confluence pages with Azure AD SSO authentication.
Uses browser session cookies for authentication.

Usage:
    # Export a single page and its children
    python confluence_export.py --site confluence.example.com --page 123456 --html

Requirements:
    - Python 3.8+
    - browser_cookie3
    - requests
    - beautifulsoup4
    - pypandoc
    - Pillow

Author: Modified for SSO support
Date: 2025
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
    """Main exporter class for Confluence content"""

    def __init__(self, site: str, session: requests.Session):
        self.site = site.replace("https://", "").replace("http://", "")
        self.session = session
        self.user_name = ""  # Empty for session-based auth
        self.api_token = session  # Pass session as token

    def get_page_tree(
        self, root_page_id: str, max_workers: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Recursively fetch all pages starting from root page

        Args:
            root_page_id: ID of the root page
            max_workers: Number of concurrent workers for fetching

        Returns:
            List of page dictionaries with metadata
        """

        def fetch_children(page_id: str, level: int = 0) -> List[Dict[str, Any]]:
            """Recursively fetch page and its children"""
            pages = []
            indent = "  " * level

            # Get page info
            page_body = myModules.get_body_export_view(
                self.site, page_id, self.user_name, self.api_token
            ).json()

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

            # Get children
            children_url = (
                f"https://{self.site}/rest/api/content/{page_id}/child/page?limit=250"
            )
            children_response = self.session.get(children_url, timeout=30)

            if children_response.status_code == 200:
                children_data = children_response.json()
                child_pages = children_data.get("results", [])

                if child_pages:
                    print(f"{indent}│  ({len(child_pages)} children)")

                    # Fetch all children concurrently
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = []
                        for child in child_pages:
                            child_id = child["id"]
                            future = executor.submit(
                                fetch_children, child_id, level + 1
                            )
                            futures.append((child_id, future))

                        # Collect results
                        for child_id, future in futures:
                            child_pages_list = future.result()
                            # Set parent IDs
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
        Build hierarchical folder paths for pages

        Args:
            pages: List of page dictionaries

        Returns:
            Dictionary mapping page_id to folder path
        """
        page_paths = {}

        def get_path(page_id: str) -> str:
            if page_id in page_paths:
                return page_paths[page_id]

            page = next((p for p in pages if p["id"] == page_id), None)
            if not page or page["parent_id"] is None:
                page_paths[page_id] = ""
                return ""

            parent_path = get_path(page["parent_id"])
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

        for page in pages:
            get_path(page["id"])

        return page_paths

    def export_pages(
        self,
        pages: List[Dict[str, Any]],
        page_paths: Dict[str, str],
        base_dir: str,
        sphinx: bool,
        tags: bool,
        html_output: bool,
        rst_output: bool,
        max_workers: int = 5,
    ):
        """
        Export all pages concurrently

        Args:
            pages: List of page dictionaries
            page_paths: Mapping of page_id to folder path
            base_dir: Base output directory
            sphinx: Sphinx compatibility mode
            tags: Add tags to RST
            html_output: Export HTML files
            rst_output: Export RST files
            max_workers: Number of concurrent workers
        """

        def export_single(page: Dict[str, Any], page_num: int):
            """Export a single page"""
            page_body = page["body"]
            page_html = page_body["body"]["export_view"]["value"]
            page_title = (
                page_body["title"]
                .replace("/", "-")
                .replace(",", "")
                .replace("&", "And")
                .replace(":", "-")
                .replace(" ", "_")
            )
            page_id = page["id"]

            # Determine output folder
            if page["level"] == 0:
                page_outdir = base_dir
            else:
                parent_path = page_paths.get(page["parent_id"], "")
                page_outdir = (
                    os.path.join(base_dir, parent_path) if parent_path else base_dir
                )
                os.makedirs(page_outdir, exist_ok=True)

            print(f"[{page_num}/{len(pages)}] {page['title']}")

            # Get metadata
            page_labels = myModules.get_page_labels(
                self.site, page_id, self.user_name, self.api_token
            )
            page_parent = myModules.get_page_parent(
                self.site, page_id, self.user_name, self.api_token
            )

            # Export
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
                tags,
                arg_html_output=html_output,
                arg_rst_output=rst_output,
            )

        print("\nExporting pages...")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for idx, page in enumerate(pages, 1):
                future = executor.submit(export_single, page, idx)
                futures.append(future)

            for future in futures:
                future.result()

        elapsed = time.time() - start_time
        print(f"\n✓ Exported {len(pages)} pages in {elapsed:.2f}s")


def get_browser_session(domain: str) -> requests.Session:
    """
    Extract authenticated session from browser cookies

    Args:
        domain: Confluence domain

    Returns:
        Authenticated requests.Session

    Raises:
        Exception: If cookies cannot be loaded
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
            print(f"✓ Loaded session from {browser_name}")
            return session
        except:
            continue

    raise Exception(
        "Could not load cookies from any browser. Make sure you're logged into Confluence."
    )


def test_authentication(session: requests.Session, domain: str) -> bool:
    """Test if session is authenticated"""
    test_url = f"https://{domain}/rest/api/space"
    try:
        response = session.get(test_url, timeout=10)
        return response.status_code == 200
    except:
        return False


def main():
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
        "--tags", action="store_true", help="Add labels as tags in RST files"
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
        default=5,
        help="Number of concurrent workers (default: 5)",
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
        args.tags,
        args.html,
        args.rst,
        max_workers=args.workers,
    )

    print("\n✓ Export complete!")


if __name__ == "__main__":
    main()
