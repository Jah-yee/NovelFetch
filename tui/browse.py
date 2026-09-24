from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import (
    Footer,
    Input,
    LoadingIndicator,
    OptionList,
    Static,
)
from textual.widgets.option_list import Option

from core.progress import progress
from tui.download import DownloadDialog
from tui.reader import ReaderScreen
from tui.shared import CustomHeader
from tui.utils import _get_chapters, _get_source


def _novel_to_option(novel: dict) -> Option:
    sub = novel.get("author", "")
    if novel.get("latest"):
        sub += f"  ·  {novel['latest']}"
    text = novel["title"]
    if sub:
        text += f"\n{sub}"
    return Option(text, id=novel["slug"])


class SearchScreen(Screen):
    BINDINGS = [
        Binding("escape", "clear_or_pop", "Back"),
        Binding("n", "next_page", "Next"),
        Binding("p", "prev_page", "Prev"),
    ]

    def __init__(self, source):
        super().__init__()
        self.source = source
        self._query = ""
        self._page = 1
        self._total_pages = 1
        self._results = []
        self._search_timer = None
        self._fetch_lock = False

    def compose(self):
        yield CustomHeader()
        yield Input(placeholder="Search novels...")
        yield Static("", id="page-info")
        yield OptionList(id="search-results")
        yield LoadingIndicator(classes="loading")
        yield Footer()

    def on_mount(self):
        self.query_one(Input).focus()

    def on_input_changed(self, event: Input.Changed):
        q = event.value.strip()
        if q == self._query:
            return
        self._query = q
        self._page = 1
        self._total_pages = 1
        self._results = []
        self._clear_list()
        self.query_one("#page-info").update("")
        if self._search_timer:
            self._search_timer.stop()
        if self._query:
            self._search_timer = self.set_timer(0.75, self._do_search)

    def _clear_list(self):
        ol = self.query_one("#search-results", OptionList)
        ol.clear_options()

    async def _do_search(self):
        if not self._query:
            return
        await self._fetch_page()

    async def _fetch_page(self):
        if self._fetch_lock:
            return
        self._fetch_lock = True
        inp = self.query_one(Input)
        inp.disabled = True
        self.query_one(LoadingIndicator).set_class(True, "-visible")
        try:
            novels, total_pages = await self.source.search(self._query, self._page)
            self._results = novels
            self._total_pages = total_pages
            self._show_results(novels)
        except Exception:
            self.notify("Search failed. Check internet.", timeout=3)
        finally:
            self._fetch_lock = False
            inp.disabled = False
            self.query_one(LoadingIndicator).set_class(False, "-visible")

    def _show_results(self, novels):
        ol = self.query_one("#search-results", OptionList)
        ol.clear_options()
        for n in novels:
            ol.add_option(_novel_to_option(n))
        pi = self.query_one("#page-info")
        if not novels:
            pi.update("No novels found")
        elif self._total_pages > 1:
            pi.update(f"{len(novels)} results — Page {self._page}/{self._total_pages}")
        else:
            pi.update(f"{len(novels)} results")

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        idx = event.option_list.index
        if idx is None or idx >= len(self._results):
            return
        event.option_list.disabled = True
        self.query_one(LoadingIndicator).set_class(True, "-visible")
        try:
            slug = self._results[idx]["slug"]
            chapters = await _get_chapters(self.source, slug)
            if chapters:
                self.app.push_screen(
                    ChapterListScreen(
                        chapters, self.source.qualify_slug(slug), source=self.source
                    )
                )
            else:
                self.notify("No chapters found.", timeout=3)
        except Exception:
            self.notify("Failed to fetch chapters. Check your connection.", timeout=3)
        finally:
            self.query_one(LoadingIndicator).set_class(False, "-visible")
            event.option_list.disabled = False

    def action_next_page(self):
        if self._page < self._total_pages and not self._fetch_lock:
            self._page += 1
            self._clear_list()
            self.run_worker(self._fetch_page(), exclusive=True)

    def action_prev_page(self):
        if self._page > 1 and not self._fetch_lock:
            self._page -= 1
            self._clear_list()
            self.run_worker(self._fetch_page(), exclusive=True)

    def action_clear_or_pop(self):
        inp = self.query_one(Input)
        ol = self.query_one("#search-results", OptionList)
        if inp.value:
            inp.value = ""
            self._clear_list()
            self.query_one("#page-info").update("")
        elif ol.option_count > 0:
            self._clear_list()
            self._results = []
            self.query_one("#page-info").update("")
        else:
            self.app.pop_screen()

    def action_pop(self):
        self.app.pop_screen()


class NovelListScreen(Screen):
    BINDINGS = [Binding("escape", "pop", "Back")]

    def __init__(self, novels: list, source=None):
        super().__init__()
        self.novels = novels
        self.source = source

    def compose(self):
        yield CustomHeader()
        options = [_novel_to_option(n) for n in self.novels]
        yield OptionList(*options, id="novel-list")
        yield LoadingIndicator(classes="loading")
        yield Footer()

    async def on_mount(self):
        self.query_one("#novel-list", OptionList).focus()

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        idx = event.option_list.index
        if idx is None:
            return
        event.option_list.disabled = True
        self.query_one(LoadingIndicator).set_class(True, "-visible")
        try:
            novel = self.novels[idx]
            slug = novel["slug"]
            source = self.source or _get_source(slug)
            if not source:
                self.notify("No source found for this novel.", timeout=3)
                return
            bare = slug.split(":", 1)[-1] if ":" in slug else slug
            chapters = await _get_chapters(source, bare)
            if chapters:
                self.app.push_screen(
                    ChapterListScreen(
                        chapters, source.qualify_slug(bare), source=source
                    )
                )
            else:
                self.notify("No chapters found.", timeout=3)
        except Exception:
            self.notify("Failed to fetch chapters. Check your connection.", timeout=3)
        finally:
            self.query_one(LoadingIndicator).set_class(False, "-visible")
            event.option_list.disabled = False

    def action_pop(self):
        self.app.pop_screen()


class ChapterListScreen(Screen):
    def __init__(self, chapters: list, slug: str, source=None):
        super().__init__()
        self.chapters = chapters
        self.slug = slug
        self.source = source

    BINDINGS = [
        Binding("escape", "pop", "Back"),
        Binding("c", "continue_reading", "Continue"),
        Binding("d", "download_dialog", "Download"),
    ]

    def compose(self):
        yield CustomHeader()
        yield Static(f"Chapters: 1-{len(self.chapters)}", classes="title")
        seen = progress.get_seen(self.slug)
        options = [
            Option(("✓ " if i in seen else "  ") + c["title"])
            for i, c in enumerate(self.chapters)
        ]
        yield OptionList(*options, id="chapter-list")
        yield Footer()

    def on_mount(self):
        self.query_one("#chapter-list", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        idx = event.option_list.index
        if idx is None:
            return
        self.app.push_screen(
            ReaderScreen(self.chapters, self.slug, source=self.source, start=idx)
        )

    def action_continue_reading(self):
        idx = progress.get_last(self.slug)
        if idx is not None and 0 <= idx < len(self.chapters):
            self.app.push_screen(
                ReaderScreen(self.chapters, self.slug, source=self.source, start=idx)
            )
        else:
            self.notify("No saved progress.", timeout=2)

    def action_download_dialog(self):
        self.app.push_screen(
            DownloadDialog(
                self.chapters,
                self.slug,
                self.source,
                current_idx=None,
                has_translation=False,
            )
        )

    def action_pop(self):
        self.app.pop_screen()


class GenreScreen(Screen):
    BINDINGS = [Binding("escape", "pop", "Back")]

    def __init__(self, source):
        super().__init__()
        self.source = source

    def compose(self):
        yield CustomHeader()
        yield Static("Genres", classes="title")
        yield OptionList(
            *[Option(name) for name in self.source.genres.values()],
            id="genre-list",
        )
        yield LoadingIndicator(classes="loading")
        yield Footer()

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        idx = event.option_list.index
        if idx is None:
            return
        event.option_list.disabled = True
        self.query_one(LoadingIndicator).set_class(True, "-visible")
        try:
            slug = list(self.source.genres.keys())[idx]
            novels = await self.source.browse_genre(slug)
            if novels:
                self.app.push_screen(NovelListScreen(novels, source=self.source))
            else:
                self.notify("No results.", timeout=3)
        except Exception:
            self.notify("Failed to load genre. Check your connection.", timeout=3)
        finally:
            self.query_one(LoadingIndicator).set_class(False, "-visible")
            event.option_list.disabled = False

    def on_mount(self):
        self.query_one("#genre-list", OptionList).focus()

    def action_pop(self):
        self.app.pop_screen()
