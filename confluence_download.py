"""Confluence file download with fallback strategies."""

import requests

from confluence_api import (build_base_url, find_attachment_by_filename,
                            make_request)


def download_with_fallback(
    url, filename, arg_site, arg_page_id, arg_username, arg_api_token, use_auth=True
):
    """Download a file with automatic fallback strategies.

    Tries multiple strategies to successfully download:
    1. Direct URL download
    2. Search on current page via API
    3. Search on source page (extracted from URL) via API

    Args:
        url: URL to download from
        filename: Name of the file to download
        arg_site: Site name
        arg_page_id: Current page ID
        arg_username: Username for auth
        arg_api_token: API token for auth
        use_auth: Whether to use authentication (False for external URLs)

    Returns:
        Tuple of (success: bool, response: requests.Response or None, message: str)
    """

    def is_valid_download(response):
        """Check if response is a valid download (not HTML error page)."""
        if response.status_code != 200 or len(response.content) == 0:
            return False
        content_type = response.headers.get("Content-Type", "").lower()
        if (
            "html" in content_type
            or response.content.startswith(b"<!DOCTYPE")
            or response.content.startswith(b"<html")
        ):
            return False
        return True

    # Strategy 1: Try original URL
    try:
        if use_auth:
            response = make_request(
                url, arg_username, arg_api_token, allow_redirects=True
            )
        else:
            response = requests.get(url, allow_redirects=True)

        if is_valid_download(response):
            return (True, response, "Downloaded from original URL")

        # Log why it failed
        failure_reason = f"HTTP {response.status_code}"
        content_type = response.headers.get("Content-Type", "").lower()
        if "html" in content_type:
            failure_reason += ", returned HTML instead of file"

    except Exception as e:
        failure_reason = f"Request failed: {e}"

    print(f"WARNING: Failed to download {filename}: {failure_reason}")
    print(f"  URL: {url}")

    # Only try API fallback for Confluence attachments
    if "/download/attachments/" not in url:
        return (False, None, "Not a Confluence attachment URL")

    # Strategy 2: Search on current page
    print(f"  Trying API fallback on current page...")
    fallback_url = find_attachment_by_filename(
        arg_site, arg_page_id, filename, arg_username, arg_api_token
    )

    if not fallback_url:
        print(f"  Attachment '{filename}' not found on current page {arg_page_id}")
    else:
        try:
            if use_auth:
                response = make_request(
                    fallback_url, arg_username, arg_api_token, allow_redirects=True
                )
            else:
                response = requests.get(fallback_url, allow_redirects=True)

            if is_valid_download(response):
                print(f"  ✓ Downloaded via API from current page")
                return (True, response, "Downloaded via API from current page")
        except Exception as e:
            pass

    # Strategy 3: Extract page ID from URL and search there
    try:
        # Handle both standard and embedded-page URL formats
        if "/download/attachments/embedded-page/" in url:
            # For embedded-page URLs, we can't extract a page ID
            # These attachments might be on a page related to the space/title in the URL
            # Skip this strategy for embedded-page URLs
            pass
        elif "/download/attachments/" in url:
            url_parts = url.split("/download/attachments/")[1]
            url_page_id = url_parts.split("/")[0]

            if url_page_id.isdigit() and url_page_id != str(arg_page_id):
                print(f"  Trying API fallback on source page {url_page_id}...")
                fallback_url = find_attachment_by_filename(
                    arg_site, url_page_id, filename, arg_username, arg_api_token
                )

                if fallback_url:
                    try:
                        if use_auth:
                            response = make_request(
                                fallback_url,
                                arg_username,
                                arg_api_token,
                                allow_redirects=True,
                            )
                        else:
                            response = requests.get(fallback_url, allow_redirects=True)

                        if is_valid_download(response):
                            print(
                                f"  ✓ Downloaded via API from source page {url_page_id}"
                            )
                            return (
                                True,
                                response,
                                f"Downloaded via API from source page {url_page_id}",
                            )
                    except Exception as e:
                        pass
    except Exception:
        pass

    return (False, None, "All fallback strategies failed")
