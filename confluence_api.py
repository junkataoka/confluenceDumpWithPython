"""Confluence API client functions."""

import time
from random import uniform

import requests


def get_auth_headers(arg_username, arg_api_token):
    """Build authentication headers.

    Args:
        arg_username: Username for auth (empty string for PAT)
        arg_api_token: API token or PAT token

    Returns:
        Dictionary of headers for authentication
    """
    if arg_username == "" or arg_username is None:
        return {"Authorization": f"Bearer {arg_api_token}"}
    else:
        return {}


def make_request(url, arg_username, arg_api_token, **kwargs):
    """Make an authenticated request with retry logic.

    Args:
        url: URL to request
        arg_username: Username for auth
        arg_api_token: API token or PAT
        **kwargs: Additional arguments for requests.get

    Returns:
        requests.Response object
    """
    max_retries = 10
    base_delay = 3.0  # Start with 3 second delay for rate limiting

    for attempt in range(max_retries):
        try:
            # Add delay on retries to avoid rate limiting
            if attempt > 0:
                delay = base_delay * (
                    2 ** (attempt - 1)
                )  # Exponential: 3s, 6s, 12s, 24s...
                print(f"  Waiting {delay}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(delay)
            else:
                # Small jitter on first attempt to spread out concurrent requests
                time.sleep(uniform(0.05, 0.15))

            # Check if arg_api_token is actually a requests.Session object
            if hasattr(arg_api_token, "get") and hasattr(arg_api_token, "cookies"):
                response = arg_api_token.get(url, **kwargs)
            else:
                auth_headers = get_auth_headers(arg_username, arg_api_token)
                if auth_headers:
                    if "headers" in kwargs:
                        kwargs["headers"].update(auth_headers)
                    else:
                        kwargs["headers"] = auth_headers
                    response = requests.get(url, **kwargs)
                else:
                    response = requests.get(
                        url, auth=(arg_username, arg_api_token), **kwargs
                    )

            # Check for rate limiting
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    print(
                        f"  Rate limited (429). Will retry with exponential backoff..."
                    )
                    continue
                else:
                    print(f"  Rate limited (429) after {max_retries} attempts")
                    return response

            # Success - return response
            return response

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                print(f"  Request failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"  Request failed after {max_retries} attempts: {e}")
                raise

    # Should never reach here, but just in case
    raise Exception(f"Failed to complete request to {url} after {max_retries} attempts")


def build_base_url(arg_site):
    """Build the base URL for Confluence API calls.

    Args:
        arg_site: Site name (subdomain for *.atlassian.net or full domain for custom)

    Returns:
        Base URL for the Confluence instance
    """
    site = arg_site.replace("https://", "").replace("http://", "")

    if "." in site and not site.endswith(".atlassian.net"):
        return f"https://{site}"
    elif ".atlassian.net" in site:
        return f"https://{site}"
    else:
        return f"https://{site}.atlassian.net"


def get_space_title(arg_site, arg_space_id, arg_username, arg_api_token):
    """Get title of a Confluence space.

    Args:
        arg_site: The site name
        arg_space_id: ID of the space
        arg_username: Username for auth
        arg_api_token: API token for auth

    Returns:
        Space title string
    """
    base_url = build_base_url(arg_site)
    server_url = f"{base_url}/rest/api/space/{arg_space_id}"
    response = make_request(server_url, arg_username, arg_api_token, timeout=30)
    response.raise_for_status()
    response = response.json()["name"]
    return response


def get_spaces_all(arg_site, arg_username, arg_api_token):
    """Get all spaces from Confluence instance.

    Args:
        arg_site: The site name
        arg_username: Username for auth
        arg_api_token: API token for auth

    Returns:
        List of space dictionaries
    """
    base_url = build_base_url(arg_site)
    server_url = f"{base_url}/rest/api/space?limit=250"
    response = make_request(server_url, arg_username, arg_api_token, timeout=30)
    response.raise_for_status()
    space_list = response.json()["results"]

    # Handle pagination
    while "next" in response.json()["_links"].keys():
        next_url = f"{base_url}{response.json()['_links']['next']}"
        response = make_request(next_url, arg_username, arg_api_token, timeout=30)
        space_list = space_list + response.json()["results"]

    return space_list


def get_pages_from_space(arg_site, arg_space_id, arg_username, arg_api_token):
    """Get all pages from a Confluence space.

    Args:
        arg_site: The site name
        arg_space_id: ID of the space
        arg_username: Username for auth
        arg_api_token: API token for auth

    Returns:
        List of page dictionaries
    """
    page_list = []
    base_url = build_base_url(arg_site)
    server_url = f"{base_url}/rest/api/space/{arg_space_id}/content/page?limit=250&expand=ancestors,space"
    response = make_request(server_url, arg_username, arg_api_token, timeout=30)
    response_data = response.json()

    # V1 API returns pages in page.results
    page_list = response_data.get("page", {}).get("results", [])

    # Handle pagination
    page_data = response_data.get("page", {})
    while "next" in page_data.get("_links", {}).keys():
        next_url = f"{base_url}{page_data['_links']['next']}"
        response = make_request(next_url, arg_username, arg_api_token, timeout=30)
        response_data = response.json()
        page_data = response_data.get("page", {})
        page_list = page_list + page_data.get("results", [])

    return page_list


def get_body_export_view(arg_site, arg_page_id, arg_username, arg_api_token):
    """Get page body in export view format.

    Args:
        arg_site: The site name
        arg_page_id: Page ID
        arg_username: Username for auth
        arg_api_token: API token for auth

    Returns:
        Response object with page body
    """
    base_url = build_base_url(arg_site)
    server_url = f"{base_url}/rest/api/content/{arg_page_id}?expand=body.export_view"
    response = make_request(server_url, arg_username, arg_api_token)
    return response


def get_page_name(arg_site, arg_page_id, arg_username, arg_api_token):
    """Get page name formatted as 'ID_Title'.

    Args:
        arg_site: The site name
        arg_page_id: Page ID
        arg_username: Username for auth
        arg_api_token: API token for auth

    Returns:
        Formatted page name string
    """
    base_url = build_base_url(arg_site)
    server_url = f"{base_url}/rest/api/content/{arg_page_id}"
    r_pagetree = make_request(server_url, arg_username, arg_api_token, timeout=30)
    page_data = r_pagetree.json()
    return f"{page_data['id']}_{page_data['title']}"


def get_page_parent(arg_site, arg_page_id, arg_username, arg_api_token):
    """Get parent page ID.

    Args:
        arg_site: The site name
        arg_page_id: Page ID
        arg_username: Username for auth
        arg_api_token: API token for auth

    Returns:
        Parent page ID or None if no parent
    """
    base_url = build_base_url(arg_site)
    server_url = f"{base_url}/rest/api/content/{arg_page_id}"
    response = make_request(server_url, arg_username, arg_api_token, timeout=30)
    # V1 API returns ancestors array, get the last one's id
    ancestors = response.json().get("ancestors", [])
    return ancestors[-1]["id"] if ancestors else None


def get_page_labels(arg_site, arg_page_id, arg_username, arg_api_token):
    """Get all labels for a page.

    Args:
        arg_site: The site name
        arg_page_id: Page ID
        arg_username: Username for auth
        arg_api_token: API token for auth

    Returns:
        Comma-separated string of label names
    """
    html_labels = []
    base_url = build_base_url(arg_site)
    server_url = f"{base_url}/rest/api/content/{arg_page_id}/label"
    response = make_request(server_url, arg_username, arg_api_token, timeout=30).json()

    for l in response["results"]:
        html_labels.append(l["name"])
        print(f"Label: {l['name']}")

    html_labels = ", ".join(html_labels)
    print(f"Page labels: {html_labels}")
    return html_labels


def get_editor_version(arg_site, arg_page_id, arg_username, arg_api_token):
    """Get editor version metadata for a page.

    Args:
        arg_site: The site name
        arg_page_id: Page ID
        arg_username: Username for auth
        arg_api_token: API token for auth

    Returns:
        Response object with editor metadata
    """
    base_url = build_base_url(arg_site)
    server_url = (
        f"{base_url}/rest/api/content/{arg_page_id}?expand=metadata.properties.editor"
    )
    response = make_request(server_url, arg_username, arg_api_token)
    return response


def find_attachment_by_filename(
    arg_site, arg_page_id, filename, arg_username, arg_api_token
):
    """Find attachment download URL by searching for filename on page.

    Args:
        arg_site: The site name
        arg_page_id: Page ID to search
        filename: Name of the attachment file
        arg_username: Username for auth
        arg_api_token: API token for auth

    Returns:
        Download URL if found, None otherwise
    """
    try:
        base_url = build_base_url(arg_site)
        server_url = f"{base_url}/rest/api/content/{arg_page_id}/child/attachment?limit=250"
        response = make_request(server_url, arg_username, arg_api_token, timeout=30)

        if response.status_code == 200:
            response_data = response.json()
            attachments = response_data.get("results", [])

            # Handle pagination - keep fetching until we find the file or run out of pages
            while True:
                for attachment in attachments:
                    if attachment["title"] == filename:
                        download_path = attachment["_links"].get("download")
                        if download_path:
                            return f"{base_url}{download_path}"
                
                # Check if there are more pages
                if "next" in response_data.get("_links", {}):
                    next_url = f"{base_url}{response_data['_links']['next']}"
                    response = make_request(next_url, arg_username, arg_api_token, timeout=30)
                    if response.status_code == 200:
                        response_data = response.json()
                        attachments = response_data.get("results", [])
                    else:
                        break
                else:
                    break

        return None
    except Exception as e:
        print(f"  Error searching for attachment: {e}")
        return None
