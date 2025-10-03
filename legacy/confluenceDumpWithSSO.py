#!/usr/bin/env python3
"""
Confluence Dump with SSO Support

This version supports Azure AD SSO authentication by using browser session cookies.
Make sure you're logged into Confluence in your browser before running this script.
"""

import os
import argparse
import myModules
from concurrent.futures import ThreadPoolExecutor
import time

try:
    import browser_cookie3
except ImportError:
    print("ERROR: browser_cookie3 module not installed")
    print("Install it with: pip install browser-cookie3")
    exit(1)

def get_confluence_session(domain):
    """Get authenticated session from browser cookies"""
    import requests
    session = requests.Session()
    
    # Try different browsers
    for browser_func in [browser_cookie3.chrome, browser_cookie3.firefox, browser_cookie3.safari, browser_cookie3.edge]:
        try:
            cookies = browser_func(domain_name=domain)
            session.cookies.update(cookies)
            print(f"✓ Loaded session cookies from browser")
            return session
        except:
            continue
    
    raise Exception("Could not load cookies. Make sure you're logged into Confluence in your browser.")

parser = argparse.ArgumentParser()
parser.add_argument('--mode', '-m', dest='mode',
                    choices=['single', 'space', 'bylabel', 'pageprops'],
                    help='Chose a download mode', required=True)
parser.add_argument('--site', '-S', type=str,
                    help='Atlassian Site', required=True)
parser.add_argument('--space', '-s', type=str,
                    help='Space Key')
parser.add_argument('--page', '-p', type=str,
                    help='Page ID')
parser.add_argument('--label', '-l', type=str,
                    help='Page label')
parser.add_argument('--outdir', '-o', type=str, default='output',
                    help='Folder for export', required=False)
parser.add_argument('--sphinx', '-x', action='store_true', default=False,
                    help='Sphinx compatible folder structure', required=False)
parser.add_argument('--tags', action='store_true', default=False,
                    help='Add labels as .. tags::', required=False)
parser.add_argument('--html', action='store_true', default=False,
                    help='Include .html file in export (default is only .rst)', required=False)
parser.add_argument('--no-rst', action='store_false', dest="rst", default=True,
                    help='Disable .rst file in export', required=False)
parser.add_argument('--showlabels', action='store_true', default=False,
                    help='Export .rst files with the page labels at the bottom', required=False)

args = parser.parse_args()

# Extract domain from site
atlassian_site = args.site.replace('https://', '').replace('http://', '')

print(f"Using SSO authentication via browser cookies for {atlassian_site}")
print("Make sure you're logged into Confluence in your browser!")
print()

# Get authenticated session from browser
try:
    session = get_confluence_session(atlassian_site)
except Exception as e:
    print(f"ERROR: {e}")
    print()
    print("Troubleshooting:")
    print("1. Make sure you're logged into Confluence in your browser")
    print("2. Try opening Confluence in Chrome, Firefox, or Safari")
    print("3. Install browser-cookie3: pip install browser-cookie3")
    exit(1)

# Test the session
test_url = f"https://{atlassian_site}/rest/api/space"
try:
    test_response = session.get(test_url, timeout=10)
    if test_response.status_code != 200:
        print(f"ERROR: Authentication test failed (HTTP {test_response.status_code})")
        print("Make sure you're logged into Confluence and try again.")
        exit(1)
    print("✓ Authentication successful!")
    print()
except Exception as e:
    print(f"ERROR: Could not connect to Confluence: {e}")
    exit(1)

# Use empty username and pass session as api_token
user_name = ""
api_token = session  # Pass the session object as the token

sphinx_compatible = args.sphinx
sphinx_tags = args.tags
my_outdir_base = args.outdir

if args.mode == 'single':
    ############
    ## SINGLE ##
    ############
    print(f"Exporting a single page (Sphinx set to {sphinx_compatible})")
    
    # Ask if user wants to export children too
    export_children = True  # Default to True for parent pages
    
    page_id = args.page
    
    if page_id is None:
        print("ERROR: --page is required for single mode")
        print("Example: --mode single --page 796450310")
        exit(1)
    
    print(f"Fetching page {page_id} and all its children...")
    print()
    
    # Function to get all child pages recursively with concurrent fetching
    def get_all_children_concurrent(page_id, level=0):
        """Recursively get all children of a page"""
        pages = []
        indent = "  " * level
        
        # Get page info
        my_body_export_view = myModules.get_body_export_view(atlassian_site, page_id, user_name, api_token).json()
        page_title = my_body_export_view['title']
        print(f"{indent}Found: {page_title} (ID: {page_id})")
        
        pages.append({
            'id': page_id,
            'title': page_title,
            'body': my_body_export_view,
            'level': level,
            'parent_id': None  # Will be set by parent
        })
        
        # Get children
        children_url = f"https://{atlassian_site}/rest/api/content/{page_id}/child/page?limit=250"
        children_response = session.get(children_url, timeout=30)
        
        if children_response.status_code != 200:
            return pages
        
        children_data = children_response.json()
        
        child_pages = children_data.get('results', [])
        
        if child_pages:
            print(f"{indent}  → {len(child_pages)} children")
            
            # Fetch all children concurrently using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = []
                for child in child_pages:
                    child_id = child['id']
                    future = executor.submit(get_all_children_concurrent, child_id, level + 1)
                    futures.append((child_id, future))
                
                # Wait for all child tasks to complete
                for child_id, future in futures:
                    child_pages_list = future.result()
                    # Set parent IDs
                    for cp in child_pages_list:
                        if cp['level'] == level + 1 and cp['parent_id'] is None:
                            cp['parent_id'] = page_id
                    pages.extend(child_pages_list)
        
        return pages
    
    print("Fetching page tree (concurrent)...")
    start_time = time.time()
    all_pages = get_all_children_concurrent(page_id)
    fetch_time = time.time() - start_time
    print(f"✓ Fetched {len(all_pages)} pages in {fetch_time:.2f} seconds")
    
    # Build a map of page_id -> folder path
    page_paths = {}
    
    def get_page_path(page_id):
        """Get the folder path for a page based on its hierarchy"""
        if page_id in page_paths:
            return page_paths[page_id]
        
        # Find the page
        page = next((p for p in all_pages if p['id'] == page_id), None)
        if not page:
            return ""
        
        # If it's the root, put it in the root folder
        if page['parent_id'] is None:
            page_paths[page_id] = ""
            return ""
        
        # Otherwise, nest it under the parent
        parent_path = get_page_path(page['parent_id'])
        # Create a clean folder name from the current page title
        clean_title = page['title'].replace("/", "-").replace(",", "").replace("&", "And").replace(":", "-").replace(" ", "_")
        page_folder = f"{page['id']}-{clean_title}"
        
        if parent_path:
            page_paths[page_id] = os.path.join(parent_path, page_folder)
        else:
            page_paths[page_id] = page_folder
        
        return page_paths[page_id]
    
    # Pre-calculate all paths
    for page in all_pages:
        get_page_path(page['id'])
    
    print()
    print(f"Total pages to export: {len(all_pages)}")
    print("=" * 70)
    print()
    
    # Get the root page info for the base folder name
    root_page = all_pages[0]
    root_title = root_page['title'].replace("/", "-").replace(",", "").replace("&", "And").replace(":", "-")
    
    my_outdir_base = os.path.join(my_outdir_base, f"{page_id}-{root_title}")
    my_outdir_content = my_outdir_base
    
    my_outdirs = myModules.mk_outdirs(my_outdir_base)
    
    print(f"Export folder: \"{my_outdir_base}\"")
    print()
    
    # Export pages with concurrent processing
    def export_page(page, page_num, total_pages):
        """Export a single page (can be run in parallel)"""
        page_body = page['body']
        page_html = page_body['body']['export_view']['value']
        page_title = page_body['title'].replace("/", "-").replace(",", "").replace("&", "And").replace(":", "-").replace(" ", "_")
        page_id_current = page['id']
        
        # Determine the output folder for this page
        if page['level'] == 0:
            # Root page goes in the base folder
            page_outdir = my_outdir_content
        else:
            # Child pages go in subfolders based on hierarchy
            parent_path = get_page_path(page['parent_id']) if page['parent_id'] else ""
            page_outdir = os.path.join(my_outdir_base, parent_path) if parent_path else my_outdir_content
            
            # Create the directory if it doesn't exist
            if not os.path.exists(page_outdir):
                os.makedirs(page_outdir, exist_ok=True)
        
        print(f"[{page_num}/{total_pages}] Exporting: {page['title']}")
        
        page_labels = myModules.get_page_labels(atlassian_site, page_id_current, user_name, api_token)
        page_parent = myModules.get_page_parent(atlassian_site, page_id_current, user_name, api_token)
        
        myModules.dump_html(
            atlassian_site, page_html, page_title, page_id_current,
            my_outdir_base, page_outdir, page_labels, page_parent,
            user_name, api_token, sphinx_compatible, sphinx_tags,
            arg_html_output=args.html, arg_rst_output=args.rst
        )
    
    # Use ThreadPoolExecutor for concurrent exports
    print("Exporting pages (concurrent)...")
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for idx, page in enumerate(all_pages, 1):
            future = executor.submit(export_page, page, idx, len(all_pages))
            futures.append(future)
        
        # Wait for all to complete
        for future in futures:
            future.result()
    
    export_time = time.time() - start_time
    print()
    print(f"✓ Exported {len(all_pages)} pages in {export_time:.2f} seconds")
    print(f"Total time: {fetch_time + export_time:.2f} seconds")
    
    """
    # OLD SEQUENTIAL CODE - keeping for reference
    page_counter = 0
    for page in all_pages:
        page_counter += 1
        
        page_body = page['body']
        page_html = page_body['body']['export_view']['value']
        page_title = page_body['title'].replace("/", "-").replace(",", "").replace("&", "And").replace(":", "-").replace(" ", "_")
        page_id_current = page['id']
        
        # Determine the output folder for this page
        if page['level'] == 0:
            # Root page goes in the base folder
            page_outdir = my_outdir_content
        else:
            # Child pages go in subfolders based on hierarchy
            parent_path = get_page_path(page['parent_id']) if page['parent_id'] else ""
            page_outdir = os.path.join(my_outdir_base, parent_path) if parent_path else my_outdir_content
            
            # Create the directory if it doesn't exist
            if not os.path.exists(page_outdir):
                os.makedirs(page_outdir, exist_ok=True)
        
        print(f"Exporting page {page_counter}/{len(all_pages)}: {page['title']}")
        
        page_labels = myModules.get_page_labels(atlassian_site, page_id_current, user_name, api_token)
        page_parent = myModules.get_page_parent(atlassian_site, page_id_current, user_name, api_token)
        
        myModules.dump_html(
            atlassian_site, page_html, page_title, page_id_current,
            my_outdir_base, page_outdir, page_labels, page_parent,
            user_name, api_token, sphinx_compatible, sphinx_tags,
            arg_html_output=args.html, arg_rst_output=args.rst
        )
    """
    
    print()
    print("Done!")

elif args.mode == 'space':
    ###########
    ## SPACE ##
    ###########
    print(f"Exporting a whole space (Sphinx set to {sphinx_compatible})")
    space_key = args.space
    
    all_spaces_full = myModules.get_spaces_all(atlassian_site, user_name, api_token)
    all_spaces_short = []
    
    space_id = None
    space_name = None
    
    for n in all_spaces_full:
        all_spaces_short.append({
            'space_key': n['key'],
            'space_id': n['id'],
            'space_name': n['name'],
            'homepage_id': n.get('_expandable', {}).get('homepage', '').split('/')[-1] if n.get('_expandable', {}).get('homepage') else None,
            'spaceDescription': n.get('_expandable', {}).get('description', ''),
        })
        if (n['key'] == space_key) or n['key'] == str.upper(space_key) or n['key'] == str.lower(space_key):
            print("Found space: " + n['key'])
            space_id = n['id']  # Numeric ID for display
            space_key_found = n['key']  # Key for API calls
            space_name = n['name']
    
    if space_id is None:
        print(f"Could not find Space Key '{space_key}' in this site")
        exit(1)
    
    # Use the space key for API calls, not the numeric ID
    my_outdir_content = os.path.join(my_outdir_base, f"{space_key_found}-{space_name}")
    if not os.path.exists(my_outdir_content):
        os.mkdir(my_outdir_content)
    if not sphinx_compatible:
        my_outdir_base = my_outdir_content
    
    # Get list of pages from space
    all_pages_full = myModules.get_pages_from_space(atlassian_site, space_key_found, user_name, api_token)
    all_pages_short = []
    
    for n in all_pages_full:
        # Extract parent ID from ancestors if available
        parent_id = None
        if n.get('ancestors') and len(n.get('ancestors', [])) > 0:
            parent_id = n['ancestors'][-1].get('id')
        
        all_pages_short.append({
            'page_id': n['id'],
            'pageTitle': n['title'],
            'parentId': parent_id,
            'space_id': n.get('space', {}).get('key') or space_key_found,
        })
    
    print(f"{len(all_pages_short)} pages to export")
    page_counter = 0
    
    for p in all_pages_short:
        page_counter = page_counter + 1
        my_body_export_view = myModules.get_body_export_view(atlassian_site, p['page_id'], user_name, api_token).json()
        my_body_export_view_html = my_body_export_view['body']['export_view']['value']
        my_body_export_view_title = p['pageTitle'].replace("/", "-").replace(",", "").replace("&", "And").replace(" ", "_")
        
        print()
        print(f"Getting page #{page_counter}/{len(all_pages_short)}, {my_body_export_view_title}, {p['page_id']}")
        
        my_body_export_view_labels = myModules.get_page_labels(atlassian_site, p['page_id'], user_name, api_token)
        
        myModules.dump_html(
            atlassian_site, my_body_export_view_html, my_body_export_view_title, p['page_id'],
            my_outdir_base, my_outdir_content, my_body_export_view_labels, p['parentId'],
            user_name, api_token, sphinx_compatible, sphinx_tags,
            arg_html_output=args.html, arg_rst_output=args.rst
        )
    
    print("Done!")

else:
    print(f"Mode '{args.mode}' not yet implemented in SSO version")
    print("Currently only --mode space is supported")
    print("Please use confluenceDumpWithPython.py for other modes")
