"""Performance benchmarks for the Textual TUI frontend.

Runs the TUI headlessly via Textual's ``app.run_test()`` and measures
wall-clock times for startup, screen mounts, navigation, list rendering,
search debounce, download progress, and memory usage.

All network calls are mocked — these benchmarks isolate **UI rendering cost**.

Run with::

    pytest tests/test_tui_performance.py -v -s
"""

import os
import statistics
import sys
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_novel(idx: int) -> dict:
    return {
        "title": f"Test Novel {idx}",
        "author": f"Author {idx}",
        "slug": f"rr:test-novel-{idx}",
        "latest": f"Chapter {idx * 10}",
    }


def _make_fake_chapter(idx: int) -> dict:
    return {
        "num": idx + 1,
        "title": f"Chapter {idx + 1}",
        "url": f"https://example.com/ch/{idx}",
    }


def _make_mock_source(novels=None, chapters=None):
    """Create a mock Source that satisfies the ABC without network calls."""
    src = MagicMock()
    src.name = "test"
    src.label = "Test Source"
    src.ascii_art = "  TEST  "
    src.browse_urls = {"hot": "", "latest": "", "popular": "", "completed": ""}
    src.genres = {f"genre-{i}": f"Genre {i}" for i in range(5)}
    src.search_supported = True

    _novels = novels or [_make_fake_novel(i) for i in range(20)]
    _chapters = chapters or [_make_fake_chapter(i) for i in range(50)]

    async def fake_search(query, page=1):
        return _novels, 1

    async def fake_fetch_chapters(slug):
        return _chapters

    async def fake_read_chapter(url):
        return [f"Content of chapter at {url}"]

    async def fake_fetch_url(url, params=None):
        return None

    async def fake_cover_url(slug):
        return ""

    async def fake_browse_genre(genre_slug):
        return _novels

    src.search = AsyncMock(side_effect=fake_search)
    src.fetch_chapters = AsyncMock(side_effect=fake_fetch_chapters)
    src.read_chapter = AsyncMock(side_effect=fake_read_chapter)
    src.fetch_url = AsyncMock(side_effect=fake_fetch_url)
    src.cover_url = AsyncMock(side_effect=fake_cover_url)
    src.browse_genre = AsyncMock(side_effect=fake_browse_genre)
    src.extract_novel_rows = MagicMock(side_effect=lambda soup: _novels)
    src.qualify_slug = MagicMock(side_effect=lambda s: f"rr:{s}")
    return src


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_source():
    return _make_mock_source()


@pytest.fixture
def patch_registry(fake_source, monkeypatch):
    """Replace the global REGISTRY so the TUI uses our fake source."""
    import sources

    monkeypatch.setattr(sources, "REGISTRY", {"test": fake_source})


@pytest.fixture
def progress_tracker(tmp_path, monkeypatch):
    """Isolate the progress tracker to a temp directory."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "novels").mkdir()
    from core.progress import ProgressTracker

    tracker = ProgressTracker(str(tmp_path / "novels" / "progress.json"))
    import core.progress as prog_mod

    monkeypatch.setattr(prog_mod, "progress", tracker)
    return tracker


# ---------------------------------------------------------------------------
# 1. Cold startup
# ---------------------------------------------------------------------------


class TestStartupPerformance:
    @pytest.mark.asyncio
    async def test_cold_startup_time(self, patch_registry, progress_tracker):
        """Measure time from app creation to MainMenu mount."""
        from tui.main import NovelFetchApp

        times = []
        for _ in range(5):
            app = NovelFetchApp()
            async with app.run_test(size=(80, 24)) as pilot:
                t0 = time.perf_counter()
                await pilot.pause()
                t1 = time.perf_counter()
                times.append(t1 - t0)
                app.exit()

        stats = {
            "min": min(times),
            "max": max(times),
            "mean": statistics.mean(times),
        }
        print(
            f"\n  Startup: min={stats['min']:.4f}s  mean={stats['mean']:.4f}s  max={stats['max']:.4f}s"
        )
        assert stats["mean"] < 5.0, f"Startup too slow: {stats['mean']:.2f}s mean"


# ---------------------------------------------------------------------------
# 2. Screen mount latency
# ---------------------------------------------------------------------------


class TestScreenMountPerformance:
    @pytest.mark.asyncio
    async def test_main_menu_mount(self, patch_registry, progress_tracker):
        from tui.main import NovelFetchApp

        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            times = []
            for _ in range(5):
                from tui.main_menu import MainMenu

                t0 = time.perf_counter()
                app.push_screen(MainMenu())
                await pilot.pause()
                t1 = time.perf_counter()
                times.append(t1 - t0)
                app.pop_screen()
                await pilot.pause()
            app.exit()

        mean_ms = statistics.mean(times) * 1000
        print(f"\n  MainMenu mount: mean={mean_ms:.1f}ms")
        assert mean_ms < 500, f"MainMenu mount too slow: {mean_ms:.0f}ms"

    @pytest.mark.asyncio
    async def test_search_screen_mount(
        self, patch_registry, progress_tracker, fake_source
    ):
        from tui.browse import SearchScreen
        from tui.main import NovelFetchApp

        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            times = []
            for _ in range(5):
                t0 = time.perf_counter()
                app.push_screen(SearchScreen(source=fake_source))
                await pilot.pause()
                t1 = time.perf_counter()
                times.append(t1 - t0)
                app.pop_screen()
                await pilot.pause()
            app.exit()

        mean_ms = statistics.mean(times) * 1000
        print(f"\n  SearchScreen mount: mean={mean_ms:.1f}ms")
        assert mean_ms < 500, f"SearchScreen mount too slow: {mean_ms:.0f}ms"

    @pytest.mark.asyncio
    async def test_novel_list_screen_mount(
        self, patch_registry, progress_tracker, fake_source
    ):
        from tui.browse import NovelListScreen
        from tui.main import NovelFetchApp

        novels = [_make_fake_novel(i) for i in range(50)]
        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            times = []
            for _ in range(5):
                t0 = time.perf_counter()
                app.push_screen(NovelListScreen(novels, source=fake_source))
                await pilot.pause()
                t1 = time.perf_counter()
                times.append(t1 - t0)
                app.pop_screen()
                await pilot.pause()
            app.exit()

        mean_ms = statistics.mean(times) * 1000
        print(f"\n  NovelListScreen (50 items) mount: mean={mean_ms:.1f}ms")
        assert mean_ms < 1000, f"NovelListScreen mount too slow: {mean_ms:.0f}ms"

    @pytest.mark.asyncio
    async def test_chapter_list_screen_mount(
        self, patch_registry, progress_tracker, fake_source
    ):
        from tui.browse import ChapterListScreen
        from tui.main import NovelFetchApp

        chapters = [_make_fake_chapter(i) for i in range(50)]
        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            times = []
            for _ in range(5):
                t0 = time.perf_counter()
                app.push_screen(
                    ChapterListScreen(chapters, "rr:test", source=fake_source)
                )
                await pilot.pause()
                t1 = time.perf_counter()
                times.append(t1 - t0)
                app.pop_screen()
                await pilot.pause()
            app.exit()

        mean_ms = statistics.mean(times) * 1000
        print(f"\n  ChapterListScreen (50 items) mount: mean={mean_ms:.1f}ms")
        assert mean_ms < 1000, f"ChapterListScreen mount too slow: {mean_ms:.0f}ms"

    @pytest.mark.asyncio
    async def test_genre_screen_mount(
        self, patch_registry, progress_tracker, fake_source
    ):
        from tui.browse import GenreScreen
        from tui.main import NovelFetchApp

        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            times = []
            for _ in range(5):
                t0 = time.perf_counter()
                app.push_screen(GenreScreen(source=fake_source))
                await pilot.pause()
                t1 = time.perf_counter()
                times.append(t1 - t0)
                app.pop_screen()
                await pilot.pause()
            app.exit()

        mean_ms = statistics.mean(times) * 1000
        print(f"\n  GenreScreen mount: mean={mean_ms:.1f}ms")
        assert mean_ms < 500, f"GenreScreen mount too slow: {mean_ms:.0f}ms"

    @pytest.mark.asyncio
    async def test_download_dialog_mount(
        self, patch_registry, progress_tracker, fake_source
    ):
        from tui.download import DownloadDialog
        from tui.main import NovelFetchApp

        chapters = [_make_fake_chapter(i) for i in range(50)]
        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            times = []
            for _ in range(5):
                t0 = time.perf_counter()
                app.push_screen(DownloadDialog(chapters, "rr:test", fake_source))
                await pilot.pause()
                t1 = time.perf_counter()
                times.append(t1 - t0)
                app.pop_screen()
                await pilot.pause()
            app.exit()

        mean_ms = statistics.mean(times) * 1000
        print(f"\n  DownloadDialog mount: mean={mean_ms:.1f}ms")
        assert mean_ms < 500, f"DownloadDialog mount too slow: {mean_ms:.0f}ms"


# ---------------------------------------------------------------------------
# 3. Screen navigation latency
# ---------------------------------------------------------------------------


class TestNavigationPerformance:
    @pytest.mark.asyncio
    async def test_push_pop_cycle(self, patch_registry, progress_tracker, fake_source):
        from tui.browse import SearchScreen
        from tui.main import NovelFetchApp

        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            times = []
            for _ in range(10):
                t0 = time.perf_counter()
                app.push_screen(SearchScreen(source=fake_source))
                await pilot.pause()
                app.pop_screen()
                await pilot.pause()
                t1 = time.perf_counter()
                times.append(t1 - t0)
            app.exit()

        mean_ms = statistics.mean(times) * 1000
        print(f"\n  Push/pop cycle: mean={mean_ms:.1f}ms")
        assert mean_ms < 600, f"Navigation too slow: {mean_ms:.0f}ms"

    @pytest.mark.asyncio
    async def test_multi_screen_push_pop(
        self, patch_registry, progress_tracker, fake_source
    ):
        from tui.browse import GenreScreen, NovelListScreen, SearchScreen
        from tui.main import NovelFetchApp

        novels = [_make_fake_novel(i) for i in range(20)]
        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screens = [
                SearchScreen(source=fake_source),
                GenreScreen(source=fake_source),
                NovelListScreen(novels, source=fake_source),
            ]
            t0 = time.perf_counter()
            for s in screens:
                app.push_screen(s)
                await pilot.pause()
            for _ in screens:
                app.pop_screen()
                await pilot.pause()
            t1 = time.perf_counter()
            app.exit()

        elapsed_ms = (t1 - t0) * 1000
        per_screen = elapsed_ms / len(screens)
        print(
            f"\n  3-screen push/pop: total={elapsed_ms:.1f}ms  per-screen={per_screen:.1f}ms"
        )
        assert per_screen < 800, f"Multi-screen nav too slow: {per_screen:.0f}ms/screen"


# ---------------------------------------------------------------------------
# 4. Large list rendering
# ---------------------------------------------------------------------------


class TestLargeListRendering:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("count", [10, 100, 500])
    async def test_novel_list_scaling(
        self, patch_registry, progress_tracker, fake_source, count
    ):
        from tui.browse import NovelListScreen
        from tui.main import NovelFetchApp

        novels = [_make_fake_novel(i) for i in range(count)]
        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            t0 = time.perf_counter()
            app.push_screen(NovelListScreen(novels, source=fake_source))
            await pilot.pause()
            t1 = time.perf_counter()
            app.exit()

        elapsed_ms = (t1 - t0) * 1000
        print(f"\n  NovelList {count} items: {elapsed_ms:.1f}ms")
        threshold = {10: 1000, 100: 1000, 500: 2000}.get(count, 2000)
        assert elapsed_ms < threshold, (
            f"Rendering {count} items too slow: {elapsed_ms:.0f}ms"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("count", [10, 100, 500])
    async def test_chapter_list_scaling(
        self, patch_registry, progress_tracker, fake_source, count
    ):
        from tui.browse import ChapterListScreen
        from tui.main import NovelFetchApp

        chapters = [_make_fake_chapter(i) for i in range(count)]
        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            t0 = time.perf_counter()
            app.push_screen(ChapterListScreen(chapters, "rr:test", source=fake_source))
            await pilot.pause()
            t1 = time.perf_counter()
            app.exit()

        elapsed_ms = (t1 - t0) * 1000
        print(f"\n  ChapterList {count} items: {elapsed_ms:.1f}ms")
        threshold = {10: 1000, 100: 1000, 500: 2000}.get(count, 2000)
        assert elapsed_ms < threshold, (
            f"Rendering {count} chapters too slow: {elapsed_ms:.0f}ms"
        )


# ---------------------------------------------------------------------------
# 5. Search debounce isolation
# ---------------------------------------------------------------------------


class TestSearchDebounce:
    @pytest.mark.asyncio
    async def test_debounce_does_not_fire_per_keystroke(
        self, patch_registry, progress_tracker, fake_source
    ):
        """Rapid input changes should not trigger a search per keystroke."""
        from tui.browse import SearchScreen
        from tui.main import NovelFetchApp

        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = SearchScreen(source=fake_source)
            app.push_screen(screen)
            await pilot.pause()

            search_call_count_before = fake_source.search.call_count

            # Simulate rapid typing: each character within the debounce window
            inp = screen.query_one("Input")
            for ch in "hello":
                inp.value += ch
                await pilot.pause()

            # The debounce timer is 0.75s — within the rapid typing window
            # search should NOT have been called yet for each keystroke
            calls_after = fake_source.search.call_count - search_call_count_before
            print(f"\n  Search calls after rapid typing 'hello': {calls_after}")
            assert calls_after <= 1, (
                f"Search called {calls_after} times during rapid typing — "
                f"debounce not working (expected <= 1)"
            )
            app.exit()


# ---------------------------------------------------------------------------
# 6. Download progress updates
# ---------------------------------------------------------------------------


class TestDownloadProgressPerformance:
    @pytest.mark.asyncio
    async def test_progress_bar_update_rate(self, patch_registry, progress_tracker):
        """ProgressBar should handle rapid updates without excessive overhead."""
        from textual.app import App
        from textual.widgets import ProgressBar, Static

        class ProgressApp(App):
            def compose(self):
                yield Static("Progress Benchmark")
                yield ProgressBar(total=100, id="bar")

        app = ProgressApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            bar = app.query_one("#bar", ProgressBar)
            times = []
            for i in range(1, 101):
                t0 = time.perf_counter()
                bar.progress = i
                await pilot.pause()
                t1 = time.perf_counter()
                times.append(t1 - t0)

        mean_ms = statistics.mean(times) * 1000
        p99 = sorted(times)[98] * 1000
        print(f"\n  ProgressBar update: mean={mean_ms:.2f}ms  p99={p99:.2f}ms")
        assert p99 < 100, f"ProgressBar p99 too slow: {p99:.0f}ms"


# ---------------------------------------------------------------------------
# 7. Memory footprint
# ---------------------------------------------------------------------------


class TestMemoryUsage:
    def _get_rss_mb(self):
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF)
        # On Linux, ru_maxrss is in KB
        return ru.ru_maxrss / 1024

    @pytest.mark.asyncio
    async def test_memory_after_startup(self, patch_registry, progress_tracker):
        from tui.main import NovelFetchApp

        rss_before = self._get_rss_mb()
        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            rss_after = self._get_rss_mb()
            app.exit()

        delta = rss_after - rss_before
        print(f"\n  RSS at startup: {rss_after:.1f}MB (delta: +{delta:.1f}MB)")
        assert rss_after < 130, f"RSS too high at startup: {rss_after:.0f}MB"

    @pytest.mark.asyncio
    async def test_memory_after_screen_cycle(
        self, patch_registry, progress_tracker, fake_source
    ):
        from tui.browse import (
            ChapterListScreen,
            GenreScreen,
            NovelListScreen,
            SearchScreen,
        )
        from tui.download import DownloadDialog
        from tui.main import NovelFetchApp

        novels = [_make_fake_novel(i) for i in range(50)]
        chapters = [_make_fake_chapter(i) for i in range(50)]

        app = NovelFetchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screens = [
                SearchScreen(source=fake_source),
                GenreScreen(source=fake_source),
                NovelListScreen(novels, source=fake_source),
                ChapterListScreen(chapters, "rr:test", source=fake_source),
                DownloadDialog(chapters, "rr:test", fake_source),
            ]
            for s in screens:
                app.push_screen(s)
                await pilot.pause()
            for _ in screens:
                app.pop_screen()
                await pilot.pause()

            rss = self._get_rss_mb()
            app.exit()

        print(f"\n  RSS after 5-screen cycle: {rss:.1f}MB")
        assert rss < 150, f"RSS too high after navigation: {rss:.0f}MB"
