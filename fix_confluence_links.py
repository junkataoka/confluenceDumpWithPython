#!/usr/bin/env python3
"""
Fix Internal Confluence Links in Exported HTML and RST Files

This script scans all exported HTML and RST files, builds a mapping of
Confluence page IDs to file paths, and converts internal Confluence links
to proper relative file paths.

Requires an export made with --html (page IDs are read from the HTML <meta> tags).
The same fix can be run automatically via `confluence_export.py --fix-links`.

Usage:
    python fix_confluence_links.py [--dry-run] [output_directory]

Example:
    python fix_confluence_links.py --dry-run "output/123456-My Space Home"
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict


class ConfluenceLinkFixer:
    """Fix internal Confluence links in exported HTML and RST files."""

    # Internal page links: /spaces/KEY/pages/ID, /wiki/spaces/..., absolute Cloud
    # URLs, and Server/DC viewpage.action?pageId=ID
    PAGE_ID_RE = re.compile(r"(?:/pages/|[?&]pageId=)(\d+)")
    HTML_LINK_RE = re.compile(
        r'(<a\b[^>]*?\bhref=")([^"]*(?:/pages/\d+|[?&](?:amp;)?pageId=\d+)[^"]*)(")'
    )
    RST_LINK_RE = re.compile(
        r"`([^`<]+?)\s+<([^>]*(?:/pages/\d+|[?&]pageId=\d+)[^>]*)>`__"
    )

    def __init__(self, base_dir: str, dry_run: bool = False):
        """
        Initialize the link fixer.

        Args:
            base_dir: Root directory containing exported files
            dry_run: Report changes without writing files
        """
        self.base_dir = Path(base_dir).resolve()
        self.dry_run = dry_run
        self.page_id_to_path: Dict[str, Path] = {}
        self.stats = {
            "html_files": 0,
            "rst_files": 0,
            "html_links_fixed": 0,
            "rst_links_fixed": 0,
            "broken_links": 0,
        }

    def scan_files(self) -> None:
        """Scan all HTML and RST files to build page ID to file path mapping."""
        print(f"Scanning files in: {self.base_dir}")

        for file_path in self.base_dir.rglob("*.html"):
            if file_path.name.startswith("."):
                continue

            # Read the HTML file to extract page ID
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Extract page ID from meta tag
                match = re.search(
                    r'<meta name="ConfluencePageID" content="(\d+)">', content
                )
                if match:
                    page_id = match.group(1)
                    self.page_id_to_path[page_id] = file_path
                    self.stats["html_files"] += 1
            except Exception as e:
                print(f"Warning: Could not read {file_path}: {e}")

        print(f"Found {self.stats['html_files']} HTML files with page IDs")
        print(f"Page ID mapping contains {len(self.page_id_to_path)} entries\n")

    def extract_page_id_from_url(self, url: str) -> str | None:
        """
        Extract Confluence page ID from URL.

        Args:
            url: URL that may contain a Confluence page ID

        Returns:
            Page ID if found, None otherwise
        """
        match = self.PAGE_ID_RE.search(url.replace("&amp;", "&"))
        if match:
            return match.group(1)
        return None

    def calculate_relative_path(self, from_path: Path, to_path: Path) -> str:
        """
        Calculate relative path from one file to another.

        Args:
            from_path: Source file path
            to_path: Target file path

        Returns:
            Relative path string
        """
        try:
            rel_path = os.path.relpath(to_path, from_path.parent)
            return rel_path
        except ValueError:
            # Files on different drives (Windows)
            return str(to_path)

    def fix_html_links(self, file_path: Path) -> int:
        """
        Fix internal Confluence links in an HTML file.

        Args:
            file_path: Path to HTML file

        Returns:
            Number of links fixed
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return 0

        original_content = content
        links_fixed = 0

        # Find all anchor tags with href attributes
        # Pattern: <a href="/spaces/...">...</a>
        def replace_link(match):
            nonlocal links_fixed
            full_match = match.group(0)
            href = match.group(2)

            # Check if this is an internal Confluence link
            page_id = self.extract_page_id_from_url(href)
            if not page_id:
                return full_match

            # Look up the target file
            if page_id not in self.page_id_to_path:
                print(
                    f"  Warning: Page ID {page_id} not found in exports (in {file_path.name})"
                )
                self.stats["broken_links"] += 1
                return full_match

            target_path = self.page_id_to_path[page_id]
            relative_path = self.calculate_relative_path(file_path, target_path)

            links_fixed += 1
            if self.dry_run:
                print(f"  {file_path.name}: {href} -> {relative_path}")
            return f"{match.group(1)}{relative_path}{match.group(3)}"

        content = self.HTML_LINK_RE.sub(replace_link, content)

        if content != original_content and not self.dry_run:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                print(f"Error writing {file_path}: {e}")
                return 0

        return links_fixed

    def fix_rst_links(self, file_path: Path) -> int:
        """
        Fix internal Confluence links in an RST file.

        Args:
            file_path: Path to RST file

        Returns:
            Number of links fixed
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return 0

        original_content = content
        links_fixed = 0

        # Find RST links with pattern: `Text </spaces/AIP/pages/12345/...>`__
        def replace_rst_link(match):
            nonlocal links_fixed
            full_match = match.group(0)
            link_text = match.group(1)
            url = match.group(2)

            # Check if this is an internal Confluence link
            page_id = self.extract_page_id_from_url(url)
            if not page_id:
                return full_match

            # Look up the target file - need to find corresponding HTML file
            if page_id not in self.page_id_to_path:
                print(
                    f"  Warning: Page ID {page_id} not found in exports (in {file_path.name})"
                )
                self.stats["broken_links"] += 1
                return full_match

            target_html_path = self.page_id_to_path[page_id]

            # Convert to .rst extension
            target_rst_path = target_html_path.with_suffix(".rst")

            # Check if RST file exists, otherwise use HTML
            if target_rst_path.exists():
                target_path = target_rst_path
            else:
                target_path = target_html_path

            relative_path = self.calculate_relative_path(file_path, target_path)

            links_fixed += 1
            if self.dry_run:
                print(f"  {file_path.name}: {url} -> {relative_path}")
            return f"`{link_text} <{relative_path}>`__"

        content = self.RST_LINK_RE.sub(replace_rst_link, content)

        if content != original_content and not self.dry_run:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                print(f"Error writing {file_path}: {e}")
                return 0

        return links_fixed

    def process_all_files(self) -> None:
        """Process all HTML and RST files to fix links."""
        print("Processing HTML files...")
        for file_path in self.base_dir.rglob("*.html"):
            if file_path.name.startswith("."):
                continue

            links_fixed = self.fix_html_links(file_path)
            if links_fixed > 0:
                print(f"  Fixed {links_fixed} links in {file_path.name}")
                self.stats["html_links_fixed"] += links_fixed

        print("\nProcessing RST files...")
        for file_path in self.base_dir.rglob("*.rst"):
            if file_path.name.startswith("."):
                continue

            self.stats["rst_files"] += 1
            links_fixed = self.fix_rst_links(file_path)
            if links_fixed > 0:
                print(f"  Fixed {links_fixed} links in {file_path.name}")
                self.stats["rst_links_fixed"] += links_fixed

    def print_summary(self) -> None:
        """Print summary statistics."""
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"HTML files scanned:       {self.stats['html_files']}")
        print(f"RST files processed:      {self.stats['rst_files']}")
        print(f"HTML links fixed:         {self.stats['html_links_fixed']}")
        print(f"RST links fixed:          {self.stats['rst_links_fixed']}")
        print(
            f"Total links fixed:        {self.stats['html_links_fixed'] + self.stats['rst_links_fixed']}"
        )
        print(f"Broken/missing links:     {self.stats['broken_links']}")
        print("=" * 70)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fix internal Confluence links in exported HTML and RST files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes, then apply them
  %(prog)s --dry-run "output/123456-My Space Home"
  %(prog)s "output/123456-My Space Home"

  # Fix links with explicit path
  %(prog)s /path/to/exported/confluence/files
        """,
    )

    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show which links would change without modifying files",
    )
    parser.add_argument(
        "directory",
        type=str,
        nargs="?",
        default="output",
        help="Root directory containing exported Confluence files (default: output)",
    )

    args = parser.parse_args()

    # Validate directory
    base_dir = Path(args.directory)
    if not base_dir.exists():
        print(f"ERROR: Directory not found: {base_dir}")
        sys.exit(1)

    if not base_dir.is_dir():
        print(f"ERROR: Not a directory: {base_dir}")
        sys.exit(1)

    print("Confluence Link Fixer")
    print("=" * 70)
    print()

    # Create fixer and process files
    fixer = ConfluenceLinkFixer(str(base_dir), dry_run=args.dry_run)
    fixer.scan_files()
    fixer.process_all_files()
    fixer.print_summary()

    if args.dry_run:
        print("\nDry run - no files were modified.")
    else:
        print("\n✓ Link fixing complete!")


if __name__ == "__main__":
    main()
