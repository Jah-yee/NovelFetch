import asyncio
import urllib.parse

from bs4 import BeautifulSoup

from core.http_client import get_client_with_headers
from sources.base import Source


class ScribbleHubSource(Source):
    _headers = {
        "Referer": "https://www.scribblehub.com/",
    }

    def __init__(self):
        self._blocked = False
        # Lazily-created, reused across calls (only when curl_cffi is
        # unavailable) so the fallback path keeps one pooled/keep-alive
        # connection instead of paying a fresh TCP+TLS handshake, plus a
        # thread-pool hop, on every single request.
        self._httpx_client = None

    @property
    def blocked(self) -> bool:
        return self._blocked

    @staticmethod
    def _absolutize(url: str) -> str:
        if url.startswith("/"):
            return "https://www.scribblehub.com" + url
        return url

    def _get_httpx_client(self):
        if self._httpx_client is None:
            self._httpx_client = get_client_with_headers(
                ScribbleHubSource._headers)
        return self._httpx_client

    async def _fetch(self, url: str, data: dict | None = None):
        # curl_cffi is a compiled AAPI extension that python-for-android cannot
        # cross-build reliably. Import lazily so the module (and the whole app)
        # still imports when it is unavailable; requests fall back to plain
        # http for a source that is Cloudflare-blocked anyway.
        try:
            from curl_cffi import requests as curl_requests
        except (ImportError, OSError):
            client = self._get_httpx_client()
            if data:
                resp = await client.post(url, data=data)
            else:
                resp = await client.get(url)
            if resp.status_code in (403, 429) or "Just a moment" in resp.text:
                self._blocked = True
            return resp

        if data:
            response = await asyncio.to_thread(
                lambda: curl_requests.post(url, data=data, impersonate="chrome120", headers=ScribbleHubSource._headers)
            )
        else:
            response = await asyncio.to_thread(
                lambda: curl_requests.get(url, impersonate="chrome120", headers=ScribbleHubSource._headers)
            )
        if response.status_code in (403, 429) or "Just a moment" in response.text:
            self._blocked = True
        return response

    @property
    def name(self) -> str:
        return "scribblehub"

    @property
    def label(self) -> str:
        return "ScribbleHub"
    @property
    def ascii_art(self) -> str:
        return """\
███████╗ ██████╗██████╗ ██╗██████╗ ██████╗ ██╗     ███████╗██╗  ██╗██╗   ██╗██████╗
██╔════╝██╔════╝██╔══██╗██║██╔══██╗██╔══██╗██║     ██╔════╝██║  ██║██║   ██║██╔══██╗
███████╗██║     ██████╔╝██║██████╔╝██████╔╝██║     █████╗  ███████║██║   ██║██████╔╝
╚════██║██║     ██╔══██╗██║██╔══██╗██╔══██╗██║     ██╔══╝  ██╔══██║██║   ██║██╔══██╗
███████║╚██████╗██║  ██║██║██████╔╝██████╔╝███████╗███████╗██║  ██║╚██████╔╝██████╔╝
╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝╚═════╝ ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝"""

    @property
    def browse_urls(self) -> dict[str, str]:
        return {
            "hot": "https://www.scribblehub.com/series-ranking/",
            "latest": "https://www.scribblehub.com/latest-series/",
            "popular": "https://www.scribblehub.com/series-finder/?sf=1&sort=pageviews&order=desc",
            "completed": "https://www.scribblehub.com/series-finder/?sf=1&cp=completed",
        }

    @property
    def genres(self) -> dict[str, str]:
        return {
            "action": "Action",
            "adventure": "Adventure",
            "comedy": "Comedy",
            "drama": "Drama",
            "ecchi": "Ecchi",
            "fanfiction": "Fanfiction",
            "fantasy": "Fantasy",
            "harem": "Harem",
            "historical": "Historical",
            "horror": "Horror",
            "isekai": "Isekai",
            "josei": "Josei",
            "litrpg": "LitRPG",
            "martial-arts": "Martial Arts",
            "mature": "Mature",
            "mecha": "Mecha",
            "mystery": "Mystery",
            "psychological": "Psychological",
            "romance": "Romance",
            "school-life": "School Life",
            "sci-fi": "Sci-fi",
            "seinen": "Seinen",
            "slice-of-life": "Slice of Life",
            "sports": "Sports",
            "supernatural": "Supernatural",
            "tragedy": "Tragedy",
        }

    async def fetch_url(self, url: str, params: dict | None = None):
        response = await self._fetch(url)
        return BeautifulSoup(response.text, "html.parser")

    def parse_slug(self, url: str) -> str | None:
        o = urllib.parse.urlparse(url)
        if o.hostname and "scribblehub.com" in o.hostname:
            parts = o.path.split("/")
            if "series" in parts:
                idx = parts.index("series")
                slug = "/".join(parts[idx + 1:]).rstrip("/")
                return slug

    def qualify_slug(self, slug: str) -> str:
        return f"scribblehub:{slug}"

    def extract_novel_rows(self, soup) -> list[dict]:
        results = []
        rows = soup.select(".search_main_box")
        for row in rows:
            title_tag = row.select_one(".search_title a")
            if not title_tag:
                continue
            href = title_tag.get("href", "")
            slug = self.parse_slug(href)
            img_tag = row.select_one(".search_img img")
            cover = img_tag.get("src", "") if img_tag else ""
            cover = self._absolutize(cover)
            author_tag = row.select_one(".search_stats span[title='Author'] .a_un_st a")
            author = author_tag.text.strip() if author_tag else "Unknown"
            results.append({
                "title": title_tag.text.strip(),
                "author": author,
                "slug": slug or "",
                "latest": "",
                "cover": cover,
            })
        return results

    async def search(self, query: str, page: int = 1) -> tuple[list[dict], int]:
        url = f"https://www.scribblehub.com/series-finder/?sf=1&sh={query}&pg={page}"
        soup = await self.fetch_url(url)
        novels = self.extract_novel_rows(soup)
        total_pages = 50  # generous upper bound
        if not novels:
            total_pages = page - 1  # no results means went past the last page
        return novels, total_pages

    async def read_chapter(self, url: str) -> list[str] | None:
        soup = await self.fetch_url(url)
        content = soup.select_one("#chp_raw")
        if not content:
            return None
        return [p.get_text(strip=True) for p in content.find_all("p")]

    async def cover_url(self, slug: str) -> str:
        url = f"https://www.scribblehub.com/series/{slug}/"
        soup = await self.fetch_url(url)
        img = soup.select_one(".fic_image img")
        if img:
            src = img.get("data-src") or img.get("src") or ""
            return self._absolutize(str(src))
        return ""

    async def browse_genre(self, genre_slug: str) -> list[dict]:
        url = f"https://www.scribblehub.com/genre/{genre_slug}/"
        soup = await self.fetch_url(url)
        return self.extract_novel_rows(soup)


    async def fetch_chapters(self, slug: str) -> list[dict]:
        url = f"https://www.scribblehub.com/series/{slug}/"
        soup = await self.fetch_url(url)
        mypostid_input = soup.select_one("input#mypostid")
        if not mypostid_input:
            return []
        mypostid = mypostid_input.get("value", "")
        ajax_url = "https://www.scribblehub.com/wp-admin/admin-ajax.php"
        response = await self._fetch(ajax_url, data={
            "action": "wi_getreleases_pagination",
            "pagenum": -1,
            "mypostid": mypostid,
        })
        chapter_soup = BeautifulSoup(response.text, "html.parser")
        chapters = []
        links = chapter_soup.select(".toc_ol a.toc_a")
        for i, a in enumerate(reversed(links), 1):
            href = str(a.get("href", ""))
            if href and not href.startswith("http"):
                href = "https://www.scribblehub.com" + href
            chapters.append({
                "num": i,
                "title": a.text.strip(),
                "url": href,
            })
        return chapters

    def novel_url(self, slug: str) -> str:
        return f"https://www.scribblehub.com/series/{slug}/"

    async def get_novel_info(self, slug: str) -> dict:
        url = f"https://www.scribblehub.com/series/{slug}/"
        soup = await self.fetch_url(url)
        author_el = soup.select_one(".fic_author a") or soup.select_one(".author a")
        author = author_el.get_text(strip=True) if author_el else "Unknown"
        desc_el = soup.select_one(".wi_fic_desc") or soup.select_one(".description")
        description = desc_el.get_text("\n\n", strip=True) if desc_el else "No description available."
        return {"author": author, "description": description}
