"""
Helper to extract Confluence session cookies from your browser
This allows you to use your authenticated browser session for API calls
"""

import browser_cookie3
import requests


def get_confluence_session_cookies(domain):
    """
    Extract Confluence session cookies from your browser

    Args:
        domain: Your Confluence domain (e.g., 'confluence.tmc-stargate.com')

    Returns:
        requests.Session object with authentication cookies
    """
    session = requests.Session()

    # Try to get cookies from different browsers
    try:
        # Try Chrome first
        cookies = browser_cookie3.chrome(domain_name=domain)
        session.cookies.update(cookies)
        print(f"✓ Loaded cookies from Chrome")
        return session
    except:
        pass

    try:
        # Try Firefox
        cookies = browser_cookie3.firefox(domain_name=domain)
        session.cookies.update(cookies)
        print(f"✓ Loaded cookies from Firefox")
        return session
    except:
        pass

    try:
        # Try Safari
        cookies = browser_cookie3.safari(domain_name=domain)
        session.cookies.update(cookies)
        print(f"✓ Loaded cookies from Safari")
        return session
    except:
        pass

    try:
        # Try Edge
        cookies = browser_cookie3.edge(domain_name=domain)
        session.cookies.update(cookies)
        print(f"✓ Loaded cookies from Edge")
        return session
    except:
        pass

    raise Exception(
        "Could not load cookies from any browser. Make sure you're logged into Confluence in your browser."
    )


def test_session(session, base_url):
    """Test if the session works"""
    # Try multiple API endpoints
    endpoints = [
        "/wiki/rest/api/space",
        "/rest/api/space",
        "/wiki/api/v2/spaces",
        "/api/v2/spaces",
    ]

    print("Testing API endpoints:")
    for endpoint in endpoints:
        test_url = f"{base_url}{endpoint}"
        print(f"  Trying: {endpoint}...", end=" ")
        try:
            response = session.get(test_url, timeout=10, allow_redirects=False)
            if response.status_code == 200:
                print(f"✓ SUCCESS (HTTP 200)")
                print(f"\nCorrect API endpoint found: {endpoint}")
                return True
            elif response.status_code == 302 or response.status_code == 301:
                print(f"→ Redirect (HTTP {response.status_code})")
            else:
                print(f"✗ HTTP {response.status_code}")
        except Exception as e:
            print(f"✗ Error: {e}")

    print("\n✗ Could not find working API endpoint")
    return False


def test_session_old(session, base_url):
    """Test if the session works (old version)"""
    try:
        response = session.get(f"{base_url}/wiki/rest/api/space", timeout=10)
        if response.status_code == 200:
            print(f"✓ Authentication successful!")
            return True
        else:
            print(f"✗ Authentication failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == "__main__":
    domain = "confluence.tmc-stargate.com"
    base_url = f"https://{domain}"

    print(f"Attempting to load session cookies for {domain}")
    print("Make sure you're logged into Confluence in your browser!")
    print()

    session = get_confluence_session_cookies(domain)
    test_session(session, base_url)
