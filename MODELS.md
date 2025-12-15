# Trainer Bot - Models Structure

## 📁 Структура моделей данных

```
trainer/
├── models/
│   ├── __init__.py
│   └── user.py          # Модель пользователя
├── repositories/
│   ├── __init__.py
│   └── user_repository.py  # Менеджер для работы с User
├── database.py          # Конфигурация БД и Base класс
├── main.py
├── config.py
└── commands.py
```

## 🗃️ Модель User

### Поля модели:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | Integer | Первичный ключ (автоинкремент) |
| `tg_id` | BigInteger | Telegram ID (уникальный, индексированный) |
| `first_name` | String(100) | Имя |
| `last_name` | String(100) | Фамилия (опционально) |
| `middle_name` | String(100) | Отчество (опционально) |
| `birth_date` | Date | Дата рождения (опционально) |
| `weight` | Float | Вес в кг (опционально) |
| `created_at` | DateTime | Дата создания записи |
| `updated_at` | DateTime | Дата последнего обновления |

### Свойства (properties):

- `full_name` - возвращает полное ФИО
- `age` - вычисляет возраст на основе даты рождения

## 📦 UserManager

Менеджер предоставляет методы для работы с пользователями:

### Методы создания:
- `create()` - создание нового пользователя

### Методы чтения:
- `get_by_id(user_id)` - получить пользователя по ID
- `get_by_tg_id(tg_id)` - получить пользователя по Telegram ID
- `get_all(limit, offset)` - получить всех пользователей с пагинацией
- `exists(tg_id)` - проверить существование пользователя
- `count()` - подсчет количества пользователей

### Методы обновления:
- `update_weight(tg_id, weight)` - обновить вес пользователя
- `update_user(tg_id, **kwargs)` - обновить данные пользователя

### Методы удаления:
- `delete(tg_id)` - удалить пользователя

## 💡 Примеры использования

### Создание пользователя:
```python
async with async_session_maker() as session:
    user_manager = UserManager(session)
    user = await user_manager.create(
        tg_id=123456789,
        first_name="Иван",
        last_name="Иванов",
        middle_name="Иванович",
        birth_date=date(1990, 1, 1),
        weight=75.5
    )
```

### Получение пользователя:
```python
async with async_session_maker() as session:
    user_manager = UserManager(session)
    user = await user_manager.get_by_tg_id(123456789)
    
    if user:
        print(f"Пользователь: {user.full_name}")
        print(f"Возраст: {user.age} лет")
        print(f"Вес: {user.weight} кг")
```

### Обновление веса:
```python
async with async_session_maker() as session:
    user_manager = UserManager(session)
    await user_manager.update_weight(123456789, 73.2)
```

## 🔄 Интеграция с командами

В `commands.py` реализована автоматическая регистрация пользователей:
- При команде `/start` пользователь автоматически добавляется в БД
- Команда `/stats` показывает количество пользователей (только для админов)

## 🚀 Инициализация БД

База данных автоматически инициализируется при запуске бота в `main.py`:
```python
await init_db()  # Создает все таблицы
```

## 📝 Следующие шаги

Можно добавить дополнительные модели:
- `Workout` - тренировки
- `Exercise` - упражнения
- `WeightHistory` - история изменения веса
- `Subscription` - подписки пользователей
