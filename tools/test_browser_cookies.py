#!/usr/bin/env python3
"""
Quick test to check if browser cookies can be extracted
Tests all supported browsers: Chrome, Firefox, Safari, Edge
"""

try:
    import browser_cookie3
except ImportError:
    print("ERROR: browser_cookie3 module not installed")
    print("Install it with: pip install browser-cookie3")
    exit(1)

domain = "confluence.tmc-stargate.com"

print(f"Testing cookie extraction for: {domain}")
print("=" * 60)
print()

browsers = [
    ("Chrome", browser_cookie3.chrome),
    ("Firefox", browser_cookie3.firefox),
    ("Safari", browser_cookie3.safari),
    ("Edge", browser_cookie3.edge),
]

success_count = 0
for browser_name, browser_func in browsers:
    try:
        print(f"Testing {browser_name}...", end=" ")
        cookies = browser_func(domain_name=domain)
        cookie_list = list(cookies)
        if cookie_list:
            print(f"✓ Found {len(cookie_list)} cookies")
            success_count += 1
            # Show some cookie names (not values for security)
            cookie_names = [c.name for c in cookie_list[:5]]
            print(f"  Sample cookies: {', '.join(cookie_names)}")
        else:
            print(f"⚠ No cookies found (not logged in?)")
    except Exception as e:
        print(f"✗ Failed: {type(e).__name__}")
        if "pycryptodomex" in str(e).lower():
            print(f"  Note: Edge/Chrome might need: pip install pycryptodomex")

print()
print("=" * 60)
if success_count > 0:
    print(f"✓ SUCCESS: Found cookies in {success_count} browser(s)")
    print()
    print("You can now run:")
    print(f"  python confluenceDumpWithSSO.py --mode space --site {domain} --space YOUR_SPACE_KEY")
else:
    print("✗ FAILED: Could not extract cookies from any browser")
    print()
    print("Troubleshooting:")
    print("1. Make sure you're logged into Confluence in one of the supported browsers")
    print("2. Try opening https://confluence.tmc-stargate.com in your browser")
    print("3. Install dependencies: pip install browser-cookie3 pycryptodomex")
    print("4. On macOS: you might need to grant Terminal access to browser data")
