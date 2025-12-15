from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from typing import Any, Optional, Union, Dict, List

PAGINATION = 4

class Superlist:
    PAGE_PREFIX = "superlist_page_"
    ITEM_PREFIX = "superlist_callback_"

    def __init__(self, objects: Optional[List[Any]] = None):
        self.objects = objects if objects is not None else []
        self.objects.sort()
        self.inline_items = {
            str(self.objects[i]): f"{self.ITEM_PREFIX}{i}" for i in range(len(self.objects))
        }

    def get_inline_keyboard(self, page: int = 1) -> InlineKeyboardMarkup:
        total = len(self.objects)
        if total == 0:
            return InlineKeyboardMarkup(inline_keyboard=[])

        last_page = max(1, (total + PAGINATION - 1) // PAGINATION)
        page = max(1, min(page, last_page))

        start = (page - 1) * PAGINATION
        end = min(start + PAGINATION, total)

        keyboard = []
        for idx in range(start, end):
            text = str(self.objects[idx])
            cb = f"{self.ITEM_PREFIX}{idx}"
            keyboard.append([InlineKeyboardButton(text=text, callback_data=cb)])

        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"{self.PAGE_PREFIX}{page-1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{page}/{last_page}", callback_data=f"{self.PAGE_PREFIX}info"))
        if page < last_page:
            nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"{self.PAGE_PREFIX}{page+1}"))

        keyboard.append(nav_buttons)
        return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def process_base_superlist_callback(callback_data: str, superlist: Superlist) -> Union[None, Any, Dict[str, int]]:
    prefix_item = Superlist.ITEM_PREFIX
    if callback_data.startswith(prefix_item):
        index_str = callback_data[len(prefix_item):]
        if index_str.isdigit():
            index = int(index_str)
            if 0 <= index < len(superlist.objects):
                return superlist.objects[index]
        return None

    prefix_page = Superlist.PAGE_PREFIX
    if callback_data.startswith(prefix_page):
        page_str = callback_data[len(prefix_page):]
        if page_str.isdigit():
            return {"page": int(page_str)}
        return None

    return None


class SuperlistSelection:
    PAGE_PREFIX = "superlist_selection_page_"
    ITEM_PREFIX = "superlist_selection_callback_"
    ALL_PREFIX = "superlist_selection_all_"
    CANCEL_PREFIX = "superlist_selection_cancel_"
    READY_PREFIX = "superlist_selection_ready_"

    def __init__(self, objects: Optional[List[Any]] = None):
        self.objects = objects if objects is not None else []
        self.objects.sort()
        self.selected = set()
        self.inline_items = {
            str(self.objects[i]): f"{self.ITEM_PREFIX}{i}" for i in range(len(self.objects))
        }

    def get_inline_keyboard(self, page: int = 1) -> InlineKeyboardMarkup:
        total = len(self.objects)
        if total == 0:
            return InlineKeyboardMarkup(inline_keyboard=[])

        last_page = max(1, (total + PAGINATION - 1) // PAGINATION)
        page = max(1, min(page, last_page))

        start = (page - 1) * PAGINATION
        end = min(start + PAGINATION, total)

        keyboard = []
        for idx in range(start, end):
            obj = self.objects[idx]
            text = str(obj)
            if obj in self.selected:
                text = "✅ " + text
            cb = f"{self.ITEM_PREFIX}{idx}"
            keyboard.append([InlineKeyboardButton(text=text, callback_data=cb)])

        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"{self.PAGE_PREFIX}{page-1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{page}/{last_page}", callback_data=f"{self.PAGE_PREFIX}info"))
        if page < last_page:
            nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"{self.PAGE_PREFIX}{page+1}"))

        keyboard.append(nav_buttons)

        all_button = InlineKeyboardButton(text="Отметить всех", callback_data=f"{self.ALL_PREFIX}{page}")
        cancel_button = InlineKeyboardButton(text="Отменить выбор", callback_data=f"{self.CANCEL_PREFIX}{page}")
        ready_button = InlineKeyboardButton(text="Готово", callback_data=f"{self.READY_PREFIX}{page}")
        keyboard.append([all_button])
        keyboard.append([cancel_button])
        keyboard.append([ready_button])

        return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def process_superlist_selection_callback(callback_data: str, superlist_selection: SuperlistSelection) -> Union[None, Any, Dict[str, Any]]:
    prefix_item = SuperlistSelection.ITEM_PREFIX
    if callback_data.startswith(prefix_item):
        index_str = callback_data[len(prefix_item):]
        if index_str.isdigit():
            index = int(index_str)
            if 0 <= index < len(superlist_selection.objects):
                obj = superlist_selection.objects[index]
                if obj in superlist_selection.selected:
                    superlist_selection.selected.remove(obj)
                else:
                    superlist_selection.selected.add(obj)
        return None

    prefix_page = SuperlistSelection.PAGE_PREFIX
    if callback_data.startswith(prefix_page):
        page_str = callback_data[len(prefix_page):]
        if page_str.isdigit():
            return {"page": int(page_str)}
        return None

    prefix_all = SuperlistSelection.ALL_PREFIX
    if callback_data.startswith(prefix_all):
        superlist_selection.selected = set(superlist_selection.objects)
        return None

    prefix_cancel = SuperlistSelection.CANCEL_PREFIX
    if callback_data.startswith(prefix_cancel):
        superlist_selection.selected.clear()
        return None

    prefix_ready = SuperlistSelection.READY_PREFIX
    if callback_data.startswith(prefix_ready):
        return {"selected": list(superlist_selection.selected)}

    return None