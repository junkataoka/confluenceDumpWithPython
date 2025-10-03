#!/usr/bin/env python3
"""
Check the actual structure of the API response
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

url = f"https://{domain}/rest/api/space?limit=1"
response = session.get(url)

if response.status_code == 200:
    data = response.json()
    print("Full API Response Structure:")
    print("=" * 70)
    print(json.dumps(data, indent=2))
    
    if "results" in data and len(data["results"]) > 0:
        print()
        print("=" * 70)
        print("First Space Keys:")
        print("=" * 70)
        space = data["results"][0]
        for key in space.keys():
            print(f"  {key}: {type(space[key]).__name__}")
else:
    print(f"Error: {response.status_code}")
