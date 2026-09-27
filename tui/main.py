"""Textual TUI application (terminal frontend)."""

import os

from textual.app import App

from tui import MainMenu


class NovelFetchApp(App):
    TITLE = "NovelFetch"
    CSS_PATH = "novelfetch.tcss"

    def __init__(self):
        super().__init__()
        self.current_source = None
        self.version = "1.0.0"

    def on_mount(self):
        self.push_screen(MainMenu())


def main():
    from core.paths import ensure_data_dir

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Only use repo root as dev data dir when running from a source checkout.
    # pip/AUR installs place __file__ in site-packages (root-owned), so passing
    # it as dev_root would either crash on mkdir or write into a system dir.
    if os.path.isdir(os.path.join(repo_root, ".git")):
        ensure_data_dir(dev_root=repo_root)
    else:
        ensure_data_dir()
    NovelFetchApp().run()


if __name__ == "__main__":
    main()
