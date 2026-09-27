import asyncio
import urllib.parse

from bs4 import BeautifulSoup

from core.http_client import get_client
from sources.base import Source


class WuxiaSpotSource(Source):
    search_supported = False

    def __init__(self):
        self._client = get_client()
        self._cover_cache: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "wuxiaspot"

    @property
    def label(self) -> str:
        return "WuxiaSpot"
    @property
    def ascii_art(self) -> str:
        return """
    ██╗    ██╗██╗   ██╗██╗  ██╗██╗ █████╗    ███████╗██████╗  ██████╗ ████████╗
    ██║    ██║██║   ██║██║  ██║██║██╔══██╗   ██╔════╝██╔══██╗██╔═══██╗╚══██╔══╝
    ██║ █╗ ██║██║   ██║███████║██║███████║   ███████╗██████╔╝██║   ██║   ██║
    ██║███╗██║██║   ██║██╔══██║██║██╔══██║   ╚════██║██╔═══╝ ██║   ██║   ██║
    ╚███╔███╔╝╚██████╔╝██║  ██║██║██║  ██║██╗███████║██║     ╚██████╔╝   ██║
     ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚═╝╚══════╝╚═╝      ╚═════╝    ╚═╝"""
    @property
    def browse_urls(self) -> dict[str, str]:
        return {
            "hot": "https://www.wuxiaspot.com/list/all/all-onclick-0.html",
            "latest": "https://www.wuxiaspot.com/list/all/all-newstime-0.html",
            "popular": "https://www.wuxiaspot.com/list/all/all-onclick-0.html",
            "new": "https://www.wuxiaspot.com/list/all/all-newstime-0.html",
            "updates": "https://www.wuxiaspot.com/list/all/all-lastdotime-0.html",
            "ongoing": "https://www.wuxiaspot.com/list/all/Ongoing-onclick-0.html",
            "completed": "https://www.wuxiaspot.com/list/all/Completed-onclick-0.html",
        }

    @property
    def genres(self) -> dict[str, str]:
        return {
            "action": "Action",
            "adventure": "Adventure",
            "comedy": "Comedy",
            "drama": "Drama",
            "eastern": "Eastern",
            "ecchi": "Ecchi",
            "erciyuan": "Erciyuan",
            "fan-fiction": "Fan-Fiction",
            "fantasy": "Fantasy",
            "fantasy-romance": "Fantasy Romance",
            "game": "Game",
            "gender-bender": "Gender Bender",
            "girls-channel": "Girls Channel",
            "harem": "Harem",
            "historical": "Historical",
            "historical-romance": "Historical Romance",
            "horror": "Horror",
            "josei": "Josei",
            "magic": "Magic",
            "magical-realism": "Magical Realism",
            "martial-arts": "Martial Arts",
            "mecha": "Mecha",
            "military": "Military",
            "mystery": "Mystery",
            "other": "Other",
            "psychological": "Psychological",
            "romance": "Romance",
            "school-life": "School Life",
            "sci-fi": "Sci-Fi",
            "science-fiction": "Science Fiction",
            "seinen": "Seinen",
            "shoujo": "Shoujo",
            "shoujo-ai": "Shoujo Ai",
            "shounen": "Shounen",
            "shounen-ai": "Shounen Ai",
            "slice-of-life": "Slice Of Life",
            "smut": "Smut",
            "sports": "Sports",
            "supernatural": "Supernatural",
            "tragedy": "Tragedy",
            "two-dimensional": "Two-dimensional",
            "urban": "Urban",
            "urban-life": "Urban Life",
            "video-games": "Video Games",
            "virtual-reality": "Virtual Reality",
            "war": "War",
            "wuxia": "Wuxia",
            "xianxia": "Xianxia",
            "xuanhuan": "Xuanhuan",
            "yaoi": "Yaoi",
            "yuri": "Yuri",
        }

    async def fetch_url(self, url: str, params: dict | None = None):
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def parse_slug(self, url: str) -> str | None:
        o = urllib.parse.urlparse(url)
        if o.hostname and "wuxiaspot.com" in o.hostname:
            path = o.path.removesuffix(".html").rstrip("/")
            parts = path.split("/")
            if "novel" in parts:
                idx = parts.index("novel")
                return "/".join(parts[idx + 1:])


    def qualify_slug(self, slug: str) -> str:
        return f"wuxiaspot:{slug}"

    @staticmethod
    def _absolutize(url: str) -> str:
        if url.startswith("/"):
            return "https://www.wuxiaspot.com" + url
        return url

    def extract_novel_rows(self, soup) -> list[dict]:
        results = []
        items = soup.select(".novel-item")
        for item in items:
            link = item.select_one("a[href*='/novel/']")
            if not link:
                continue
            href = link.get("href", "")
            slug = self.parse_slug("https://www.wuxiaspot.com" + href)
            title_el = item.select_one(".novel-title")
            title = title_el.text.strip() if title_el else ""
            img = item.select_one(".novel-cover img.lazy")
            cover = img.get("data-src", "") if img else ""
            cover = self._absolutize(cover)
            if slug:
                self._cover_cache[slug] = cover
            results.append({
                "title": title,
                "author": "Unknown",
                "slug": slug or "",
                "latest": "",
                "cover": cover,
            })
        return results

    async def search(self, query: str, page: int = 1) -> tuple[list[dict], int]:
        try:
            search_url = "https://www.wuxiaspot.com/e/search/index.php"
            data = {
                "keyboard": query,
                "show": "title",
                "tempid": "1",
                "tbname": "news",
            }
            response = await self._client.post(search_url, data=data)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception:
            return [], 0

        page_links = soup.select(".pagination a")
        searchid = None
        total_pages = 1
        for a in page_links:
            href = str(a.get("href") or "")
            text = a.text.strip()
            if text.isdigit():
                num = int(text)
                if num > total_pages:
                    total_pages = num
            if "searchid=" in href:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                if "searchid" in qs:
                    searchid = qs["searchid"][0]

        if page > 1 and searchid:
            try:
                result_url = f"https://www.wuxiaspot.com/e/search/result/index.php?page={page - 1}&searchid={searchid}"
                response = await self._client.get(result_url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
            except Exception:
                return self.extract_novel_rows(soup), total_pages

        novels = self.extract_novel_rows(soup)
        return novels, total_pages

    async def fetch_chapters(self, slug: str) -> list[dict]:
        url = f"https://www.wuxiaspot.com/novel/{slug}.html"
        soup = await self.fetch_url(url)
        chapters = []

        links = soup.select(".chapter-list li a")
        for a in links:
            href = str(a.get("href") or "")
            title_el = a.select_one(".chapter-title")
            title = title_el.text.strip() if title_el else a.text.strip()
            if href and not href.startswith("http"):
                href = "https://www.wuxiaspot.com" + href
            chapters.append({"num": 0, "title": title, "url": href})

        page_links = soup.select("#chpagedlist .pagination a")
        total_pages = 1
        for a in page_links:
            text = a.text.strip()
            if text.isdigit():
                num = int(text)
                if num > total_pages:
                    total_pages = num

        async def fetch_page(p):
            try:
                page_url = f"https://www.wuxiaspot.com/e/extend/fy.php?page={p}&wjm={slug}"
                resp = await self._client.get(page_url)
                resp.raise_for_status()
                page_soup = BeautifulSoup(resp.text, "html.parser")
                page_chapters = []
                for a in page_soup.select(".chapter-list li a"):
                    href = str(a.get("href") or "")
                    title_el = a.select_one(".chapter-title")
                    title = title_el.text.strip() if title_el else a.text.strip()
                    if href and not href.startswith("http"):
                        href = "https://www.wuxiaspot.com" + href
                    page_chapters.append({"num": 0, "title": title, "url": href})
                return page_chapters
            except Exception:
                return []

        if total_pages > 1:
            results = await asyncio.gather(*[fetch_page(p) for p in range(1, total_pages)])
            for page_chs in results:
                chapters.extend(page_chs)

        for i, ch in enumerate(chapters, 1):
            ch["num"] = i
        return chapters


    async def read_chapter(self, url: str) -> list[str] | None:
        try:
            soup = await self.fetch_url(url)
            content = soup.select_one(".chapter-content")
            if not content:
                return None
            text = content.get_text("\n", strip=True)
            return [p.strip() for p in text.split("\n") if p.strip()]
        except Exception:
            return None

    async def cover_url(self, slug: str) -> str:
        try:
            cached = self._cover_cache.get(slug)
            if cached:
                return cached
            url = f"https://www.wuxiaspot.com/novel/{slug}.html"
            soup = await self.fetch_url(url)
            img = soup.select_one(".cover img.lazy")
            if img:
                src = img.get("data-src") or img.get("src") or ""
                src = self._absolutize(str(src))
                self._cover_cache[slug] = src
                return src
        except Exception:
            pass
        return ""

    async def browse_genre(self, genre_slug: str) -> list[dict]:
        try:
            url = f"https://www.wuxiaspot.com/list/{genre_slug}/all-newstime-0.html"
            soup = await self.fetch_url(url)
            return self.extract_novel_rows(soup)
        except Exception:
            return []

    def novel_url(self, slug: str) -> str:
        return f"https://www.wuxiaspot.com/novel/{slug}.html"

    async def get_novel_info(self, slug: str) -> dict:
        url = f"https://www.wuxiaspot.com/novel/{slug}.html"
        soup = await self.fetch_url(url)
        author_el = soup.select_one(".novel-author") or soup.select_one(".author")
        author = author_el.get_text(strip=True) if author_el else "Unknown"
        desc_el = soup.select_one(".novel-desc") or soup.select_one(".description") or soup.select_one(".summary")
        description = desc_el.get_text("\n\n", strip=True) if desc_el else "No description available."
        return {"author": author, "description": description}






