from typing import Optional, Callable, List, Dict, Any
import logging
from datetime import datetime, date as date_type, time as time_type

from utils.payment_decorators import requires_payment_info

from aiogram import Router, Bot, F
from aiogram.filters import StateFilter
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    Location,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from aiogram_calendar import (
    SimpleCalendar,
    SimpleCalendarCallback,
    DialogCalendar,
    DialogCalendarCallback,
    get_user_locale,
)

from sqlalchemy import select, insert, update as sa_update

from models.user import User
from managers.user import UserManager
from database import async_session_maker
from models.workout import Workout as WorkoutModel, workout_participants as wp_table
from states import AdminStates
from config import settings

from utils.superlist import Superlist, SuperlistSelection
from utils.ui_constants import UI

logger = logging.getLogger(__name__)


class AdminWorkoutStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_location = State()
    waiting_for_price = State()
    waiting_for_comment = State()
    waiting_for_public = State()
    waiting_for_invited_selection = State()
    waiting_for_confirmation = State()
    waiting_for_send_option = State()

superlist_selections_admin: Dict[int, Dict[str, Any]] = {}
workout_superlist_selections: Dict[int, Dict[str, Any]] = {}


class AdminPanel:
    CREATE = "admin:create_workout"
    LIST_USERS = "admin:list_users"
    LIST_USERS_PAGE = "admin:list_users:page:"
    REPORT = "admin:report"
    REVIEW_USER_PREFIX = "admin:review_user:"
    BACK_TO_PANEL = "admin:back_to_panel"
    
    def __init__(self, user_manager: Optional[UserManager] = None,
        start_create_cb: Optional[Callable[[CallbackQuery, FSMContext], object]] = None,
        page_size: int = 10, bot: Optional[Bot] = None):

        self.user_manager = user_manager
        self.start_create_cb = start_create_cb or self._start_create_workout
        self.page_size = page_size
        self.bot = bot

    def markup(self) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=UI.CREATE_WORKOUT, callback_data=self.CREATE)],
                [InlineKeyboardButton(text=UI.LIST_USERS, callback_data=self.LIST_USERS)],
                [InlineKeyboardButton(text="📋 Тренировки", callback_data="admin:list_workouts")],
                [InlineKeyboardButton(text=UI.REPORT, callback_data=self.REPORT)],
            
        ])
        return kb

    def users_list_markup(self, users: List[User], page: int = 1) -> InlineKeyboardMarkup:
        labels: List[str] = []
        label_to_id: Dict[str, str] = {}
        for u in users:
            label = " ".join(
                p for p in (
                    getattr(u, "full_name", "") or "",
                ) if p
            ) or f"tg:{getattr(u, 'tg_id', 'unknown')}"
            labels.append(label)
            user_id = str(getattr(u, "id", getattr(u, "tg_id", "")))
            label_to_id[label] = user_id

        superlist = Superlist(objects=labels)
        kb = superlist.get_inline_keyboard(page=page)

        for row in kb.inline_keyboard:
            for btn in row:
                cd = getattr(btn, "callback_data", "") or ""
                if cd.startswith(Superlist.ITEM_PREFIX):
                    user_id = label_to_id.get(btn.text, "0")
                    btn.callback_data = f"{self.REVIEW_USER_PREFIX}{user_id}"
                elif cd.startswith(Superlist.PAGE_PREFIX):
                    page_token = cd[len(Superlist.PAGE_PREFIX):]
                    if page_token.isdigit():
                        btn.callback_data = f"{self.LIST_USERS_PAGE}{page_token}"
                    else:
                        btn.callback_data = f"{self.LIST_USERS_PAGE}info"

        kb.inline_keyboard.append([InlineKeyboardButton(text=UI.BACK_TO_PANEL, callback_data=self.BACK_TO_PANEL)])
        return kb

    def register(self, router: Router):
        router.callback_query.register(self._on_create, lambda cq: cq.data == self.CREATE)
        router.callback_query.register(self._on_list_users, lambda cq: cq.data == self.LIST_USERS)
        router.callback_query.register(self._on_report, lambda cq: cq.data == self.REPORT)
        router.callback_query.register(self._on_review_user, lambda cq: cq.data and cq.data.startswith(self.REVIEW_USER_PREFIX))
        router.callback_query.register(self._on_edit_user, lambda cq: cq.data and cq.data.startswith("admin:edit_user:"))
        router.callback_query.register(self._on_edit_field, lambda cq: cq.data and cq.data.startswith("admin:edit_field:"))
        router.callback_query.register(self._on_delete_user, lambda cq: cq.data and cq.data.startswith("admin:delete_user:"))
        router.callback_query.register(self._on_confirm_delete_user, lambda cq: cq.data and cq.data.startswith("admin:confirm_delete_user:"))
        router.callback_query.register(self._on_back_to_panel, lambda cq: cq.data == self.BACK_TO_PANEL)
        router.callback_query.register(self._on_list_users_page, lambda cq: cq.data and cq.data.startswith(self.LIST_USERS_PAGE))
        
        router.callback_query.register(self._on_list_workouts, lambda cq: cq.data == "admin:list_workouts")
        router.callback_query.register(self._on_list_workouts_page, lambda cq: cq.data and cq.data.startswith(Superlist.PAGE_PREFIX))
        router.callback_query.register(self._on_workout_selected, lambda cq: cq.data and cq.data.startswith("admin:review_workout:"))
        router.callback_query.register(self._on_resend_workout, lambda cq: cq.data and cq.data.startswith("admin:resend_workout:"))
        router.callback_query.register(self._on_send_workout_option, lambda cq: cq.data in ["workout:send_now", "workout:send_later"])
        
        router.callback_query.register(self._on_workout_join, lambda cq: cq.data and cq.data.startswith("workout:join:"))
        router.callback_query.register(self._on_workout_location, lambda cq: cq.data and cq.data.startswith("workout:location:"))
        router.callback_query.register(self._on_pay_tg, lambda cq: cq.data and cq.data.startswith("pay_tg:"))
        router.callback_query.register(self._on_pay_link, lambda cq: cq.data and cq.data.startswith("pay_link:"))
        
        router.pre_checkout_query.register(self._on_pre_checkout_query)
        router.message.register(self._on_successful_payment, F.successful_payment)

        router.message.register(self._wc_name, StateFilter(AdminWorkoutStates.waiting_for_name))
        router.message.register(self._wc_date, StateFilter(AdminWorkoutStates.waiting_for_date))
        router.message.register(self._wc_time, StateFilter(AdminWorkoutStates.waiting_for_time))
        router.message.register(self._wc_location_received, StateFilter(AdminWorkoutStates.waiting_for_location), F.location)
        router.message.register(self._wc_location_skip, StateFilter(AdminWorkoutStates.waiting_for_location))
        router.message.register(self._wc_price, StateFilter(AdminWorkoutStates.waiting_for_price))
        router.message.register(self._wc_comment, StateFilter(AdminWorkoutStates.waiting_for_comment))

        router.callback_query.register(self._wc_cancel, lambda c: c.data == "create_workout_cancel")
        router.callback_query.register(self._wc_confirm, lambda c: c.data == "create_workout_confirm")
        router.callback_query.register(self._wc_public_selected, lambda c: c.data in ["workout_public_true", "workout_public_false"])
        router.callback_query.register(
            self._wc_invited_selection, 
            self._check_invited_selection_callback,
            StateFilter(AdminWorkoutStates.waiting_for_invited_selection)
        )

        router.callback_query.register(self._process_simple_calendar, SimpleCalendarCallback.filter())
        router.callback_query.register(self._process_dialog_calendar, DialogCalendarCallback.filter())

        logger.info("AdminPanel handlers registered")

    @staticmethod
    def _check_invited_selection_callback(c: CallbackQuery) -> bool:
        return bool(
            c.data and (
                c.data.startswith(SuperlistSelection.ITEM_PREFIX) or 
                c.data.startswith(SuperlistSelection.PAGE_PREFIX) or 
                c.data.startswith(SuperlistSelection.ALL_PREFIX) or 
                c.data.startswith(SuperlistSelection.CANCEL_PREFIX) or 
                c.data.startswith(SuperlistSelection.READY_PREFIX)
            )
        )

    async def _on_create(self, callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        await self.start_create_cb(callback, state)

    async def _on_list_users(self, callback: CallbackQuery) -> None:
        await callback.answer()
        if not self.user_manager or not hasattr(self.user_manager, "get_all_users"):
            await callback.message.answer("User manager не настроен. Невозможно получить список пользователей.")
            return
        try:
            users = await self.user_manager.get_all_users()
            if not users:
                await callback.message.answer("Список пользователей пуст.")
                return
            kb = self.users_list_markup(users, page=1)
            await callback.message.edit_text(f"{UI.PEOPLE} Список пользователей (выберите для деталей):", reply_markup=kb)
        except Exception:
            logger.exception("Ошибка получения списка пользователей")
            await callback.message.answer("Ошибка при получении списка пользователей.")

    async def _on_list_users_page(self, callback: CallbackQuery):
        await callback.answer()
        data = (callback.data or "").removeprefix(self.LIST_USERS_PAGE)
        try:
            page = int(data)
        except Exception:
            page = 1
        try:
            users = await self.user_manager.get_all_users()
            kb = self.users_list_markup(users, page=page)
            await callback.message.edit_text(f"{UI.PEOPLE} Список пользователей — страница {page}:", reply_markup=kb)
        except Exception:
            logger.exception("Ошибка при навигации по списку пользователей")
            await callback.message.answer("Ошибка при навигации по списку пользователей.")

    async def _on_review_user(self, callback: CallbackQuery):
        await callback.answer()
        data = callback.data or ""
        try:
            uid = data.split(self.REVIEW_USER_PREFIX)[-1]
            user = None
            if self.user_manager and hasattr(self.user_manager, "get_by_id"):
                try:
                    user = await self.user_manager.get_by_id(int(uid))
                except Exception:
                    user = None
            if not user and self.user_manager and hasattr(self.user_manager, "get_all_users"):
                users = await self.user_manager.get_all_users()
                user = next((u for u in users if str(getattr(u, "id", getattr(u, "tg_id", None))) == str(uid)), None)
            if not user:
                await callback.message.answer("Пользователь не найден.")
                return
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=UI.BACK_TO_LIST, callback_data=self.LIST_USERS)],
                [InlineKeyboardButton(text=UI.EDIT, callback_data=f"admin:edit_user:{getattr(user,'id',getattr(user,'tg_id','0'))}")],
                [InlineKeyboardButton(text=UI.DELETE, callback_data=f"admin:delete_user:{getattr(user,'id',getattr(user,'tg_id','0'))}")],
            ])
            await callback.message.edit_text(user.get_text_display_tg(), reply_markup=kb, parse_mode="HTML")
        except Exception:
            logger.exception("Ошибка показа деталей пользователя")
            await callback.message.answer("Ошибка при показе деталей пользователя.")

    async def _on_edit_user(self, callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        data = callback.data or ""
        try:
            uid = data.split("admin:edit_user:")[-1]
            user = None
            if self.user_manager and hasattr(self.user_manager, "get_by_id"):
                try:
                    user = await self.user_manager.get_by_id(int(uid))
                except Exception:
                    user = None
            if not user and self.user_manager and hasattr(self.user_manager, "get_all_users"):
                users = await self.user_manager.get_all_users()
                user = next((u for u in users if str(getattr(u, "id", getattr(u, "tg_id", None))) == str(uid)), None)
            
            if not user:
                await callback.message.answer("Пользователь не найден.")
                return
            
            await state.update_data(editing_user_id=int(uid))
            
            editable_fields = user.editable_fields_display
            
            buttons = []
            for field_name, field_label in editable_fields.items():
                buttons.append([
                    InlineKeyboardButton(
                        text=f"✏️ {field_label}",
                        callback_data=f"admin:edit_field:{field_name}:{int(uid)}"
                    )
                ])
            
            buttons.append([
                InlineKeyboardButton(text=UI.BACK_TO_LIST, callback_data=self.LIST_USERS)
            ])
            
            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            text = (
                f"{UI.PERSON} Выберите поле для редактирования:\n"
                f"{user.full_name}"
            )
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            logger.exception("Ошибка при выборе поля для редактирования")
            await callback.message.answer("Ошибка при выборе поля для редактирования.")

    async def _on_edit_field(self, callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        data = callback.data or ""
        try:
            parts = data.split(":")
            field_name = parts[2] if len(parts) > 2 else None
            uid = int(parts[3]) if len(parts) > 3 else None
            
            if not field_name or not uid:
                await callback.message.answer("Ошибка: некорректные данные.")
                return
            
            await state.update_data(editing_user_id=uid, editing_field=field_name)
            
            field_to_state = {
                "first_name": AdminStates.waiting_for_edit_first_name,
                "last_name": AdminStates.waiting_for_edit_last_name,
                "middle_name": AdminStates.waiting_for_edit_middle_name,
                "birth_date": AdminStates.waiting_for_edit_birth_date,
                "weight": AdminStates.waiting_for_edit_weight,
                "phone": AdminStates.waiting_for_edit_phone,
                "email": AdminStates.waiting_for_edit_email,
            }

            field_to_label = {
                "first_name": "Имя",
                "last_name": "Фамилия",
                "middle_name": "Отчество",
                "birth_date": "Дата рождения (ДД.МММ.ГГГГ)",
                "weight": "Вес (в кг)",
                "phone": "Телефон (79991234567)",
                "email": "Email",
            }

            if field_name not in field_to_state:
                await callback.message.answer(f"Поле '{field_name}' не поддерживается для редактирования.")
                return
            
            await state.set_state(field_to_state[field_name])
            label = field_to_label.get(field_name, field_name)
            
            await callback.message.answer(f"Введите новое значение для '{label}':")
        except Exception:
            logger.exception("Ошибка при редактировании поля")
            await callback.message.answer("Ошибка при редактировании поля.")

    async def _on_back_to_panel(self, callback: CallbackQuery):
        await callback.answer()
        await callback.message.edit_text("Админская панель", reply_markup=self.markup())

    async def _on_delete_user(self, callback: CallbackQuery):
        await callback.answer()
        uid = (callback.data or "").split("admin:delete_user:")[-1]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"admin:confirm_delete_user:{uid}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"{self.REVIEW_USER_PREFIX}{uid}"),
            ]
        ])
        await callback.message.edit_text(
            "⚠️ <b>Удаление пользователя</b>\n\nВы уверены? Это действие нельзя отменить.",
            reply_markup=kb,
        )

    async def _on_confirm_delete_user(self, callback: CallbackQuery):
        await callback.answer()
        uid = (callback.data or "").split("admin:confirm_delete_user:")[-1]
        try:
            from sqlalchemy import delete as sa_delete
            from models.user import User as UserModel
            async with async_session_maker() as session:
                await session.execute(sa_delete(UserModel).where(UserModel.id == int(uid)))
                await session.commit()
            await callback.message.edit_text(f"✅ Пользователь удалён.", reply_markup=None)
        except Exception:
            logger.exception("Ошибка при удалении пользователя")
            await callback.message.answer("❌ Ошибка при удалении пользователя.")

    async def _on_report(self, callback: CallbackQuery):
        await callback.answer()
        await callback.message.answer(UI.REPORT)

    async def _start_create_workout(self, callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        await state.clear()
        await state.set_state(AdminWorkoutStates.waiting_for_name)
        await callback.message.answer(f"{UI.PLUS} <b>Создание тренировки</b>\n\nВведите название тренировки:")

    async def _wc_name(self, message: Message, state: FSMContext):
        name = (message.text or "").strip()
        if not name:
            await message.answer(f"{UI.CROSS_MARK} Название не должно быть пустым. Введите название:")
            return
        await state.update_data(name=name)
        user_locale = await get_user_locale(message.from_user)
        try:
            calendar = SimpleCalendar(locale=user_locale, show_alerts=True)
        except Exception as e:
            logger.warning(f"Calendar locale '{user_locale}' unsupported: {e}; falling back to 'en'.")
            try:
                calendar = SimpleCalendar(locale="en", show_alerts=True)
            except Exception:
                calendar = SimpleCalendar(show_alerts=True)

        await message.answer(
            "Выберите дату тренировки:",
            reply_markup=await calendar.start_calendar()
        )
        await state.set_state(AdminWorkoutStates.waiting_for_date)

    async def _wc_date(self, message: Message, state: FSMContext):
        text = (message.text or "").strip()
        dt = None
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(text, fmt).date()
                break
            except Exception:
                continue
        if dt is None:
            await message.answer(f"{UI.CROSS_MARK} Неверный формат даты. Используйте календарь или формат ДД.MM.ГГГГ")
            return

        if dt < date_type.today():
            await message.answer(f"{UI.CROSS_MARK} Дата не может быть в прошлом. Выберите сегодня или позже.")
            return

        await state.update_data(date=dt)
        await message.answer("Введите время тренировки (ЧЧ:ММ), например 19:30:")
        await state.set_state(AdminWorkoutStates.waiting_for_time)

    async def _wc_time(self, message: Message, state: FSMContext):
        text = (message.text or "").strip()
        try:
            t = datetime.strptime(text, "%H:%M").time()
        except Exception:
            await message.answer(f"{UI.CROSS_MARK} Неверный формат времени. Используйте ЧЧ:ММ (например 19:30).")
            return
        await state.update_data(time=t)
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=UI.SELECT_LOCATION, request_location=True)],
                [KeyboardButton(text=UI.SKIP_STEP)]
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.answer(f"Отправьте геолокацию (необязательно) или нажмите '{UI.SKIP_STEP}':", reply_markup=kb)
        await state.set_state(AdminWorkoutStates.waiting_for_location)

    async def _wc_location_received(self, message: Message, state: FSMContext):
        loc: Location = message.location
        await state.update_data(latitude=loc.latitude, longitude=loc.longitude)
        await message.answer("Геолокация принята.", reply_markup=ReplyKeyboardRemove())
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=UI.SKIP_STEP)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.answer(f"Укажите цену (необязательно) или нажмите '{UI.SKIP_STEP}':", reply_markup=kb)
        await state.set_state(AdminWorkoutStates.waiting_for_price)

    async def _wc_location_skip(self, message: Message, state: FSMContext):
        if (message.text or "").strip() == UI.SKIP_STEP:
            await state.update_data(latitude=None, longitude=None)
            await message.answer("Геолокация пропущена.", reply_markup=ReplyKeyboardRemove())
            kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=UI.SKIP_STEP)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            )
            await message.answer(f"Укажите цену (необязательно) или нажмите '{UI.SKIP_STEP}':", reply_markup=kb)
            await state.set_state(AdminWorkoutStates.waiting_for_price)
            return
        await message.answer(f"Пожалуйста, используйте кнопку '{UI.SELECT_LOCATION}' или нажмите '{UI.SKIP_STEP}'.")

    async def _wc_price(self, message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if text == UI.SKIP_STEP or text == "":
            await state.update_data(price=None)
        else:
            try:
                price = float(text.replace(",", "."))
                await state.update_data(price=price)
            except Exception:
                await message.answer(f"{UI.CROSS_MARK} Неверный формат цены. Введите число или нажмите '{UI.SKIP_STEP}'.")
                return
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=UI.SKIP_STEP)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.answer(f"Добавьте комментарий к тренировке (необязательно) или нажмите '{UI.SKIP_STEP}':", reply_markup=kb)
        await state.set_state(AdminWorkoutStates.waiting_for_comment)

    async def _wc_comment(self, message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if text == UI.SKIP_STEP or text == "":
            await state.update_data(comment=None)
            await message.answer("Комментарий пропущен.", reply_markup=ReplyKeyboardRemove())
        else:
            await state.update_data(comment=text)
            await message.answer("Комментарий сохранён.", reply_markup=ReplyKeyboardRemove())

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=UI.PUBLIC_WORKOUT, callback_data="workout_public_true")],
            [InlineKeyboardButton(text=UI.PRIVATE_WORKOUT, callback_data="workout_public_false")]
        ])
        await message.answer("Выберите тип тренировки:", reply_markup=kb)
        await state.set_state(AdminWorkoutStates.waiting_for_public)

    async def _wc_cancel(self, callback: CallbackQuery, state: FSMContext):
        await callback.answer("Создание тренировки отменено")
        await callback.message.edit_text("Создание тренировки отменено.", reply_markup=None)
        await state.clear()

    async def _wc_public_selected(self, callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        is_public = callback.data == "workout_public_true"
        await state.update_data(is_public=is_public)
        
        if is_public:
            await state.update_data(invited_users=[])
            await self._show_confirmation(callback.message, state)
        else:
            if not self.user_manager or not hasattr(self.user_manager, "get_all_users"):
                await callback.message.answer("User manager не настроен. Невозможно выбрать пользователей.")
                return
            try:
                users = await self.user_manager.get_all_users()
                user_names = [user.full_name for user in users]
                selection = SuperlistSelection(user_names)
                superlist_selections_admin[callback.message.chat.id] = {'selection': selection, 'all_users': users, 'current_page': 1}
                text = "Выберите пользователей для приглашения:\n\nВыбранные: никто"
                keyboard = selection.get_inline_keyboard()
                await callback.message.edit_text(text, reply_markup=keyboard)
                await state.set_state(AdminWorkoutStates.waiting_for_invited_selection)
            except Exception:
                logger.exception("Ошибка получения списка пользователей для приглашения")
                await callback.message.answer("Ошибка при выборе пользователей.")

    async def _show_confirmation(self, message: Message, state: FSMContext):
        data = await state.get_data()
        parts = [
            f"Название: {data.get('name')}",
            f"Дата: {data.get('date').strftime('%d.%m.%Y')}",
            f"Время: {data.get('time').strftime('%H:%M')}",
        ]
        lat = data.get("latitude")
        lon = data.get("longitude")
        parts.append(f"Гео: {f'{lat},{lon}' if lat and lon else 'не указано'}")
        parts.append(f"Цена: {data.get('price') if data.get('price') is not None else 'не указана'}")
        comment = data.get('comment')
        parts.append(f"Комментарий: {comment if comment else 'не указан'}")
        parts.append(f"Тип: {'Публичная' if data.get('is_public') else 'Приватная'}")
        if not data.get('is_public'):
            invited = data.get('invited_users', [])
            invited_names = [u.full_name for u in invited] if invited else []
            parts.append(f"Приглашенные: {', '.join(invited_names) if invited_names else 'никто'}")
        summary = "Подтвердите создание тренировки:\n\n" + "\n".join(parts)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=UI.CONFIRM, callback_data="create_workout_confirm"),
             InlineKeyboardButton(text=UI.CANCEL, callback_data="create_workout_cancel")]
        ])
        await message.answer(summary, reply_markup=kb)
        await state.set_state(AdminWorkoutStates.waiting_for_confirmation)

    async def _wc_invited_selection(self, callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        data = superlist_selections_admin.get(callback.message.chat.id)
        if not data:
            await callback.message.answer("Ошибка: сессия выбора истекла.")
            return
        selection = data['selection']
        all_users = data['all_users']
        current_page = data.get('current_page', 1)
        
        from utils.superlist import process_superlist_selection_callback
        result = await process_superlist_selection_callback(callback.data, selection)
        
        if result is None:
            selected_names = list(selection.selected)
            selected_text = ", ".join(selected_names) if selected_names else "никто"
            text = f"Выберите пользователей для приглашения:\n\nВыбранные: {selected_text}"
            keyboard = selection.get_inline_keyboard(current_page)
            await callback.message.edit_text(text, reply_markup=keyboard)
        elif isinstance(result, dict) and "selected" in result:
            selected_names = result["selected"]
            invited_users = [user for user in all_users if user.full_name in selected_names]
            await state.update_data(invited_users=invited_users)
            del superlist_selections_admin[callback.message.chat.id]
            await self._show_confirmation(callback.message, state)
        elif isinstance(result, dict) and "page" in result:
            current_page = result["page"]
            superlist_selections_admin[callback.message.chat.id]['current_page'] = current_page
            keyboard = selection.get_inline_keyboard(current_page)
            await callback.message.edit_reply_markup(reply_markup=keyboard)

    async def _wc_confirm(self, callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        data = await state.get_data()
        workout_id = None
        async with async_session_maker() as session:
            workout = WorkoutModel(
                date=data["date"],
                time=data["time"],
                latitude=data.get("latitude"),
                longitude=data.get("longitude"),
                name=data.get("name") or "",
                comment=data.get("comment"),
                price=data.get("price"),
                is_public=data.get("is_public", True)
            )
            invited_users = data.get("invited_users", [])
            workout.users_invited.extend(invited_users)
            session.add(workout)
            await session.flush()
            workout_id = workout.id
            await session.commit()
        
        data['workout_id'] = workout_id
        await callback.message.edit_text(f"{UI.CHECK_MARK} Тренировка создана.", reply_markup=None)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Разослать сейчас", callback_data="workout:send_now")],
            [InlineKeyboardButton(text="Разослать потом", callback_data="workout:send_later")]
        ])
        await callback.message.answer("Разослать уведомления участникам?", reply_markup=kb)
        await state.update_data(workout_id=workout_id)
        await state.set_state(AdminWorkoutStates.waiting_for_send_option)

        
        

    async def _process_simple_calendar(self, callback: CallbackQuery, callback_data, state: FSMContext):
        user_locale = await get_user_locale(callback.from_user)
        try:
            calendar = SimpleCalendar(locale=user_locale, show_alerts=True)
        except Exception as e:
            logger.warning(f"Calendar locale '{user_locale}' unsupported: {e}; falling back to 'en'.")
            try:
                calendar = SimpleCalendar(locale="en", show_alerts=True)
            except Exception:
                calendar = SimpleCalendar(show_alerts=True)

        selected, date = await calendar.process_selection(callback, callback_data)
        if selected:
            date_only = date.date() if hasattr(date, 'date') else date
            if date_only < date_type.today():
                await callback.answer("❌ Дата не может быть в прошлом!", show_alert=True)
                kb = await calendar.start_calendar()
                await callback.message.edit_reply_markup(reply_markup=kb)
                return
            
            await callback.answer()
            await state.update_data(date=date_only)
            await callback.message.answer(f"Дата выбрана: {date_only.strftime('%d.%m.%Y')}")
            await callback.message.answer("Введите время тренировки (ЧЧ:ММ), например 19:30")
            await state.set_state(AdminWorkoutStates.waiting_for_time)

    async def _process_dialog_calendar(self, callback: CallbackQuery, callback_data, state: FSMContext):
        user_locale = await get_user_locale(callback.from_user)
        try:
            dialog_cal = DialogCalendar(locale=user_locale)
        except Exception as e:
            logger.warning(f"DialogCalendar locale '{user_locale}' unsupported: {e}; falling back to 'en'.")
            try:
                dialog_cal = DialogCalendar(locale="en")
            except Exception:
                dialog_cal = DialogCalendar()

        selected, date = await dialog_cal.process_selection(callback, callback_data)
        if selected:
            date_only = date.date() if hasattr(date, 'date') else date
            if date_only < date_type.today():
                await callback.answer("❌ Дата не может быть в прошлом!", show_alert=True)
                kb = await dialog_cal.start_calendar()
                await callback.message.edit_reply_markup(reply_markup=kb)
                return
            
            await callback.answer()
            await state.update_data(date=date_only)
            await callback.message.answer(f"Дата выбрана: {date_only.strftime('%d.%m.%Y')}")
            await callback.message.answer("Введите время тренировки (ЧЧ:ММ), например 19:30:")
            await state.set_state(AdminWorkoutStates.waiting_for_time)

    async def send_panel(self, bot, chat_id: int, text: str = "Админская панель"):
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=self.markup())

    async def send_workout_notifications(self, message: Message, data: dict):
        is_public = data.get("is_public", True)
        invited_users = data.get("invited_users", [])
        workout_id = data.get("workout_id")
        
        if not workout_id:
            logger.error("workout_id not found in data")
            return
        
        try:
            async with async_session_maker() as session:
                workout = await session.get(WorkoutModel, workout_id)
                if not workout:
                    logger.error(f"Workout {workout_id} not found")
                    return
                
                if is_public:
                    users = await UserManager(async_session_maker).get_all_users()
                    logger.info(f"Рассылка уведомлений: публичная=True, всем пользователям={len(users)}")
                    await message.answer(f"Рассылка уведомлений: публичная=True, всем пользователям ({len(users)})")
                else:
                    users = await UserManager(async_session_maker).get_all_users([u.id for u in invited_users])
                    logger.info(f"Рассылка уведомлений: публичная=False, приглашенных={len(users)}")
                    await message.answer(f"Рассылка уведомлений: публичная=False, приглашенных={len(users)}")
                
                for user in users:
                    try:
                        notification_text = workout.get_text_notification_tg()
                        
                        keyboard_buttons = []
                        
                        if workout.price == 0:
                            keyboard_buttons.append(
                                InlineKeyboardButton(text="Участвую", callback_data=f"workout:join:{workout_id}")
                            )
                        else:
                            keyboard_buttons.append(
                                InlineKeyboardButton(text=f"Участвую ({workout.price})", callback_data=f"workout:join:{workout_id}")
                            )
                        
                        if workout.has_location:
                            keyboard_buttons.append(
                                InlineKeyboardButton(text="Получить геолокацию", callback_data=f"workout:location:{workout_id}")
                            )
                        
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[[btn] for btn in keyboard_buttons])
                        
                        await self.bot.send_message(
                            chat_id=user.tg_id,
                            text=notification_text,
                            reply_markup=keyboard,
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send notification to user {user.tg_id}: {e}")
        except Exception as e:
            logger.error(f"Error in send_workout_notifications: {e}")

    async def _on_workout_join(self, callback: CallbackQuery):
        await callback.answer()
        workout_id = int(callback.data.split(":")[2])
        user_tg_id = callback.from_user.id

        async with async_session_maker() as session:
            user = await UserManager(async_session_maker).get_by_tg_id(user_tg_id)
            if not user:
                await callback.message.answer("Пользователь не найден в системе.")
                return

            workout = await session.get(WorkoutModel, workout_id)
            if not workout:
                await callback.message.answer("Тренировка не найдена.")
                return

            existing = (await session.execute(
                select(wp_table).where(
                    (wp_table.c.workout_id == workout_id) &
                    (wp_table.c.user_id == user.id)
                )
            )).first()

            if existing:
                pd = existing.payment_details or {}
                if pd.get("status") == "success":
                    await callback.message.answer(f"✅ Вы уже записаны на тренировку «{workout.name}».")
                elif pd.get("status") == "pending":
                    await callback.message.answer(f"⏳ Ожидается оплата за тренировку «{workout.name}».")
                return

            if not workout.price or workout.price == 0:
                await session.execute(
                    wp_table.insert().values(
                        workout_id=workout_id,
                        user_id=user.id,
                        payment_details={"payment_method": None, "status": "success"},
                    )
                )
                await session.commit()
                await callback.message.answer(
                    f"✅ Вы успешно записаны на тренировку!\n\n"
                    f"*{workout.name}*\n"
                    f"📅 Дата: {workout.date.strftime('%d.%m.%Y')}\n"
                    f"🕐 Время: {workout.time.strftime('%H:%M')}",
                    parse_mode="Markdown",
                )
            else:
                from payments import WorkoutPaymentHelper
                kb = WorkoutPaymentHelper.get_payment_keyboard(workout_id, workout.price)
                await callback.message.answer(
                    f"Тренировка: *{workout.name}*\n"
                    f"Стоимость: {workout.price} ₽\n\n"
                    f"Выберите способ оплаты:",
                    reply_markup=kb,
                    parse_mode="Markdown",
                )


    async def _on_pay_tg(self, callback: CallbackQuery):
        await callback.answer()
        workout_id = int(callback.data.split(":")[1])
        user_tg_id = callback.from_user.id

        user = await UserManager(async_session_maker).get_by_tg_id(user_tg_id)
        if not user:
            await callback.message.answer("Пользователь не найден в системе.")
            return

        if not user.phone or not user.email:
            missing = []
            if not user.phone:
                missing.append("номер телефона")
            if not user.email:
                missing.append("email")
            await callback.answer(
                f"⚠️ Для оплаты укажите: {' и '.join(missing)}. Используйте /profile",
                show_alert=True,
            )
            return

        async with async_session_maker() as session:
            workout = await session.get(WorkoutModel, workout_id)
            if not workout:
                await callback.message.answer("Тренировка не найдена.")
                return

            await callback.message.answer_invoice(
                title=workout.name,
                description=f"Тренировка {workout.date.strftime('%d.%m.%Y')} в {workout.time.strftime('%H:%M')}",
                payload=f"workout_{workout_id}_{user.tg_id}",
                provider_token=settings.PAYMENT_TOKEN_TG,
                currency="RUB",
                prices=[{"label": "Стоимость тренировки", "amount": int(workout.price * 100)}],
            )

    @requires_payment_info
    async def _on_pay_link(self, callback: CallbackQuery):
        await callback.answer()
        workout_id = int(callback.data.split(":")[1])
        user_tg_id = callback.from_user.id

        user = await UserManager(async_session_maker).get_by_tg_id(user_tg_id)
        if not user:
            await callback.message.answer("Пользователь не найден в системе.")
            return

        async with async_session_maker() as session:
            workout = await session.get(WorkoutModel, workout_id)
            if not workout:
                await callback.message.answer("Тренировка не найдена.")
                return

            existing = (await session.execute(
                select(wp_table).where(
                    (wp_table.c.workout_id == workout_id) &
                    (wp_table.c.user_id == user.id)
                )
            )).first()
            if existing:
                pd = existing.payment_details or {}
                if pd.get("status") == "success":
                    await callback.answer("✅ Вы уже записаны на эту тренировку.", show_alert=True)
                    return
                if pd.get("status") == "pending":
                    await callback.answer("⏳ Оплата уже в процессе. Используйте ссылку из предыдущего сообщения.", show_alert=True)
                    return

            try:
                from payments import PaymentService, WorkoutPaymentHelper
                payment = await PaymentService.create_payment(
                    amount=workout.price,
                    description=f"Тренировка {workout.name} — {workout.date.strftime('%d.%m.%Y')}",
                    customer_email=user.email,
                    customer_phone=user.phone,
                    workout_id=str(workout_id),
                    user_id=str(user.id),
                    tg_id=str(user.tg_id),
                )

                payment_details = WorkoutPaymentHelper.create_payment_details(
                    payment_method="LINK",
                    status="pending",
                    payment_id=payment.get("id"),
                )

                existing = (await session.execute(
                    select(wp_table).where(
                        (wp_table.c.workout_id == workout_id) &
                        (wp_table.c.user_id == user.id)
                    )
                )).first()

                if existing:
                    await session.execute(
                        sa_update(wp_table)
                        .where(
                            (wp_table.c.workout_id == workout_id) &
                            (wp_table.c.user_id == user.id)
                        )
                        .values(payment_details=payment_details)
                    )
                else:
                    await session.execute(
                        wp_table.insert().values(
                            workout_id=workout_id,
                            user_id=user.id,
                            payment_details=payment_details,
                        )
                    )
                await session.commit()

                confirmation_url = payment.get("confirmation_url")
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                pay_kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="💳 Оплатить через СБП", url=confirmation_url)
                ]])
                await callback.message.answer(
                    f"Тренировка: <b>{workout.name}</b>\n"
                    f"Стоимость: <b>{workout.price} ₽</b>\n\n"
                    f"После оплаты вы получите подтверждение.",
                    reply_markup=pay_kb,
                )
            except Exception as e:
                logger.error(f"Ошибка создания платежа СБП: {e}")
                await callback.message.answer("❌ Ошибка при создании платежа. Попробуйте позже.")

    async def _on_workout_location(self, callback: CallbackQuery):
        await callback.answer()
        workout_id = int(callback.data.split(":")[2])
        
        async with async_session_maker() as session:
            workout = await session.get(WorkoutModel, workout_id)
            if not workout:
                await callback.message.answer("Тренировка не найдена.")
                return
            
            if not workout.has_location:
                await callback.message.answer("Геолокация для этой тренировки не указана.")
                return
                       
            try:
                await self.bot.send_location(
                    chat_id=callback.from_user.id,
                    latitude=workout.latitude,
                    longitude=workout.longitude
                )
            except Exception as e:
                logger.error(f"Failed to send location: {e}")
                await callback.message.answer(f"📍 {workout.get_address}")

    async def _on_send_workout_option(self, callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        data = await state.get_data()
        
        if callback.data == "workout:send_now":
            await self.send_workout_notifications(callback.message, data)
            await callback.message.answer("✅ Уведомления отправлены!")
        else:
            await callback.message.answer("✅ Отправка отложена. Вы можете отправить позже из списка тренировок.")
        
        await state.clear()

    def workouts_list_markup(self, workouts: List[WorkoutModel], page: int = 1) -> InlineKeyboardMarkup:
        kb = Superlist([f"{w.name} ({w.date.strftime('%d.%m')} {w.time.strftime('%H:%M')})" for w in workouts]).get_inline_keyboard(page=page)
        
        for row in kb.inline_keyboard:
            for btn in row:
                cd = getattr(btn, "callback_data", "") or ""
                if cd.startswith(Superlist.ITEM_PREFIX):
                    idx_str = cd[len(Superlist.ITEM_PREFIX):]
                    if idx_str.isdigit():
                        idx = int(idx_str)
                        if idx < len(workouts):
                            workout = workouts[idx]
                            btn.callback_data = f"admin:review_workout:{workout.id}"
                elif cd.startswith(Superlist.PAGE_PREFIX):
                    page_token = cd[len(Superlist.PAGE_PREFIX):]
                    if page_token.isdigit():
                        btn.callback_data = f"{Superlist.PAGE_PREFIX}{page_token}"
                    else:
                        btn.callback_data = f"{Superlist.PAGE_PREFIX}info"
        
        kb.inline_keyboard.append([InlineKeyboardButton(text=UI.BACK_TO_PANEL, callback_data=self.BACK_TO_PANEL)])
        return kb

    async def _on_list_workouts(self, callback: CallbackQuery):
        await callback.answer()
        try:
            async with async_session_maker() as session:
                from sqlalchemy import select
                now = datetime.now().time()
                today = date_type.today()
                result = await session.execute(
                    select(WorkoutModel).where(
                        (WorkoutModel.date > today) | 
                        ((WorkoutModel.date == today) & (WorkoutModel.time > now))
                    ).order_by(WorkoutModel.date, WorkoutModel.time)
                )
                workouts = result.scalars().all()
                
                if not workouts:
                    await callback.message.answer("Нет предстоящих тренировок.")
                    return
                
                workout_superlist_selections[callback.message.chat.id] = {
                    'workouts': workouts,
                    'current_page': 1
                }
                
                kb = self.workouts_list_markup(workouts, page=1)
                await callback.message.edit_text("📋 Список предстоящих тренировок:", reply_markup=kb)
        except Exception as e:
            logger.exception("Ошибка при получении списка тренировок")
            await callback.message.answer(f"Ошибка при получении списка тренировок: {e}")

    async def _on_list_workouts_page(self, callback: CallbackQuery):
        await callback.answer()
        try:
            data = (callback.data or "").removeprefix(Superlist.PAGE_PREFIX)
            try:
                page = int(data)
            except Exception:
                page = 1
            
            chat_data = workout_superlist_selections.get(callback.message.chat.id)
            if not chat_data:
                await callback.message.answer("Сессия истекла. Используйте /admin для списка.")
                return
            
            workouts = chat_data['workouts']
            kb = self.workouts_list_markup(workouts, page=page)
            await callback.message.edit_reply_markup(reply_markup=kb)
        except Exception as e:
            logger.exception("Ошибка при навигации по тренировкам")
            await callback.message.answer(f"Ошибка: {e}")

    async def _on_workout_selected(self, callback: CallbackQuery):
        await callback.answer()
        try:
            callback_data = callback.data or ""
            workout_id_str = callback_data.replace("admin:review_workout:", "")
            if not workout_id_str.isdigit():
                await callback.message.answer("Ошибка: некорректный ID тренировки.")
                return
            
            workout_id = int(workout_id_str)
            
            async with async_session_maker() as session:
                workout = await session.get(WorkoutModel, workout_id)
                if not workout:
                    await callback.message.answer("Тренировка не найдена.")
                    return
                
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Разослать информацию", callback_data=f"admin:resend_workout:{workout.id}")],
                    [InlineKeyboardButton(text=UI.BACK_TO_PANEL, callback_data=self.BACK_TO_PANEL)]
                ])
                
                await callback.message.edit_text(workout.get_text_display_tg(), reply_markup=kb, parse_mode="Markdown")
        except Exception as e:
            logger.exception("Ошибка при показе деталей тренировки")
            await callback.message.answer(f"Ошибка: {e}")

    async def _on_resend_workout(self, callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        try:
            workout_id = int(callback.data.split(":")[-1])
            
            async with async_session_maker() as session:
                workout = await session.get(WorkoutModel, workout_id)
                if not workout:
                    await callback.message.answer("Тренировка не найдена.")
                    return
                
                data = {
                    'workout_id': workout_id,
                    'is_public': workout.is_public,
                    'invited_users': workout.users_invited
                }
                
                await self.send_workout_notifications(callback.message, data)
                await callback.message.answer("✅ Уведомления отправлены повторно!")
        except Exception as e:
            logger.exception("Ошибка при повторной рассылке")
            await callback.message.answer(f"Ошибка: {e}")

    async def _on_pre_checkout_query(self, pre_checkout_query):
        """Обработчик проверки платежа перед подтверждением"""
        await pre_checkout_query.answer(ok=True)

    async def _on_successful_payment(self, message):
        """Обработчик успешного платежа через Telegram"""
        try:
            if not message.successful_payment:
                return

            payload = message.successful_payment.invoice_payload
            parts = payload.split("_")
            if len(parts) < 3 or parts[0] != "workout":
                logger.error(f"Invalid payload format: {payload}")
                return

            workout_id = int(parts[1])

            from payments import WorkoutPaymentHelper
            async with async_session_maker() as session:
                workout = await session.get(WorkoutModel, workout_id)
                user = await UserManager(async_session_maker).get_by_tg_id(message.from_user.id)

                if not workout or not user:
                    await message.answer("❌ Ошибка: тренировка или пользователь не найдены.")
                    return

                payment_details = WorkoutPaymentHelper.create_payment_details(
                    payment_method="TG",
                    status="success",
                )

                existing = (await session.execute(
                    select(wp_table).where(
                        (wp_table.c.workout_id == workout_id) &
                        (wp_table.c.user_id == user.id)
                    )
                )).first()

                if existing:
                    await session.execute(
                        sa_update(wp_table)
                        .where(
                            (wp_table.c.workout_id == workout_id) &
                            (wp_table.c.user_id == user.id)
                        )
                        .values(payment_details=payment_details)
                    )
                else:
                    await session.execute(
                        wp_table.insert().values(
                            workout_id=workout_id,
                            user_id=user.id,
                            payment_details=payment_details,
                        )
                    )
                await session.commit()

                await message.answer(
                    f"✅ Спасибо за оплату!\n\n"
                    f"Вы успешно зарегистрированы на тренировку:\n"
                    f"*{workout.name}*\n\n"
                    f"📅 Дата: {workout.date.strftime('%d.%m.%Y')}\n"
                    f"🕐 Время: {workout.time.strftime('%H:%M')}\n"
                    f"💰 Стоимость: {workout.price} ₽",
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.exception("Ошибка при обработке успешного платежа")
            await message.answer(f"❌ Ошибка при обработке платежа: {e}")

        