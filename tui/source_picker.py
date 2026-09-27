from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Label, ListItem, ListView, Static

from tui.shared import CustomHeader


class SourcePickerScreen(Screen):
    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(self, items, callback):
        super().__init__()
        self._items = items
        self._callback = callback

    def compose(self):
        yield CustomHeader()
        with Vertical(classes="dialog-overlay"), Vertical(classes="dialog-box"):
            yield Static("Switch Source", classes="title")
            list_view = ListView(id="source-list")
            for item in self._items:
                list_view.append(ListItem(Label(item["label"]), id=item["id"]))
            yield list_view
        yield Footer()

    def on_mount(self):
        self.query_one("#source-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected):
        item_id = event.item.id
        self._callback(item_id)
        self.app.pop_screen()

    def action_dismiss(self):
        self._callback(None)
        self.app.pop_screen()
