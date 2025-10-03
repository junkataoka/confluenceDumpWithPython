#!/usr/bin/env python3
"""
Check the pages API response structure
"""

import sys
try:
    import browser_cookie3
    import requests
    import json
except ImportError as e:
    print(f"ERROR: {e}")
    sys.exit(1)

def get_confluence_session(domain):
    session = requests.Session()
    for browser_func in [browser_cookie3.chrome, browser_cookie3.firefox, browser_cookie3.safari, browser_cookie3.edge]:
        try:
            cookies = browser_func(domain_name=domain)
            session.cookies.update(cookies)
            return session
        except:
            continue
    raise Exception("Could not load cookies")

domain = "confluence.tmc-stargate.com"
session = get_confluence_session(domain)

# First get space ID
space_url = f"https://{domain}/rest/api/space?limit=1"
space_response = session.get(space_url)
space_data = space_response.json()
space_id = space_data['results'][0]['key']  # Use key instead of id

print(f"Testing with space: {space_id}")
print()

# Now get pages from that space
pages_url = f"https://{domain}/rest/api/space/{space_id}/content?limit=1"
print(f"URL: {pages_url}")
print()

response = session.get(pages_url)

if response.status_code == 200:
    data = response.json()
    print("Pages API Response Structure:")
    print("=" * 70)
    print(json.dumps(data, indent=2))
    
    if "page" in data and "results" in data["page"] and len(data["page"]["results"]) > 0:
        print()
        print("=" * 70)
        print("First Page Keys:")
        print("=" * 70)
        page = data["page"]["results"][0]
        for key in page.keys():
            value_type = type(page[key]).__name__
            value_preview = str(page[key])[:50] if not isinstance(page[key], (dict, list)) else value_type
            print(f"  {key}: {value_type} = {value_preview}")
else:
    print(f"Error: {response.status_code}")
    print(response.text)
