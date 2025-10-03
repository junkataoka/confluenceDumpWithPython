#!/usr/bin/env python3
"""
Debug script to test session-based authentication
"""

import sys
try:
    import browser_cookie3
    import requests
except ImportError as e:
    print(f"ERROR: Missing module: {e}")
    print("Install with: pip install browser-cookie3 requests")
    sys.exit(1)

def get_confluence_session(domain):
    """Get authenticated session from browser cookies"""
    session = requests.Session()
    
    # Try different browsers
    for browser_name, browser_func in [
        ("Chrome", browser_cookie3.chrome),
        ("Firefox", browser_cookie3.firefox),
        ("Safari", browser_cookie3.safari),
        ("Edge", browser_cookie3.edge),
    ]:
        try:
            cookies = browser_func(domain_name=domain)
            session.cookies.update(cookies)
            print(f"✓ Loaded cookies from {browser_name}")
            return session
        except:
            continue
    
    raise Exception("Could not load cookies")

# Configuration
domain = "confluence.tmc-stargate.com"
base_url = f"https://{domain}"

print("=" * 70)
print("Session Authentication Debug Test")
print("=" * 70)
print()

# Get session
print("Step 1: Loading browser cookies...")
try:
    session = get_confluence_session(domain)
    print(f"✓ Session object created: {type(session)}")
    print(f"  Number of cookies: {len(session.cookies)}")
    print(f"  Cookie names: {[c.name for c in session.cookies][:5]}")
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

print()
print("Step 2: Testing API endpoints...")
print()

# Test different endpoints
endpoints = [
    "/rest/api/space",
    "/rest/api/space?limit=10",
]

for endpoint in endpoints:
    url = f"{base_url}{endpoint}"
    print(f"Testing: {endpoint}")
    try:
        response = session.get(url, timeout=10)
        print(f"  Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if "results" in data:
                    print(f"  ✓ SUCCESS - Found {len(data['results'])} spaces")
                    if data['results']:
                        print(f"  First space: {data['results'][0].get('key', 'N/A')}")
                elif "size" in data:
                    print(f"  ✓ SUCCESS - Response contains {data.get('size', 0)} items")
                else:
                    print(f"  ✓ SUCCESS - Response keys: {list(data.keys())[:5]}")
            except:
                print(f"  ✓ SUCCESS - Non-JSON response")
        elif response.status_code == 401:
            print(f"  ✗ UNAUTHORIZED - Session not valid")
            print(f"  Response: {response.text[:200]}")
        elif response.status_code == 403:
            print(f"  ✗ FORBIDDEN - No permission")
        else:
            print(f"  ✗ Error: {response.text[:200]}")
    except Exception as e:
        print(f"  ✗ Exception: {e}")
    print()

print("=" * 70)
print("Step 3: Checking if session object passes correctly...")
print()

# Simulate what myModules.make_request does
def test_session_detection(api_token):
    """Test if we can detect session object"""
    print(f"Type: {type(api_token)}")
    print(f"Has 'get': {hasattr(api_token, 'get')}")
    print(f"Has 'cookies': {hasattr(api_token, 'cookies')}")
    print(f"Has 'request': {hasattr(api_token, 'request')}")
    
    if hasattr(api_token, 'get') and hasattr(api_token, 'cookies'):
        print("✓ Detected as session object")
        return True
    else:
        print("✗ NOT detected as session object")
        return False

test_session_detection(session)

print()
print("=" * 70)
print("Recommendation:")
print()

if test_session_detection(session):
    print("✓ Session detection works. The issue might be:")
    print("  1. Session cookies expired - re-login to Confluence in browser")
    print("  2. CSRF protection - may need X-Atlassian-Token header")
    print("  3. API permissions - your account may lack API access")
else:
    print("✗ Session object not detected properly in make_request()")
    print("  Need to fix session detection logic")
