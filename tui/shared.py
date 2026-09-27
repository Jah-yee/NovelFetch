from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, ListItem, ListView, Static

from core.progress import LANGUAGES


class CustomHeader(Horizontal):
    def compose(self):
        yield Static(self.app.title, id="header-title")

class LanguagePicker(Screen):
    BINDINGS = [Binding("escape", "dismiss_pop", "Back")]

    def compose(self):
        yield CustomHeader()
        yield Static("Target Language", classes="title")
        with ScrollableContainer():
            yield ListView(*[ListItem(Label(name)) for name in LANGUAGES])
        yield Footer()

    def dismiss(self, result=None):
        user_callback = None
        if self._result_callbacks:
            rc = self._result_callbacks[-1]
            user_callback = rc.callback
        self.app.pop_screen()
        if user_callback:
            user_callback(result)

    def on_list_view_selected(self, event: ListView.Selected):
        idx = event.list_view.index
        if idx is None:
            return
        code = list(LANGUAGES.values())[idx]
        self.dismiss(code)

    def on_mount(self):
        try:
            self.query_one(ListView).focus()
        except Exception:
            pass

    def action_dismiss_pop(self):
        self.dismiss(None)


class JumpDialog(Screen):
    BINDINGS = [Binding("escape", "dismiss_pop", "Back")]

    def __init__(self, chapters , callback):
        super().__init__()
        self.chapters = chapters
        self.callback = callback

    def compose(self):
        yield Static(f"Chapters: 1-{len(self.chapters)}")
        yield Input(placeholder="Enter a number  ", type="integer")

    async def on_input_submitted(self, event):
        try:
            num = int(event.value)
            if 1 <= num <=len(self.chapters):
                await self.callback(num-1)
                self.app.pop_screen()
        except ValueError:
            pass

    def action_dismiss_pop(self):
        self.app.pop_screen()

