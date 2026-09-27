from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Label, ListItem, ListView, LoadingIndicator, Static

from sources import REGISTRY
from tui.shared import CustomHeader


class MainMenu(Screen):
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("s", "switch_source", "Source"),
        Binding("enter", "select", "Select", show=True),
        Binding("up", "navigate_up", "Up", show=False),
        Binding("down", "navigate_down", "Down", show=False),
    ]

    def compose(self):
        yield CustomHeader()
        with Vertical(id="main-content"):
            yield Static("", id="banner", classes="banner")
            with Vertical(id="primary-group", classes="section-group"):
                yield Static("PRIMARY ACTIONS", classes="section-header")
                yield ListView(
                    ListItem(Label("Search by name"), id="search"),
                    ListItem(Label("My Library"), id="library"),
                    id="primary-actions"
                )
            with Vertical(id="browse-group", classes="section-group"):
                yield Static("BROWSE", classes="section-header")
                yield ListView(
                    ListItem(Label("Hot novels"), id="hot"),
                    ListItem(Label("Latest releases"), id="latest"),
                    ListItem(Label("Most popular"), id="popular"),
                    ListItem(Label("Completed novels"), id="completed"),
                    ListItem(Label("Browse by genre"), id="genre"),
                    id="browse-actions"
                )
            yield LoadingIndicator(classes="loading")
        yield Footer()

    def on_mount(self):
        self.app.current_source = list(REGISTRY.values())[0]
        self._update_banner()
        self.query_one("#primary-actions", ListView).focus()

    def _update_banner(self):
        src = self.app.current_source
        self.query_one("#banner", Static).update(src.ascii_art)

    async def on_list_view_selected(self, event: ListView.Selected):
        item_id = event.item.id
        if not item_id:
            return

        for lv_id in ["primary-actions", "browse-actions"]:
            self.query_one(f"#{lv_id}", ListView).disabled = True
        self.query_one(LoadingIndicator).set_class(True, "-visible")

        try:
            src = self.app.current_source
            if item_id == "search":
                from tui.browse import SearchScreen
                self.app.push_screen(SearchScreen(source=src))
            elif item_id == "library":
                from tui.library import MyLibraryScreen
                self.app.push_screen(MyLibraryScreen())
            elif item_id == "genre":
                from tui.browse import GenreScreen
                self.app.push_screen(GenreScreen(source=src))
            else:
                soup = await src.fetch_url(src.browse_urls[item_id])
                novels = src.extract_novel_rows(soup)
                from tui.browse import NovelListScreen
                self.app.push_screen(NovelListScreen(novels, source=src))
        except Exception:
            self.notify("Failed to fetch novels. Check your connection.", timeout=3)
        finally:
            for lv_id in ["primary-actions", "browse-actions"]:
                self.query_one(f"#{lv_id}", ListView).disabled = False
            self.query_one(LoadingIndicator).set_class(False, "-visible")

    def action_quit(self):
        self.app.exit()

    def action_select(self):
        focused = self.app.focused
        if isinstance(focused, ListView):
            focused.action_select_cursor()

    def action_navigate_up(self):
        focused = self.app.focused
        if isinstance(focused, ListView):
            focused.action_cursor_up()

    def action_navigate_down(self):
        focused = self.app.focused
        if isinstance(focused, ListView):
            focused.action_cursor_down()

    def action_switch_source(self):
        from tui.source_picker import SourcePickerScreen

        sources = list(REGISTRY.values())
        current = self.app.current_source
        items = []
        for src in sources:
            marker = "●" if src == current else "○"
            items.append({"label": f"{marker} {src.label}", "id": src.name})

        def on_select(src_name):
            if src_name:
                self.app.current_source = REGISTRY[src_name]
                self._update_banner()
                self.notify(f"Switched to {REGISTRY[src_name].label}")

        self.app.push_screen(SourcePickerScreen(items, on_select))
