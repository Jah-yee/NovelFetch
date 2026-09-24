import contextlib
import os

from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from core.epub import _chapter_sort_key, _export_epub
from core.progress import _scan_library, _slug_to_title, progress
from tui.download import DownloadDialog
from tui.reader import LocalReaderScreen
from tui.shared import CustomHeader
from tui.utils import _get_chapters, _get_source


class MyLibraryScreen(Screen):
    BINDINGS = [
        Binding("escape", "pop", "Back"),
        Binding("x", "delete", "Delete"),
        Binding("e", "export", "Export EPUB"),
    ]

    def compose(self):
        yield CustomHeader()
        yield Static("My Library", classes="title")
        novels = _scan_library()
        if not novels:
            yield Static("No downloaded novels found.", classes="title")
        else:
            options = []
            for n in novels:
                last = progress.get_last(n["slug"])
                suffix = f" · Last: Ch. {last + 1}" if last is not None else ""
                options.append(Option(f"{n['title']}  ({n['count']} ch.){suffix}"))
            yield OptionList(*options, id="library-list")
        yield Footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        idx = event.option_list.index
        if idx is None:
            return
        novels = _scan_library()
        if idx < len(novels):
            self.app.push_screen(LocalChapterScreen(novels[idx]["slug"]))

    def on_mount(self):
        with contextlib.suppress(Exception):
            self.query_one("#library-list", OptionList).focus()

    def action_delete(self):
        ol = self.query_one("#library-list", OptionList)
        idx = ol.highlighted
        if idx is None:
            return
        novels = _scan_library()
        if idx >= len(novels):
            return
        slug = novels[idx]["slug"]
        if getattr(self, "_pending", None) == slug:
            import shutil

            shutil.rmtree(os.path.join("novels", slug))
            self._pending = None
            self.notify(f"Deleted {_slug_to_title(slug)}", timeout=3)
            self.app.pop_screen()
            self.app.push_screen(MyLibraryScreen())
        else:
            self._pending = slug
            self.notify(f"Press x again to delete {_slug_to_title(slug)}", timeout=3)

    def action_export(self):
        ol = self.query_one("#library-list", OptionList)
        idx = ol.highlighted
        if idx is None:
            return
        novels = _scan_library()
        if idx >= len(novels):
            return
        slug = novels[idx]["slug"]
        source = _get_source(slug)
        self.run_worker(self._do_export(slug, source), exclusive=True)

    async def _do_export(self, slug, source):
        try:
            path = await _export_epub(slug, source)
        except ImportError:
            self.notify("ebooklib not installed. Run: pip install ebooklib", timeout=5)
            return
        if path:
            self.notify(f"Exported to {path}", timeout=5)
        else:
            self.notify("No chapters to export.", timeout=3)

    def action_pop(self):
        self._pending = None
        self.app.pop_screen()


class LocalChapterScreen(Screen):
    BINDINGS = [
        Binding("escape", "pop", "Back"),
        Binding("c", "continue_reading", "Continue"),
        Binding("d", "download_dialog", "Download"),
        Binding("x", "delete", "Delete"),
        Binding("e", "export", "Export EPUB"),
    ]

    def __init__(self, slug: str):
        super().__init__()
        self.slug = slug
        self.files = []

    def compose(self):
        yield CustomHeader()
        yield Static(_slug_to_title(self.slug), classes="title")
        yield OptionList(id="local-chapters")
        yield Footer()

    def on_mount(self):
        chap_dir = os.path.join("novels", self.slug)
        if os.path.isdir(chap_dir):
            self.files = []
            for root, _dirs, files in os.walk(chap_dir):
                for f in sorted(files, key=_chapter_sort_key):
                    rel = os.path.relpath(os.path.join(root, f), chap_dir)
                    self.files.append(rel)
            ol = self.query_one("#local-chapters", OptionList)
            seen = progress.get_seen(self.slug)
            options = []
            for i, fname in enumerate(self.files):
                title = (
                    os.path.basename(fname)
                    .replace(".txt", "")
                    .replace("_", " ")
                    .title()
                )
                prefix = "✓ " if i in seen else "  "
                options.append(Option(prefix + title))
            ol.add_options(options)
            ol.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        idx = event.option_list.index
        if idx is None or idx >= len(self.files):
            return
        self.app.push_screen(LocalReaderScreen(self.files, self.slug, start=idx))

    def action_delete(self):
        ol = self.query_one("#local-chapters", OptionList)
        idx = ol.highlighted
        if idx is None or idx >= len(self.files):
            return
        fname = self.files[idx]
        if getattr(self, "_pending", None) == fname:
            os.remove(os.path.join("novels", self.slug, fname))
            self._pending = None
            self.notify("Deleted", timeout=2)
            self.app.pop_screen()
            self.app.push_screen(LocalChapterScreen(self.slug))
        else:
            self._pending = fname
            self.notify("Press x again to delete", timeout=3)

    def action_continue_reading(self):
        idx = progress.get_last(self.slug)
        if idx is not None and 0 <= idx < len(self.files):
            self.app.push_screen(LocalReaderScreen(self.files, self.slug, start=idx))
        else:
            self.notify("No saved progress.", timeout=2)

    def action_download_dialog(self):
        self.run_worker(self._do_download_dialog(), exclusive=True)

    async def _do_download_dialog(self):
        source = _get_source(self.slug)
        if not source:
            self.notify("No source found for this novel.", timeout=3)
            return
        try:
            chapters = await _get_chapters(
                source, self.slug.split(":", 1)[-1] if ":" in self.slug else self.slug
            )
        except Exception:
            self.notify("Failed to fetch chapters. Check network.", timeout=3)
            return
        if not chapters:
            self.notify("Could not fetch chapters.", timeout=3)
            return
        self.app.push_screen(
            DownloadDialog(
                chapters,
                self.slug,
                source,
                current_idx=None,
                has_translation=False,
            )
        )

    def action_export(self):
        source = _get_source(self.slug)
        if not source:
            self.notify("No source found.", timeout=3)
            return
        self.run_worker(self._do_export(self.slug, source), exclusive=True)

    async def _do_export(self, slug, source):
        try:
            path = await _export_epub(slug, source)
        except ImportError:
            self.notify("ebooklib not installed. Run: pip install ebooklib", timeout=5)
            return
        if path:
            self.notify(f"Exported to {path}", timeout=5)
        else:
            self.notify("No chapters to export.", timeout=3)

    def action_pop(self):
        self._pending = None
        self.app.pop_screen()
