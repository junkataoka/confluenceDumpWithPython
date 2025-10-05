import json
import os.path
import re
import shutil
import sys

import pypandoc
import requests
from bs4 import BeautifulSoup as bs
from PIL import Image

# Script directory for accessing bundled resources
script_dir = os.path.dirname(os.path.abspath(__file__))

# Default directory structure (Sphinx-compatible)
ATTACH_DIR = "_images/"
EMOTICONS_DIR = "_images/"
STYLES_DIR = "_static/"


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
    """Make an authenticated request.

    Args:
        url: URL to request
        arg_username: Username for auth
        arg_api_token: API token or PAT
        **kwargs: Additional arguments for requests.get

    Returns:
        requests.Response object
    """
    import time
    from random import uniform
    
    max_retries = 10
    base_delay = 3.0  # Start with 3 second delay for rate limiting
    
    for attempt in range(max_retries):
        try:
            # Add delay on retries to avoid rate limiting
            if attempt > 0:
                delay = base_delay * (2 ** (attempt - 1))  # Exponential: 3s, 6s, 12s, 24s...
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
                    response = requests.get(url, auth=(arg_username, arg_api_token), **kwargs)
            
            # Check for rate limiting
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    print(f"  Rate limited (429). Will retry with exponential backoff...")
                    continue
                else:
                    print(f"  Rate limited (429) after {max_retries} attempts")
                    return response
            
            # Success - return response
            return response
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
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


def set_variables():
    """Get directory structure configuration.

    Returns:
        Dictionary with attachment, emoticon, and styles directory paths
    """
    return {
        "attach_dir": ATTACH_DIR,
        "emoticons_dir": EMOTICONS_DIR,
        "styles_dir": STYLES_DIR,
    }


def set_dirs(arg_outdir="output"):
    """Get output folder paths for attachments, emoticons, and styles.

    Args:
        arg_outdir: Base output directory

    Returns:
        List of [attachments_dir, emoticons_dir, styles_dir]
    """
    my_vars = set_variables()
    outdir_attach = os.path.join(arg_outdir, my_vars["attach_dir"])
    outdir_emoticons = os.path.join(arg_outdir, my_vars["emoticons_dir"])
    outdir_styles = os.path.join(arg_outdir, my_vars["styles_dir"])
    return [outdir_attach, outdir_emoticons, outdir_styles]


def mk_outdirs(arg_outdir="output"):
    """Create output folders with default CSS.

    Args:
        arg_outdir: Base output directory

    Returns:
        List of [attachments_dir, emoticons_dir, styles_dir]
    """
    outdir_list = set_dirs(arg_outdir)
    outdir_attach = outdir_list[0]
    outdir_emoticons = outdir_list[1]
    outdir_styles = outdir_list[2]

    # Create directories
    if not os.path.exists(arg_outdir):
        os.mkdir(arg_outdir)
    if not os.path.exists(outdir_attach):
        os.mkdir(outdir_attach)
    if not os.path.exists(outdir_emoticons):
        os.mkdir(outdir_emoticons)
    if not os.path.exists(outdir_styles):
        os.mkdir(outdir_styles)

    # Copy default CSS if not present
    if not os.path.exists(outdir_styles + "/confluence.css"):
        css_source = os.path.join(script_dir, "styles", "confluence.css")
        css_dest = os.path.join(outdir_styles, "confluence.css")
        shutil.copy(css_source, css_dest)

    return outdir_list


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


def remove_illegal_characters(input):
    """Replace illegal filename characters with underscores.

    Args:
        input: String to sanitize

    Returns:
        Sanitized string safe for filenames
    """
    return re.sub(r"[^\w_\.\- ]+", "_", input)


def get_attachments(
    arg_site, arg_page_id, arg_outdir_attach, arg_username, arg_api_token
):
    """Download all attachments for a page.

    Args:
        arg_site: The site name
        arg_page_id: Page ID
        arg_outdir_attach: Output directory for attachments
        arg_username: Username for auth
        arg_api_token: API token for auth

    Returns:
        List of downloaded attachment filenames
    """
    my_attachments_list = []
    base_url = build_base_url(arg_site)
    server_url = f"{base_url}/rest/api/content/{arg_page_id}?expand=children.attachment"
    response = make_request(server_url, arg_username, arg_api_token, timeout=30)
    my_attachments = response.json()["children"]["attachment"]["results"]

    for attachment in my_attachments:
        attachment_title = remove_illegal_characters(
            requests.utils.unquote(attachment["title"])
            .replace(" ", "_")
            .replace(":", "-")
        )
        attachment_file_path = os.path.join(arg_outdir_attach, attachment_title)

        if not os.path.exists(attachment_file_path):
            print(f"Downloading: {attachment_title}")
            try:
                attachment_url = f"{base_url}{attachment['_links']['download']}"
                request_attachment = make_request(
                    attachment_url,
                    arg_username,
                    arg_api_token,
                    allow_redirects=True,
                    timeout=30,
                )
                with open(attachment_file_path, "wb") as f:
                    f.write(request_attachment.content)
            except Exception as e:
                print(f"WARNING: Skipping attachment {attachment_file_path}: {e}")
        my_attachments_list.append(attachment_title)

    return my_attachments_list


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


def get_page_properties_children(
    arg_site, arg_html, arg_outdir, arg_username, arg_api_token
):
    """Extract page properties children from HTML.

    Args:
        arg_site: The site name
        arg_html: HTML content to parse
        arg_outdir: Output directory
        arg_username: Username for auth
        arg_api_token: API token for auth

    Returns:
        List containing [page_ids_list, page_details_dict]
    """
    my_page_properties_children = []
    my_page_properties_children_dict = {}
    soup = bs(arg_html, "html.parser")
    my_page_properties_items = soup.findAll("td", class_="title")
    my_page_properties_items_counter = 0

    for n in my_page_properties_items:
        my_page_id = str(n["data-content-id"])
        my_page_properties_children.append(str(n["data-content-id"]))
        my_page_properties_items_counter = my_page_properties_items_counter + 1

        my_page_name = (
            get_page_name(arg_site, int(my_page_id), arg_username, arg_api_token)
            .rsplit("_", 1)[1]
            .replace(":", "-")
            .replace(" ", "_")
            .replace("%20", "_")
        )

        my_page_properties_children_dict.update({my_page_id: {}})
        my_page_properties_children_dict[my_page_id].update({"ID": my_page_id})
        my_page_properties_children_dict[my_page_id].update({"Name": my_page_name})

    print(f"{my_page_properties_items_counter} Page Properties Children Pages")
    return [my_page_properties_children, my_page_properties_children_dict]


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


def dump_html(
    arg_site,
    arg_html,
    arg_title,
    arg_page_id,
    arg_outdir_base,
    arg_outdir_content,
    arg_page_labels,
    arg_page_parent,
    arg_username,
    arg_api_token,
    arg_sphinx_compatible=True,
    arg_type="",
    arg_html_output=False,
    arg_rst_output=True,
):
    """Create HTML and RST files for a Confluence page.

    Args:
        arg_site: Name of the Confluence Site
        arg_html: HTML Content to use for page
        arg_title: Title of the page
        arg_page_id: Page ID
        arg_outdir_base: Base output folder
        arg_outdir_content: Output folder for Content
        arg_page_labels: Labels of the page
        arg_page_parent: Parent of the page
        arg_username: Username for authentication
        arg_api_token: API Token for authentication
        arg_sphinx_compatible: Use Sphinx-compatible folder structure
        arg_type: Page type for Page Properties ("report", "child", or "" for normal)
        arg_html_output: Whether to keep HTML files
        arg_rst_output: Whether to generate RST files
    """
    my_vars = set_variables()
    my_emoticons_list = []
    my_outdir_content = arg_outdir_content

    if not os.path.exists(my_outdir_content):
        os.mkdir(my_outdir_content)

    my_outdirs = mk_outdirs(arg_outdir_base)

    # Calculate relative path from content folder to base folder for images
    rel_path = os.path.relpath(arg_outdir_base, my_outdir_content)
    if rel_path == ".":
        rel_prefix = ""
    else:
        rel_prefix = rel_path + "/"

    soup = bs(arg_html, "html.parser")

    # Remove unwanted elements
    my_undesirables = soup.findAll("div", class_="expand-control")
    for div in my_undesirables:
        div.decompose()

    # Clean up pre tags
    pre_tags = soup.find_all("pre")
    for pre in pre_tags:
        pre["class"] = [c for c in pre.get("class", []) if c != "syntaxhighlighter-pre"]

    # Generate filenames
    html_file_name = (
        (f"{arg_title}.html").replace("/", "-").replace(":", "-").replace(" ", "_")
    )
    html_file_path = os.path.join(my_outdir_content, html_file_name)

    # Download attachments
    my_attachments = get_attachments(
        arg_site, arg_page_id, str(my_outdirs[0]), arg_username, arg_api_token
    )

    # Handle Page Properties Report pages
    if arg_type == "report":
        my_report_children_dict = get_page_properties_children(
            arg_site, arg_html, my_outdir_content, arg_username, arg_api_token
        )[1]
        my_page_properties_items = soup.findAll("td", class_="title")
        for item in my_page_properties_items:
            id = item["data-content-id"]
            item.a["href"] = f"{my_report_children_dict[id]['Name']}.html"

    # Process external embedded images
    my_embeds_externals = soup.findAll(
        "img", class_="confluence-embedded-image confluence-external-resource"
    )
    my_embeds_externals_counter = 0
    
    # Build base URL for handling relative URLs
    base_url = build_base_url(arg_site)
    
    for embed_ext in my_embeds_externals:
        orig_embed_ext_src = embed_ext["src"]
        
        # Handle relative URLs by prepending base URL - must be done BEFORE any operations
        if orig_embed_ext_src.startswith("/"):
            orig_embed_external_path = base_url + orig_embed_ext_src
        elif not orig_embed_ext_src.startswith(("http://", "https://")):
            # Relative path without leading slash
            orig_embed_external_path = f"{base_url}/{orig_embed_ext_src}"
        else:
            orig_embed_external_path = orig_embed_ext_src
        
        orig_embed_external_name = orig_embed_external_path.rsplit("/", 1)[-1].rsplit(
            "?"
        )[0]

        my_embed_external_name = remove_illegal_characters(
            (
                f"{arg_page_id}-{my_embeds_externals_counter}-{requests.utils.unquote(orig_embed_external_name)}"
            )
            .replace(" ", "_")
            .replace(":", "-")
        )

        my_embed_external_path = os.path.join(my_outdirs[0], my_embed_external_name)
        my_embed_external_path_relative = os.path.join(
            rel_prefix + my_vars["attach_dir"], my_embed_external_name
        )

        try:
            if not os.path.exists(my_embed_external_path):
                to_download = requests.get(
                    orig_embed_external_path, allow_redirects=True
                )
                # Check if download was successful
                if to_download.status_code != 200 or len(to_download.content) == 0:
                    print(f"WARNING: Failed to download external embed {my_embed_external_name}: HTTP {to_download.status_code}, size {len(to_download.content)}")
                    continue
                
                # Check if response is HTML instead of an image
                content_type = to_download.headers.get('Content-Type', '').lower()
                if 'html' in content_type or to_download.content.startswith(b'<!DOCTYPE') or to_download.content.startswith(b'<html'):
                    print(f"WARNING: Server returned HTML instead of external image for {my_embed_external_name}")
                    print(f"  URL: {orig_embed_external_path}")
                    print(f"  Content-Type: {content_type}")
                    print(f"  Response preview: {to_download.text[:200]}")
                    continue
                
                with open(my_embed_external_path, "wb") as f:
                    f.write(to_download.content)
            
            # Skip PIL for SVG files (not supported by Pillow)
            if my_embed_external_name.lower().endswith('.svg'):
                img = None  # SVG doesn't need size detection
                embed_ext["width"] = 600  # Default width for SVG
            else:
                try:
                    img = Image.open(my_embed_external_path)
                except Exception as img_error:
                    # Can't identify image format - could be avatar, corrupted, or unsupported format
                    print(f"WARNING: Can't identify external image format for {my_embed_external_name}: {img_error}")
                    print(f"  File size: {os.path.getsize(my_embed_external_path) if os.path.exists(my_embed_external_path) else 'N/A'} bytes")
                    img = None
                    embed_ext["width"] = 600  # Default width
        except Exception as e:
            print(f"WARNING: Skipping external embed {my_embed_external_path}: {e}")
            continue
        else:
            if img is not None:  # Raster image with dimensions
                if img.width < 600:
                    embed_ext["width"] = img.width
                else:
                    embed_ext["width"] = 600
                img.close()
            
            # Set attributes for both SVG and raster images
            embed_ext["height"] = "auto"
            embed_ext["onclick"] = (
                f'window.open("{my_embed_external_path_relative}")'
            )
            embed_ext["src"] = str(my_embed_external_path_relative)
            embed_ext["data-image-src"] = str(my_embed_external_path_relative)
            my_embeds_externals_counter = my_embeds_externals_counter + 1

    # Process embedded images (attachments)
    my_embeds = soup.findAll("img", class_=re.compile("^confluence-embedded-image"))
    print(str(len(my_embeds)) + " embedded images.")
    
    # Build base URL for handling relative URLs
    base_url = build_base_url(arg_site)
    
    for embed in my_embeds:
        orig_embed_src = embed["src"]
        
        # Handle relative URLs by prepending base URL - must be done BEFORE any operations
        if orig_embed_src.startswith("/"):
            orig_embed_path = base_url + orig_embed_src
        elif not orig_embed_src.startswith(("http://", "https://")):
            # Relative path without leading slash
            orig_embed_path = f"{base_url}/{orig_embed_src}"
        else:
            orig_embed_path = orig_embed_src
        
        orig_embed_name = orig_embed_path.rsplit("/", 1)[-1].rsplit("?")[0]

        my_embed_name = remove_illegal_characters(
            requests.utils.unquote(orig_embed_name).replace(" ", "_")
        )
        my_embed_path = os.path.join(my_outdirs[0], my_embed_name)
        my_embed_path_relative = f"{rel_prefix}{my_vars['attach_dir']}{my_embed_name}"

        img = None
        try:
            if not os.path.exists(my_embed_path):
                to_download = make_request(
                    orig_embed_path, arg_username, arg_api_token, allow_redirects=True
                )
                # Check if download was successful
                if to_download.status_code != 200 or len(to_download.content) == 0:
                    print(f"WARNING: Failed to download embed {my_embed_name}: HTTP {to_download.status_code}, size {len(to_download.content)}")
                    print(f"  URL: {orig_embed_path}")
                    continue
                
                # Check if response is HTML instead of an image
                content_type = to_download.headers.get('Content-Type', '').lower()
                if 'html' in content_type or to_download.content.startswith(b'<!DOCTYPE') or to_download.content.startswith(b'<html'):
                    print(f"WARNING: Server returned HTML instead of image for {my_embed_name}")
                    print(f"  URL: {orig_embed_path}")
                    print(f"  Content-Type: {content_type}")
                    print(f"  Response preview: {to_download.text[:200]}")
                    continue
                
                with open(my_embed_path, "wb") as f:
                    f.write(to_download.content)
                    
                print(f"  Downloaded {my_embed_name}: {len(to_download.content)} bytes")
            
            # Skip PIL for SVG files (not supported by Pillow)
            if my_embed_name.lower().endswith('.svg'):
                img = None  # SVG doesn't need size detection
                embed["width"] = 600  # Default width for SVG
            else:
                try:
                    img = Image.open(my_embed_path)
                except Exception as img_error:
                    # Can't identify image format - could be avatar, corrupted, or unsupported format
                    # Still set it up with default dimensions
                    print(f"WARNING: Can't identify image format for {my_embed_name}: {img_error}")
                    if os.path.exists(my_embed_path):
                        file_size = os.path.getsize(my_embed_path)
                        print(f"  File exists: {my_embed_path}")
                        print(f"  File size: {file_size} bytes")
                        # Read first few bytes to check file type
                        with open(my_embed_path, 'rb') as f:
                            header = f.read(20)
                            print(f"  File header: {header[:8].hex() if len(header) >= 8 else 'too short'}")
                    else:
                        print(f"  File does NOT exist: {my_embed_path}")
                    img = None
                    embed["width"] = 600  # Default width
        except Exception as e:
            print(f"WARNING: Skipping embed {my_embed_path}: {e}")
            continue
        else:
            if img is not None:  # Raster image with dimensions
                if img.width < 600:
                    embed["width"] = img.width
                else:
                    embed["width"] = 600
                img.close()
            
            # Set attributes for both SVG and raster images
            embed["height"] = "auto"
            embed["onclick"] = f'window.open("{my_embed_path_relative}")'
            embed["src"] = my_embed_path_relative

    # Process emoticons
    my_emoticons = soup.findAll(
        "img", class_=re.compile("emoticon|expand-control-image")
    )
    print(f"{len(my_emoticons)} emoticons.")
    for emoticon in my_emoticons:
        my_emoticon_title = emoticon["src"].rsplit("/", 1)[-1]
        my_emoticon_path = f"{rel_prefix}{my_vars['emoticons_dir']}{my_emoticon_title}"

        if my_emoticon_title not in my_emoticons_list:
            my_emoticons_list.append(my_emoticon_title)
            print(f"Getting emoticon: {my_emoticon_title}")
            file_path = os.path.join(
                my_outdirs[1], remove_illegal_characters(my_emoticon_title)
            )
            if not os.path.exists(file_path):
                orig_emoticon_src = emoticon["src"]
                
                # Handle relative URLs by prepending base URL - must be done BEFORE any operations
                if orig_emoticon_src.startswith("/"):
                    emoticon_src = base_url + orig_emoticon_src
                elif not orig_emoticon_src.startswith(("http://", "https://")):
                    emoticon_src = f"{base_url}/{orig_emoticon_src}"
                else:
                    emoticon_src = orig_emoticon_src
                
                try:
                    request_emoticons = make_request(
                        emoticon_src, arg_username, arg_api_token
                    )
                    with open(file_path, "wb") as f:
                        f.write(request_emoticons.content)
                except Exception as e:
                    print(f"WARNING: Skipping emoticon {file_path}: {e}")
        emoticon["src"] = my_emoticon_path

    # Get page metadata
    my_body_export_view = get_body_export_view(
        arg_site, arg_page_id, arg_username, arg_api_token
    ).json()
    page_url = f"{my_body_export_view['_links']['base']}{my_body_export_view['_links']['webui']}"
    styles_dir_relative = f"{rel_prefix}{my_vars['styles_dir']}"

    # Build HTML header
    my_header = (
        f"<html>\n"
        f"<head>\n"
        f"<title>{arg_title}</title>\n"
        f'<link rel="stylesheet" href="{styles_dir_relative}confluence.css" type="text/css" />\n'
        f'<meta name="generator" content="confluenceExportHTML" />\n'
        f'<META http-equiv="Content-Type" content="text/html; charset=UTF-8">\n'
        f'<meta name="ConfluencePageLabels" content="{arg_page_labels}">\n'
        f'<meta name="ConfluencePageID" content="{arg_page_id}">\n'
        f'<meta name="ConfluencePageParent" content="{arg_page_parent}">\n'
        f"</head>\n"
        f"<body>\n"
        f"<h2>{arg_title}</h2>\n"
        f'<p>Original URL: <a href="{page_url}"> {arg_title}</a><hr>\n'
    )

    my_footer = "</body>\n</html>"

    # Build attachments list
    attach_dir = rel_prefix + my_vars["attach_dir"]
    my_pre_footer = ""
    if len(my_attachments) > 0:
        my_pre_footer = "<h2>Attachments</h2><ol>"
        for attachment in my_attachments:
            my_pre_footer += f'<li><a href="{os.path.join(attach_dir,attachment)}">{attachment}</a></li>'
        my_pre_footer += "</ol></br>"

    # Write HTML file
    pretty_html = soup.prettify()
    with open(html_file_path, "w", encoding="utf-8") as html_file:
        html_file.write(my_header)
        html_file.write(pretty_html)
        if len(my_attachments) > 0:
            html_file.write(my_pre_footer)
        html_file.write(my_footer)

    if arg_html_output:
        print(f"Exported HTML file {html_file_path}")

    # Convert to RST
    if not arg_rst_output:
        return

    rst_file_name = f"{html_file_name.replace('html','rst')}"
    rst_file_path = os.path.join(my_outdir_content, rst_file_name)
    try:
        # Read HTML content and convert to avoid Path issues
        with open(html_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # Use convert_text instead of convert_file to avoid Path issues
        output_rst = pypandoc.convert_text(
            html_content,
            to="rst",
            format="html",
            extra_args=["--standalone", "--wrap=none", "--list-tables"],
        )
    except Exception as e:
        print(f"ERROR: Failed to generate RST file: {e}")
    else:
        # Build RST header with metadata
        if arg_sphinx_compatible:
            rst_page_header = (
                f":conf_pagetype: {arg_type}\n"
                f":conf_pageid: {arg_page_id}\n"
                f":conf_parent: {arg_page_parent}\n"
                f":conf_labels: {arg_page_labels}\n"
                f":doc_title: {arg_title}\n"
                f"\n"
            )
        else:
            rst_page_header = (
                f".. meta::\n"
                f"    :confluencePageId: {arg_page_id} \n"
                f"    :confluencePageLabels: {arg_page_labels} \n"
                f"    :confluencePageParent: {arg_page_parent} \n"
                f"\n"
            )

        with open(rst_file_path, "w", encoding="utf-8") as rst_file:
            rst_file.write(rst_page_header)
            rst_file.write(output_rst)

        print(f"Exported RST file: {rst_file_path}")

        if not arg_html_output:
            os.remove(html_file_path)
