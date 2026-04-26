from typing import Callable, Any, Optional
from functools import wraps
import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from config import settings
from database import async_session_maker
from managers.user import UserManager
from states import RegistrationStates, WorkoutStates, AdminStates, UserProfileStates
from message_templates import REGISTRATION_MESSAGES
from managers.workouts.garmin import GarminWorkout
import json
from utils.admin import AdminPanel

logger = logging.getLogger(__name__)

router = Router()

admin_panel: Optional[AdminPanel] = None


def owner_only(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs) -> Any:
        user_id = message.from_user.id
        if user_id != settings.OWNER_ID:
            await message.answer("❌ Эта команда доступна только владельцу бота.")
            logger.warning(f"Попытка доступа к owner команде от пользователя {user_id}")
            return
        return await func(message, *args, **kwargs)
    return wrapper


def admin_only(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs) -> Any:
        user_id = message.from_user.id
        if user_id not in settings.ADMIN_IDS:
            await message.answer("❌ Эта команда доступна только администраторам.")
            logger.warning(f"Попытка доступа к admin команде от пользователя {user_id}")
            return
        return await func(message, *args, **kwargs)
    return wrapper

def registered_only(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs) -> Any:
        tg_id = message.from_user.id
        async with async_session_maker() as session:
            user_manager = UserManager(session)
            if not await user_manager.exists(tg_id):
                await message.answer(
                    "❌ Вы не зарегистрированы. Пожалуйста, используйте /register для заполнения данных."
                )
                logger.warning(f"Попытка доступа к зарегистрированной команде от незарегистрированного пользователя {tg_id}")
                return
        return await func(message, *args, **kwargs)
    return wrapper

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_name = message.from_user.first_name
    tg_id = message.from_user.id

    user_manager = UserManager(async_session_maker)

    if not await user_manager.exists(tg_id):
        await user_manager.create(
            tg_id=tg_id,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            tg_username=message.from_user.username
        )
        logger.info(f"Зарегистрирован новый пользователь: {tg_id}")

    await message.answer(
        f"👋 Привет, {user_name}!\n\n"
        f"Я бот-тренер. Используй /help для просмотра доступных команд."
    )
    logger.info(f"Пользователь {tg_id} использовал команду /start")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    user_id = message.from_user.id
    is_admin = user_id in settings.ADMIN_IDS
    is_owner = user_id == settings.OWNER_ID
    
    help_text = "📋 <b>Доступные команды:</b>\n\n"
    help_text += "/start - Начать работу с ботом\n"
    help_text += "/help - Показать это сообщение\n"
    help_text += "/status - Показать статус бота\n"
    help_text += "/register - Заполнить данные профиля\n"
    help_text += "/profile - Показать мой профиль\n"
    
    if is_admin:
        help_text += "\n<b>Команды администратора:</b>\n"
        help_text += "/admin - Панель администратора\n"
        help_text += "/stats - Статистика бота\n"
    
    if is_owner:
        help_text += "\n<b>Команды владельца:</b>\n"
        help_text += "/owner - Панель владельца\n"
        help_text += "/broadcast - Рассылка сообщений\n"
    
    await message.answer(help_text)


@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext):
    """Команда профиля пользователя - просмотр и редактирование"""
    tg_id = message.from_user.id
    user_manager = UserManager(async_session_maker)
    user = await user_manager.get_by_tg_id(tg_id)
    
    if not user:
        await message.answer(
            "❌ Ваш профиль не найден.\n\n"
            "Используйте /register для регистрации."
        )
        return
    
    from utils.ui_constants import UI

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=UI.EDIT, callback_data="profile:edit_fields")],
        [InlineKeyboardButton(text=UI.DELETE, callback_data="profile:delete_account")],
    ])

    await message.answer(user.get_text_display_tg(), reply_markup=kb, parse_mode='Markdown')


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Обработчик команды /status"""
    await message.answer("✅ Бот работает нормально!")


@router.message(Command("admin"))
@admin_only
async def cmd_admin(message: Message):
    """Панель администратора"""
    if admin_panel is None:
        await message.answer(
            "🔧 <b>Панель администратора</b>\n\n"
            "Админ-панель не настроена."
        )
        return

    await admin_panel.send_panel(message.bot, message.chat.id)


@router.message(Command("stats"))
@admin_only
async def cmd_stats(message: Message):
    async with async_session_maker() as session:
        user_manager = UserManager(session)
        total_users = await user_manager.count()
    
    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: {total_users}"
    )


@router.message(Command("owner"))
@owner_only
async def cmd_owner(message: Message):
    """Панель владельца"""
    await message.answer(
        "👑 <b>Панель владельца</b>\n\n"
        "Здесь будут доступны функции владельца бота."
    )


@router.message(Command("broadcast"))
@owner_only
async def cmd_broadcast(message: Message):
    """Рассылка сообщений (только для владельца)"""
    await message.answer(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Функция рассылки будет реализована позже."
    )


@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext):
    """Начало процесса регистрации"""
    tg_id = message.from_user.id
    
    user_manager = UserManager(async_session_maker)
    user = await user_manager.get_by_tg_id(tg_id)
    
    if not user:
        await user_manager.create(
            tg_id=tg_id,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            tg_username=message.from_user.username
        )
        logger.info(f"Создан новый пользователь при регистрации: {tg_id}")
    
    await message.answer(REGISTRATION_MESSAGES['start'])
    await message.answer("Введите ваше имя:")
    await state.set_state(RegistrationStates.waiting_for_first_name)


@router.message(RegistrationStates.waiting_for_first_name)
async def process_first_name(message: Message, state: FSMContext):
    """Обработка имени"""
    first_name = message.text.strip()
    
    if not first_name:
        await message.answer("❌ Имя не должно быть пустым. Введите ваше имя:")
        return
    
    await state.update_data(first_name=first_name)
    
    skip_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏭️ Пропустить")]],
        resize_keyboard=True
    )
    
    await message.answer(REGISTRATION_MESSAGES['last_name'], reply_markup=skip_kb)
    await state.set_state(RegistrationStates.waiting_for_last_name)


@router.message(RegistrationStates.waiting_for_last_name)
async def process_last_name(message: Message, state: FSMContext):
    """Обработка фамилии"""
    last_name = None if message.text == "⏭️ Пропустить" else message.text.strip()
    
    await state.update_data(last_name=last_name)
    
    skip_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏭️ Пропустить")]],
        resize_keyboard=True
    )
    
    await message.answer(REGISTRATION_MESSAGES['middle_name'], reply_markup=skip_kb)
    await state.set_state(RegistrationStates.waiting_for_middle_name)


@router.message(RegistrationStates.waiting_for_middle_name)
async def process_middle_name(message: Message, state: FSMContext):
    """Обработка отчества"""
    middle_name = None if message.text == "⏭️ Пропустить" else message.text.strip()
    
    await state.update_data(middle_name=middle_name)
    
    skip_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏭️ Пропустить")]],
        resize_keyboard=True
    )
    
    await message.answer(REGISTRATION_MESSAGES['birth_date'], reply_markup=skip_kb)
    await state.set_state(RegistrationStates.waiting_for_birth_date)


@router.message(RegistrationStates.waiting_for_birth_date)
async def process_birth_date(message: Message, state: FSMContext):
    """Обработка даты рождения"""
    birth_date = None
    
    if message.text != "⏭️ Пропустить":
        try:
            for date_format in ["%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]:
                try:
                    birth_date = datetime.strptime(message.text.strip(), date_format).date()
                    break
                except ValueError:
                    continue
            
            if birth_date is None:
                await message.answer(
                    "❌ Неверный формат даты. Попробуйте еще раз.\n"
                    "Используйте формат: ДД.ММ.ГГГГ (например, 01.01.1990)\n\n"
                    "Или нажмите '⏭️ Пропустить'"
                )
                return
        except Exception as e:
            logger.error(f"Ошибка при парсинге даты: {e}")
            await message.answer(
                "❌ Произошла ошибка. Попробуйте еще раз или нажмите '⏭️ Пропустить'"
            )
            return
    
    await state.update_data(birth_date=birth_date)
    
    skip_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏭️ Пропустить")]],
        resize_keyboard=True
    )
    
    await message.answer(REGISTRATION_MESSAGES['weight'], reply_markup=skip_kb)
    await state.set_state(RegistrationStates.waiting_for_weight)


@router.message(RegistrationStates.waiting_for_weight)
async def process_weight(message: Message, state: FSMContext):
    """Обработка веса"""
    weight = None
    
    if message.text != "⏭️ Пропустить":
        try:
            weight = float(message.text.strip().replace(",", "."))
            
            if weight <= 0 or weight > 500:
                await message.answer(
                    "❌ Неверное значение веса. Введите корректный вес (например, 75.5)\n\n"
                    "Или нажмите '⏭️ Пропустить'"
                )
                return
        except ValueError:
            await message.answer(
                "❌ Неверный формат. Введите число (например, 75.5)\n\n"
                "Или нажмите '⏭️ Пропустить'"
            )
            return
    
    data = await state.get_data()
    tg_id = message.from_user.id

    user_manager = UserManager(async_session_maker)

    success = await user_manager.update_user(
        tg_id=tg_id,
        first_name=data.get('first_name', message.from_user.first_name),
        last_name=data.get('last_name'),
        middle_name=data.get('middle_name'),
        birth_date=data.get('birth_date'),
        weight=weight
    )
    
    if success:
        await message.answer(
            REGISTRATION_MESSAGES['complete'],
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"Пользователь {tg_id} завершил регистрацию")
    else:
        await message.answer(
            "❌ Произошла ошибка при сохранении данных. Попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
    
    await state.clear()

@router.callback_query(lambda c: c.data == "profile:edit_fields")
async def profile_edit_fields(callback, state: FSMContext):
    """Показать выбор полей для редактирования в профиле"""
    from utils.ui_constants import UI
    
    await callback.answer()
    tg_id = callback.from_user.id
    user_manager = UserManager(async_session_maker)
    user = await user_manager.get_by_tg_id(tg_id)
    
    if not user:
        await callback.message.answer("❌ Профиль не найден.")
        return
    
    await state.update_data(editing_user_id=user.id)
    
    editable_fields = user.editable_fields_display
    
    buttons = []
    for field_name, field_label in editable_fields.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ {field_label}",
                callback_data=f"profile:edit_field:{field_name}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(text="❌ Закрыть", callback_data="profile:cancel")
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    text = (
        f"{UI.PERSON} <b>Редактирование профиля</b>\n"
        f"Выберите поле для изменения:"
    )
    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(lambda c: c.data and c.data.startswith("profile:edit_field:"))
async def profile_edit_field(callback, state: FSMContext):
    """Обработать выбор поля для редактирования профиля"""
    await callback.answer()
    data_parts = callback.data.split(":")
    field_name = data_parts[2] if len(data_parts) > 2 else None
    
    if not field_name:
        await callback.message.answer("❌ Ошибка: некорректные данные.")
        return
    
    await state.update_data(editing_field=field_name)
    
    field_to_state = {
        "first_name": UserProfileStates.waiting_for_edit_first_name,
        "last_name": UserProfileStates.waiting_for_edit_last_name,
        "middle_name": UserProfileStates.waiting_for_edit_middle_name,
        "birth_date": UserProfileStates.waiting_for_edit_birth_date,
        "weight": UserProfileStates.waiting_for_edit_weight,
        "phone": UserProfileStates.waiting_for_edit_phone,
        "email": UserProfileStates.waiting_for_edit_email,
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
        await callback.message.answer(f"❌ Поле '{field_name}' не поддерживается для редактирования.")
        return
    
    await state.set_state(field_to_state[field_name])
    label = field_to_label.get(field_name, field_name)
    
    await callback.message.answer(f"✏️ Введите новое значение для '{label}':")


@router.callback_query(lambda c: c.data == "profile:delete_account")
async def profile_delete_account(callback, state: FSMContext):
    """Подтверждение удаления аккаунта"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    await callback.answer()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data="profile:confirm_delete"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="profile:cancel_delete")
        ]
    ])
    
    text = (
        "⚠️ <b>Удаление аккаунта</b>\n\n"
        "Вы уверены, что хотите удалить свой аккаунт?\n"
        "Это действие невозможно отменить!"
    )
    
    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(lambda c: c.data == "profile:confirm_delete")
async def profile_confirm_delete(callback, state: FSMContext):
    """Подтвердить удаление аккаунта"""
    await callback.answer()
    tg_id = callback.from_user.id
    
    user_manager = UserManager(async_session_maker)
    success = await user_manager.delete(tg_id)
    
    if success:
        await callback.message.answer(
            "✅ Ваш аккаунт успешно удален.\n\n"
            "Используйте /register для создания нового аккаунта."
        )
    else:
        await callback.message.answer("❌ Ошибка при удалении аккаунта.")
    
    await state.clear()


@router.callback_query(lambda c: c.data in ["profile:cancel", "profile:cancel_delete"])
async def profile_cancel(callback, state: FSMContext):
    """Отмена операции в профиле"""
    await callback.answer()
    await callback.message.delete()
    await state.clear()

@router.message(AdminStates.waiting_for_edit_first_name)
async def edit_first_name(message: Message, state: FSMContext):
    first_name = (message.text or "").strip()
    
    if not first_name or len(first_name) > 100:
        await message.answer("❌ Неверное имя. Введите имя длиной от 1 до 100 символов.")
        return
    
    data = await state.get_data()
    user_id = data.get('editing_user_id')
    
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user_by_id(user_id, first_name=first_name)
    
    if success:
        await message.answer(f"✅ Имя обновлено на '{first_name}'")
    else:
        await message.answer("❌ Ошибка при обновлении имени.")
    
    await state.clear()


@router.message(AdminStates.waiting_for_edit_last_name)
async def edit_last_name(message: Message, state: FSMContext):
    """Обработка редактирования фамилии"""
    last_name = (message.text or "").strip()
    
    if not last_name or len(last_name) > 100:
        await message.answer("❌ Неверная фамилия. Введите фамилию длиной от 1 до 100 символов.")
        return
    
    data = await state.get_data()
    user_id = data.get('editing_user_id')
    
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user_by_id(user_id, last_name=last_name)
    
    if success:
        await message.answer(f"✅ Фамилия обновлена на '{last_name}'")
    else:
        await message.answer("❌ Ошибка при обновлении фамилии.")
    
    await state.clear()


@router.message(AdminStates.waiting_for_edit_middle_name)
async def edit_middle_name(message: Message, state: FSMContext):
    """Обработка редактирования отчества"""
    middle_name = (message.text or "").strip()
    
    if middle_name and len(middle_name) > 100:
        await message.answer("❌ Неверное отчество. Введите отчество длиной до 100 символов.")
        return
    
    data = await state.get_data()
    user_id = data.get('editing_user_id')
    
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user_by_id(user_id, middle_name=middle_name or None)
    
    if success:
        await message.answer(f"✅ Отчество обновлено на '{middle_name}'")
    else:
        await message.answer("❌ Ошибка при обновлении отчества.")
    
    await state.clear()


@router.message(AdminStates.waiting_for_edit_weight)
async def edit_weight(message: Message, state: FSMContext):
    """Обработка редактирования веса"""
    weight = None
    
    try:
        weight = float((message.text or "").strip().replace(",", "."))
        
        if weight <= 0 or weight > 500:
            await message.answer(
                "❌ Неверное значение веса. Введите корректный вес (например, 75.5)"
            )
            return
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Введите число (например, 75.5)"
        )
        return
    
    data = await state.get_data()
    user_id = data.get('editing_user_id')
    
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user_by_id(user_id, weight=weight)
    
    if success:
        await message.answer(f"✅ Вес обновлен на {weight} кг")
    else:
        await message.answer("❌ Ошибка при обновлении веса.")
    
    await state.clear()


@router.message(AdminStates.waiting_for_edit_phone)
async def edit_phone_admin(message: Message, state: FSMContext):
    import re
    phone = (message.text or "").strip()
    phone = re.sub(r"[^\d+]", "", phone)
    if not re.match(r"^\+?7\d{10}$|^8\d{10}$", phone):
        await message.answer(
            "❌ Неверный формат телефона.\n"
            "Введите номер в формате 79991234567 или +79991234567"
        )
        return
    if phone.startswith("8"):
        phone = "7" + phone[1:]
    data = await state.get_data()
    user_id = data.get("editing_user_id")
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user_by_id(user_id, phone=phone)
    if success:
        await message.answer(f"✅ Телефон обновлен на {phone}")
    else:
        await message.answer("❌ Ошибка при обновлении телефона.")
    await state.clear()


@router.message(AdminStates.waiting_for_edit_email)
async def edit_email_admin(message: Message, state: FSMContext):
    import re
    email = (message.text or "").strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        await message.answer("❌ Неверный формат email. Пример: user@example.com")
        return
    data = await state.get_data()
    user_id = data.get("editing_user_id")
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user_by_id(user_id, email=email)
    if success:
        await message.answer(f"✅ Email обновлен на {email}")
    else:
        await message.answer("❌ Ошибка при обновлении email.")
    await state.clear()


@router.message(UserProfileStates.waiting_for_edit_first_name)
async def profile_edit_first_name(message: Message, state: FSMContext):
    """Редактирование имени в профиле"""
    first_name = (message.text or "").strip()
    
    if not first_name or len(first_name) > 100:
        await message.answer("❌ Неверное имя. Введите имя длиной от 1 до 100 символов.")
        return
    
    tg_id = message.from_user.id
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user(tg_id=tg_id, first_name=first_name)
    
    if success:
        await message.answer(f"✅ Имя обновлено на '{first_name}'")
    else:
        await message.answer("❌ Ошибка при обновлении имени.")
    
    await state.clear()


@router.message(UserProfileStates.waiting_for_edit_last_name)
async def profile_edit_last_name(message: Message, state: FSMContext):
    """Редактирование фамилии в профиле"""
    last_name = (message.text or "").strip()
    
    if not last_name or len(last_name) > 100:
        await message.answer("❌ Неверная фамилия. Введите фамилию длиной от 1 до 100 символов.")
        return
    
    tg_id = message.from_user.id
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user(tg_id=tg_id, last_name=last_name)
    
    if success:
        await message.answer(f"✅ Фамилия обновлена на '{last_name}'")
    else:
        await message.answer("❌ Ошибка при обновлении фамилии.")
    
    await state.clear()


@router.message(UserProfileStates.waiting_for_edit_middle_name)
async def profile_edit_middle_name(message: Message, state: FSMContext):
    """Редактирование отчества в профиле"""
    middle_name = (message.text or "").strip()
    
    if middle_name and len(middle_name) > 100:
        await message.answer("❌ Неверное отчество. Введите отчество длиной до 100 символов.")
        return
    
    tg_id = message.from_user.id
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user(tg_id=tg_id, middle_name=middle_name or None)
    
    if success:
        await message.answer(f"✅ Отчество обновлено на '{middle_name}'")
    else:
        await message.answer("❌ Ошибка при обновлении отчества.")
    
    await state.clear()


@router.message(UserProfileStates.waiting_for_edit_birth_date)
async def profile_edit_birth_date(message: Message, state: FSMContext):
    """Редактирование даты рождения в профиле"""
    from datetime import datetime
    
    birth_date_str = (message.text or "").strip()
    birth_date = None
    
    formats = ["%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]
    
    for fmt in formats:
        try:
            birth_date = datetime.strptime(birth_date_str, fmt).date()
            break
        except ValueError:
            continue
    
    if not birth_date:
        await message.answer(
            "❌ Неверный формат даты. Введите дату в формате ДД.ММ.ГГГГ\n\n"
            "Пример: 15.06.1990"
        )
        return
    
    from datetime import date as date_cls
    if birth_date > date_cls.today():
        await message.answer("❌ Дата не может быть в будущем.")
        return
    
    tg_id = message.from_user.id
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user(tg_id=tg_id, birth_date=birth_date)
    
    if success:
        await message.answer(f"✅ Дата рождения обновлена на {birth_date.strftime('%d.%m.%Y')}")
    else:
        await message.answer("❌ Ошибка при обновлении даты рождения.")
    
    await state.clear()


@router.message(UserProfileStates.waiting_for_edit_weight)
async def profile_edit_weight(message: Message, state: FSMContext):
    """Редактирование веса в профиле"""
    weight = None

    try:
        weight = float((message.text or "").strip().replace(",", "."))

        if weight <= 0 or weight > 500:
            await message.answer(
                "❌ Неверное значение веса. Введите корректный вес (например, 75.5)"
            )
            return
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Введите число (например, 75.5)"
        )
        return

    tg_id = message.from_user.id
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user(tg_id=tg_id, weight=weight)

    if success:
        await message.answer(f"✅ Вес обновлен на {weight} кг")
    else:
        await message.answer("❌ Ошибка при обновлении веса.")

    await state.clear()


@router.message(UserProfileStates.waiting_for_edit_phone)
async def profile_edit_phone(message: Message, state: FSMContext):
    """Редактирование телефона в профиле"""
    import re
    phone = (message.text or "").strip()
    phone = re.sub(r"[^\d+]", "", phone)
    if not re.match(r"^\+?7\d{10}$|^8\d{10}$", phone):
        await message.answer(
            "❌ Неверный формат телефона.\n"
            "Введите номер в формате 79991234567 или +79991234567"
        )
        return
    if phone.startswith("8"):
        phone = "7" + phone[1:]
    tg_id = message.from_user.id
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user(tg_id=tg_id, phone=phone)
    if success:
        await message.answer(f"✅ Телефон обновлен на {phone}")
    else:
        await message.answer("❌ Ошибка при обновлении телефона.")
    await state.clear()


@router.message(UserProfileStates.waiting_for_edit_email)
async def profile_edit_email(message: Message, state: FSMContext):
    """Редактирование email в профиле"""
    import re
    email = (message.text or "").strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        await message.answer("❌ Неверный формат email. Пример: user@example.com")
        return
    tg_id = message.from_user.id
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user(tg_id=tg_id, email=email)
    if success:
        await message.answer(f"✅ Email обновлен на {email}")
    else:
        await message.answer("❌ Ошибка при обновлении email.")
    await state.clear()


@router.message(AdminStates.waiting_for_edit_birth_date)
async def edit_birth_date(message: Message, state: FSMContext):
    """Обработка редактирования даты рождения в админ панели"""
    from datetime import datetime, date as date_cls
    
    birth_date_str = (message.text or "").strip()
    birth_date = None
    
    formats = ["%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]
    
    for fmt in formats:
        try:
            birth_date = datetime.strptime(birth_date_str, fmt).date()
            break
        except ValueError:
            continue
    
    if not birth_date:
        await message.answer(
            "❌ Неверный формат даты. Введите дату в формате ДД.МММ.ГГГГ\n\n"
            "Пример: 15.06.1990"
        )
        return
    
    if birth_date > date_cls.today():
        await message.answer("❌ Дата не может быть в будущем.")
        return
    
    data = await state.get_data()
    user_id = data.get('editing_user_id')
    
    user_manager = UserManager(async_session_maker)
    success = await user_manager.update_user_by_id(user_id, birth_date=birth_date)
    
    if success:
        await message.answer(f"✅ Дата рождения обновлена на {birth_date.strftime('%d.%m.%Y')}")
    else:
        await message.answer("❌ Ошибка при обновлении даты рождения.")
    
    await state.clear()


@router.message(Command("workout"))
@registered_only
async def cmd_workout(message: Message, state: FSMContext):
    """Записать тренировку по ссылке от пользователя от разных платформ"""
    message_text = message.text.strip()
    if len(message_text.split()) < 2:
        await message.answer(
            "❌ Пожалуйста, предоставьте ссылку на тренировку после команды /workout.\n\n"
            "<b>Пример:</b> /workout https://connect.garmin.com/modern/activity/20553107246\n\n"
            "Или вставьте ссылку следующим сообщением."
        )
        await state.set_state(WorkoutStates.waiting_for_workout_link)
        return

    workout_link = message_text.split(maxsplit=1)[1]
    await message.answer(f"✅ Ссылка на тренировку получена:\n<code>{workout_link}</code>")
    
    try:
        result = await process_workout_link(workout_link)
        await message.answer(f"<pre>{json.dumps(result, indent=2, ensure_ascii=False)}</pre>")
    except Exception as e:
        logger.error(f"Ошибка обработки тренировки: {e}")
        await message.answer(f"❌ Ошибка при обработке тренировки: {str(e)}")
    
    await state.clear()


@router.message(WorkoutStates.waiting_for_workout_link)
async def handle_workout_link(message: Message, state: FSMContext):
    """Обработчик состояния ожидания ссылки на тренировку"""
    workout_link = message.text.strip()
    await message.answer(f"✅ Ссылка на тренировку получена:\n<code>{workout_link}</code>")
    
    try:
        result = await process_workout_link(workout_link)
        await message.answer(f"<pre>{json.dumps(result, indent=2, ensure_ascii=False)}</pre>")
    except Exception as e:
        logger.error(f"Ошибка обработки тренировки: {e}")
        await message.answer(f"❌ Ошибка при обработке тренировки: {str(e)}")
    
    await state.clear()

async def process_workout_link(link: str) -> dict:
    """Обработка ссылки на тренировку"""
    gw = GarminWorkout(settings.GARMIN_EMAIL, settings.GARMIN_PASSWORD)
    workout = gw.get_workout_by_link(link)
    res = {
        "locationName": workout.get('locationName'),
        'summaryDTO': workout.get('summaryDTO'),
    }
    return res

@router.message(StateFilter(None), F.text)
async def handle_text_message(message: Message):
    """Обработчик текстовых сообщений"""
    logger.info(f"Получено сообщение от {message.from_user.id}: {message.text}")
    await message.answer("Я получил твоё сообщение! Используй /help для просмотра команд.")


def register_handlers(dp, admin_panel_param=None):
    """
    Регистрирует все обработчики в Dispatcher.
    admin_panel (optional) — экземпляр utils.admin.AdminPanel, если передан, его обработчики регистрируются.
    """
    global admin_panel
    admin_panel = admin_panel_param
    if admin_panel is not None:
        admin_panel.register(router)

    dp.include_router(router)


