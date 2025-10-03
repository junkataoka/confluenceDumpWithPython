#!/usr/bin/env python3
"""
Check if ancestors are expanded
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

# Test with expand parameter
url = f"https://{domain}/rest/api/space/AIP/content/page?limit=1&expand=ancestors,space"
print(f"Testing: {url}")
print()

response = session.get(url)

if response.status_code == 200:
    data = response.json()
    if data.get("page", {}).get("results"):
        page = data["page"]["results"][0]
        print("Page data with expand=ancestors,space:")
        print("=" * 70)
        print(json.dumps(page, indent=2))
        print()
        print("=" * 70)
        if "ancestors" in page:
            print("✓ ancestors field is present")
            print(f"  Value: {page['ancestors']}")
        else:
            print("✗ ancestors field NOT present")
            print(f"  _expandable has: {page.get('_expandable', {}).get('ancestors')}")
        
        if "space" in page:
            print("✓ space field is present")
            print(f"  Value: {page['space']}")
        else:
            print("✗ space field NOT present")
            print(f"  _expandable has: {page.get('_expandable', {}).get('space')}")
else:
    print(f"Error: {response.status_code}")
