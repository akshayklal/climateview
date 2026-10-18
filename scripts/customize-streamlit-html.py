#!/usr/bin/env python3
"""Customize Streamlit's initial HTML metadata and generate the public sitemap.

Streamlit's st.set_page_config changes the title after the frontend loads;
its installed HTML template initially contains <title>Streamlit</title>.
This build-time workaround gives View Page Source and clients that do not
run JavaScript meaningful metadata. It does not prerender the app content.

Each build also generates sitemap.xml beside Streamlit's installed index.html
for https://climatepatterns.app/sitemap.xml. It lists the homepage and each
configured station's ?location= URL. Submit that URL in Bing Webmaster Tools
and Google Search Console after deployment. No separate script or additional
Render command is needed; the sitemap is regenerated as stations change.

Render setup (configure this manually in the Render dashboard):
  Web service -> Settings -> Build & Deploy -> Build Command
  pip install -r requirements.txt && python scripts/customize-streamlit-html.py

If the service already has other build steps, preserve them and run this
script after the final dependency installation. Leave the Start Command
unchanged. Commit this script to GitHub; Render's automatic deploy then
runs it on each build, before the server starts. Merely committing this
file does not configure Render's Build Command.

The script locates Streamlit in the active Python environment, so no local
.venv path is needed on Render. Keep .venv in .gitignore. Reinstalling or
upgrading Streamlit can replace its template, which is why this runs after
installation. Repeated runs are safe and do not duplicate metadata.

Keep PAGE_TITLE consistent with st.set_page_config in app.py if the browser
title should remain identical after loading. This template is shared by all
locations, so use site-wide metadata and do not add a fixed canonical URL.
"""

from html import escape
from importlib.util import find_spec
from pathlib import Path
import re
import sys
from urllib.parse import urlencode
from xml.etree import ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from climateview.stations import STATIONS


PAGE_TITLE = "Climate Patterns | Explore long term climate and air quality trends in your local area."
PAGE_DESCRIPTION = ("Explore long term climate and air quality trends in your local area.")
# Bing Webmaster Tools checks this tag in the HTML head to verify ownership.
# Render injects it during the same build step as the title and description.
# Keep the tag deployed after verification so ownership can be rechecked.
BING_VERIFICATION = "1221DC0CE7576F3B71F911A5621ADC28"
SITE_URL = "https://climatepatterns.app"


def generate_sitemap() -> str:
    """List stable location URLs; omit session-only tab and filter states."""
    root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    urls = [f"{SITE_URL}/"]
    urls.extend(
        f"{SITE_URL}/?{urlencode({'location': station_key})}"
        for station_key in sorted(STATIONS)
    )
    for url in urls:
        entry = ET.SubElement(root, "url")
        ET.SubElement(entry, "loc").text = url
    # Do not invent lastmod dates from build time; deployment is not a data update.
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8") + "\n"


def customize_html(html: str) -> str:
    """Update only head metadata, preserving Streamlit's versioned assets."""
    head = re.search(r"<head\b[^>]*>(.*?)</head\s*>", html, re.IGNORECASE | re.DOTALL)
    if head is None:
        raise ValueError("Streamlit template has no <head>; template may have changed.")

    content = head.group(1)
    content, title_count = re.subn(
        r"<title\b[^>]*>.*?</title\s*>",
        lambda _: f"<title>{escape(PAGE_TITLE)}</title>",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if title_count != 1:
        raise ValueError("Expected exactly one title in Streamlit's HTML head.")

    description = (
        f'<meta name="description" content="{escape(PAGE_DESCRIPTION, quote=True)}" />'
    )
    # Match either quote style and attribute order, but not og:description.
    description_pattern = (
        r"<meta\b(?=[^>]*\sname\s*=\s*(['\"])description\1)[^>]*>"
    )
    matches = list(re.finditer(description_pattern, content, re.IGNORECASE))
    if len(matches) > 1:
        raise ValueError("Multiple description tags found; refusing an ambiguous update.")
    if matches:
        content = re.sub(
            description_pattern, lambda _: description, content, flags=re.IGNORECASE
        )
    else:
        content = content.rstrip() + f"\n    {description}\n  "

    bing_tag = (
        f'<meta name="msvalidate.01" content="{escape(BING_VERIFICATION, quote=True)}" />'
    )
    bing_pattern = r"<meta\b(?=[^>]*\sname\s*=\s*(['\"])msvalidate\.01\1)[^>]*>"
    matches = list(re.finditer(bing_pattern, content, re.IGNORECASE))
    if len(matches) > 1:
        raise ValueError("Multiple Bing verification tags found; refusing an ambiguous update.")
    if matches:
        content = re.sub(
            bing_pattern, lambda _: bing_tag, content, flags=re.IGNORECASE
        )
    else:
        content = content.rstrip() + f"\n    {bing_tag}\n  "

    return html[:head.start(1)] + content + html[head.end(1):]


def main() -> None:
    spec = find_spec("streamlit")
    if spec is None or spec.origin is None:
        raise RuntimeError("Install Streamlit before running this script.")
    template = Path(spec.origin).parent / "static" / "index.html"
    original = template.read_text(encoding="utf-8")
    updated = customize_html(original)
    if updated == original:
        print("Streamlit HTML metadata is already up to date.")
    else:
        template.write_text(updated, encoding="utf-8")
        print(f"Updated Streamlit title, description, and Bing verification in {template}")

    # Always generate the sitemap, even when HTML metadata is unchanged.
    sitemap = template.with_name("sitemap.xml")
    sitemap.write_text(generate_sitemap(), encoding="utf-8")
    print(f"Generated {sitemap} with {len(STATIONS) + 1} URLs")


if __name__ == "__main__":
    main()
