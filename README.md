# Confluence Export Tool

Export Confluence pages to HTML and RST format with **Azure AD SSO support**. Includes all images, attachments, and emoticons with proper hierarchical folder structure.

## 🎯 Key Features

- ✅ **SSO Authentication** - Uses browser session cookies (works with Azure AD, Okta, SAML, etc.)
- ✅ **Hierarchical Export** - Preserves parent-child page relationships in folder structure
- ✅ **Concurrent Processing** - Fast parallel downloads (5-10x faster than sequential)
- ✅ **Multiple Formats** - Export to HTML and/or RST (Sphinx compatible)
- ✅ **Complete Content** - Downloads all images, attachments, and emoticons
- ✅ **Smart Paths** - Automatic relative paths for nested pages

## 🚀 Quick Start

### Prerequisites

1. **Python 3.8+**
2. **Login to Confluence** in your browser (Chrome, Firefox, Safari, or Edge)
3. **Install dependencies:**

```bash
pip install browser-cookie3 requests beautifulsoup4 pypandoc Pillow
```

4. **Install Pandoc** (for RST conversion):

```bash
# macOS
brew install pandoc

# Ubuntu/Debian
sudo apt-get install pandoc

# Windows
choco install pandoc
```

### Basic Usage

**Export a single page with all children:**

```bash
python confluence_export.py --site confluence.example.com --page 796450310 --html
```

### Proxy Settings

If you're behind a corporate proxy, set the `HTTP_PROXY` and `HTTPS_PROXY` environment variables:

```bash
export HTTP_PROXY=http://your-proxy:port
export HTTPS_PROXY=http://your-proxy:port
```

## 📋 Command Line Options

```
Required:
  --site, -S          Confluence site (e.g., confluence.example.com)
  --page, -p          Page ID (required)

Optional:
  --outdir, -o        Output directory (default: output)
  --sphinx, -x        Enable Sphinx compatibility mode
  --tags              Add labels as tags in RST files
  --html              Include HTML files in export
  --no-rst            Disable RST file generation
  --workers           Number of concurrent workers (default: 5)
```

## 📁 Output Structure

For single page with children:

```
output/796450310-Page_Title/
├── _images/                    # All images (shared)
│   ├── image1.png
│   └── image2.jpg
├── _static/                    # CSS files (shared)
│   └── confluence.css
├── Page_Title.html             # Root page HTML
├── Page_Title.rst              # Root page RST
├── 123456-Child_Page/          # Child page folder
│   ├── Child_Page.html
│   ├── Child_Page.rst
│   └── 789012-Grandchild/      # Grandchild folder
│       ├── Grandchild.html
│       └── Grandchild.rst
└── 123457-Another_Child/
    ├── Another_Child.html
    └── Another_Child.rst
```

**Key Points:**

- Images are shared in `_images/` at the root (not duplicated)
- Paths automatically adjust: root uses `_images/`, children use `../_images/`, etc.
- Each page gets its own folder (parent → child → grandchild hierarchy)

### Quick Command Reference

```bash
# Single page export
python confluence_export.py --site SITE --page ID --html
```

### Supporting Files

- **`myModules.py`** - Core export functions (used by both tools)
- **`styles/confluence.css`** - Confluence CSS styling

## 🔍 Troubleshooting

### How to Find Your Page ID

**Method 1: From URL**

```
URL: <https://confluence.example.com/pages/796450310/Page+Title>
Page ID: 796450310
```

**Method 2: Page Information**

1. Go to the page in Confluence
2. Click "..." menu → "Page Information"
3. Look at the URL: `/pages/pageinfo.action?pageId=796450310`

### "Could not load cookies"

**Solution:**

- ✅ Make sure you're logged into Confluence in your browser
- ✅ Try opening a Confluence page first to ensure session is active
- ✅ Try a different browser (Chrome, Firefox, Safari, Edge)
- ✅ On macOS: Grant Terminal access to browser data

**On macOS with Safari:**

1. System Preferences → Security & Privacy → Privacy
2. Select "Full Disk Access"
3. Add Terminal (or your terminal app)
4. Restart terminal

### "Authentication failed"

**Solution:**

- ✅ Your browser session expired - login again in browser
- ✅ Clear cookies and login fresh
- ✅ Check that you can access Confluence pages in browser
- ✅ Try: Open a Confluence page in browser, then **immediately** run the tool

### Images not showing in HTML

**Problem:** You open the HTML and images are broken

**Solution:**

- Images are in `_images/` folder at the root level
- Open HTML files from their correct location (don't move them)
- For nested pages, paths automatically use `../` or `../../`

**Example structure:**

```
output/796450310-Page/
├── \_images/ ← Images stored here
│ └── diagram.png
├── Page.html ← Uses_images/diagram.png
└── Child/
└── Child.html ← Uses ../\_images/diagram.png
```

### "Module not found" errors

**Solution:**

```bash
# Install Python dependencies
pip install browser-cookie3 requests beautifulsoup4 pypandoc Pillow

# Install Pandoc (system package)
brew install pandoc              # macOS
sudo apt-get install pandoc      # Ubuntu/Debian
choco install pandoc             # Windows
```

### Export is Slow

**Solution: Use more workers**

```bash
# Increase concurrent workers (default: 5)
python confluence_export.py --site SITE --page ID --workers 10
```

**⚠️ Note:** Too many workers (>20) may hit rate limits or cause connection issues.

## 🔐 How SSO Authentication Works

1. **Login** to Confluence in your browser (Chrome, Firefox, Safari, or Edge)
2. The tool **extracts session cookies** from your browser
3. Uses those cookies to **authenticate API requests**
4. **No need** for PAT tokens, API keys, or passwords!

**Supported SSO Providers:**

- Azure AD (Microsoft)
- Okta
- SAML
- Any SSO that works with browser cookies

**Supported Browsers:**

- Chrome
- Firefox
- Safari
- Edge

## 🛠️ What It Does

- Leverages the **Confluence Cloud REST API (V1)**
- Stores Confluence metadata (Page ID, Labels) in HTML headers and RST fields
- Uses **BeautifulSoup** to parse and update HTML content
- Downloads **all attachments**, emoticons, and embedded files
- Converts HTML to RST using **Pandoc**
- Creates **hierarchical folder structure** for page trees
- Generates **dynamic relative paths** for images in nested pages
- **Concurrent processing** for speed

## 📝 Known Issues

- **Long attachment filenames** may cause issues - rename in Confluence first
- **Old emoticons** from Server migrations may not work - convert pages to New Editor
- **Browser session must be active** during export (don't logout mid-export)
- **Rate limiting** may occur with too many workers (>20)

## 🗺️ Roadmap

- [x] SSO authentication support
- [x] Hierarchical folder structure
- [x] Concurrent processing (5-10x faster)
- [x] Dynamic relative paths for nested pages
- [ ] Generate index/TOC file
- [ ] Resume interrupted exports
- [ ] Progress bar for large exports

## 📜 Version History

- **2.0** (2025)
  - ✨ Added SSO authentication support (Azure AD, Okta, SAML)
  - 📁 Added hierarchical folder structure (parent → child → grandchild)
  - ⚡ Added concurrent processing (5-10x faster)
  - 🔧 Refactored codebase with better structure
  - 🔗 Dynamic relative paths for nested pages
  - 🖼️ Shared images folder (no duplication)
- **1.4**
  - Refactoring into simpler file setup
- **1.3**
  - Added Space export (flat folder structure)
- **1.2**
  - Better HTML header and footer
  - Added page labels to HTML headers
- **1.1**
  - Added Page Properties dump
- **1.0**
  - Initial Release

## 👥 Authors

**Original:** @dernorberto  
**SSO Support & v2.0:** Modified 2025

## 📄 License

This project is licensed under the MIT License - see the LICENSE.txt file for details

## 📚 Additional Documentation

- **`tools/`** - Helper scripts for testing and diagnostics
- **Issues?** Open a GitHub issue with:
  - Command you ran
  - Error message
  - Confluence version (Cloud/Server/DC)
