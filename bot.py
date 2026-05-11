import json
import os
import sqlite3
import logging

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode

# ======================== НАСТРОЙКИ ========================
BOT_TOKEN = "8375269633:AAElLiElz8WvjdR_OxeCR6mBJZo6kzGK8xM"           # Токен от @BotFather
CHANNEL_USERNAME = "@growagarden_arferno"       # Юзернейм канала (С @, БЕЗ t.me/)
KEYS_FILE = "keys.json"
DATABASE_FILE = "users.db"
ADMIN_IDS = [7079908197]                  # Список Telegram ID админов

INSTRUCTION_TEXT = (
    "📖 <b>Инструкция по активации ключа в Steam:</b>\n\n"
    "1️⃣ Откройте клиент <b>Steam</b> и войдите в свой аккаунт.\n"
    "2️⃣ Нажмите на <b>имя вашего профиля</b> в правом верхнем углу.\n"
    "3️⃣ В выпадающем меню выберите <b>«Активация продукта»</b>.\n"
    "4️⃣ Нажмите <b>«Далее»</b>, затем поставьте галочку и нажмите <b>«Я согласен»</b>.\n"
    "5️⃣ Введите полученный ключ в пустое поле.\n"
    "6️⃣ Нажмите <b>«Далее»</b> и следуйте инструкциям на экране.\n\n"
    "🎮 После активации игра/софт появится в вашей библиотеке Steam!\n\n"
    "⚠️ Если у вас нет аккаунта Steam — создайте его на <a href=\"https://store.steampowered.com/\">store.steampowered.com</a>"
)
# ==========================================================

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
router = Router()


# ======================== БАЗА ДАННЫХ ========================
def init_db():
    """Создание таблицы пользователей при первом запуске"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            received_key TEXT,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")


def user_exists(user_id: int) -> bool:
    """Проверяет, получал ли пользователь уже ключ"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def save_user(user_id: int, username: str, first_name: str, key: str):
    """Сохраняет пользователя и выданный ему ключ"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (user_id, username, first_name, received_key) VALUES (?, ?, ?, ?)",
        (user_id, username, first_name, key)
    )
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """Возвращает статистику: сколько ключей выдано"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    conn.close()
    return {"total_users": total}


# ======================== РАБОТА С КЛЮЧАМИ ========================
def load_keys() -> list:
    """Загружает список ключей из keys.json"""
    if not os.path.exists(KEYS_FILE):
        return []
    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("keys", [])
    except (json.JSONDecodeError, KeyError):
        logger.error("Ошибка чтения keys.json — создаём пустой файл")
        save_keys([])
        return []


def save_keys(keys: list):
    """Сохраняет список ключей в keys.json"""
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump({"keys": keys}, f, ensure_ascii=False, indent=2)


def get_next_key() -> str | None:
    """Достаёт первый ключ из файла и удаляет его. Возвращает None если пусто."""
    keys = load_keys()
    if not keys:
        return None
    key = keys.pop(0)
    save_keys(keys)
    logger.info(f"🔑 Ключ выдан: {key[:8]}... (осталось {len(keys)})")
    return key


def get_keys_count() -> int:
    """Возвращает количество оставшихся ключей"""
    return len(load_keys())


# ======================== КЛАВИАТУРЫ ========================
def get_channel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой «Проверить подписку» и ссылкой на канал"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Перейти в канал", url="https://t.me/coppers_shop")],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")]
    ])


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после выдачи ключа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Наш канал", url="https://t.me/coppers_shop")]
    ])


# ======================== ПРОВЕРКА ПОДПИСКИ ========================
async def check_subscription(user_id: int) -> bool:
    """
    Проверяет, подписан ли пользователь на канал.
    ВАЖНО: бот должен быть администратором в канале @coppers_shop!
    """
    try:
        member = await bot.get_chat_member(
            chat_id=CHANNEL_USERNAME,
            user_id=user_id
        )
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Ошибка при проверке подписки пользователя {user_id}: {e}")
        return False


# ======================== ОБРАБОТЧИКИ ========================

# --- /start ---
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id

    # Если ключи закончились
    if get_keys_count() == 0:
        await message.answer(
            "👋 <b>Приветствуем!</b>\n\n"
            "😔 К сожалению, бесплатные ключи на данный момент <b>закончились</b>. "
            "Следите за обновлениями — скоро будет новая партия!\n\n"
            "📢 Подпишитесь, чтобы не пропустить:\n"
            f"🔗 <a href=\"https://t.me/coppers_shop\">coppers_shop</a>",
            reply_markup=get_channel_keyboard(),
            disable_web_page_preview=True
        )
        return

    # Уже получал ключ — не даём повторно
    if user_exists(uid):
        await message.answer(
            "🔒 <b>Упс!</b>\n\n"
            "Вы уже получали ключ. Акция действует <b>один раз на человека</b>. "
            "Попробуйте пригласить друзей 😉",
            reply_markup=get_main_keyboard()
        )
        return

    # Проверяем подписку
    is_subscribed = await check_subscription(uid)

    if not is_subscribed:
        # Не подписан — просим подписаться
        await message.answer(
            "👋 <b>Приветствуем вас!</b>\n\n"
            "🎁 Для получения <b>бесплатного ключа</b> подпишитесь на наш канал:\n\n"
            f"📢 <a href=\"https://t.me/coppers_shop\">coppers_shop</a>\n\n"
            "✅ После подписки нажмите кнопку <b>«Проверить подписку»</b> ниже 👇",
            reply_markup=get_channel_keyboard(),
            disable_web_page_preview=True
        )
    else:
        # Подписан — сразу выдаём ключ
        key = get_next_key()
        if key:
            save_user(
                user_id=uid,
                username=message.from_user.username or "N/A",
                first_name=message.from_user.first_name or "N/A",
                key=key
            )
            await message.answer(
                "🎉 <b>Поздравляем!</b>\n\n"
                f"Вот ваш ключ:\n<code>{key}</code>\n\n"
                f"📖 <b>Инструкция по активации:</b>\n\n{INSTRUCTION_TEXT}\n\n"
                "🔒 Этот ключ выдаётся один раз. Удачи! 🚀",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer("😔 Ключи закончились. Попробуйте позже!")


# --- Callback: Проверить подписку ---
@router.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    uid = callback.from_user.id

    if get_keys_count() == 0:
        await callback.message.edit_text(
            "😔 Ключи на данный момент <b>закончились</b>. Следите за обновлениями!",
            reply_markup=None
        )
        return

    is_subscribed = await check_subscription(uid)

    if not is_subscribed:
        await callback.message.edit_text(
            "❌ <b>Подписка не обнаружена!</b>\n\n"
            "Вы ещё не подписались на канал.\n\n"
            f"📢 Подпишитесь: <a href=\"https://t.me/coppers_shop\">coppers_shop</a>\n"
            "Затем нажмите <b>«Проверить подписку»</b> ещё раз.",
            reply_markup=get_channel_keyboard(),
            disable_web_page_preview=True
        )
    elif user_exists(uid):
        await callback.message.edit_text(
            "🔒 <b>Упс!</b>\n\n"
            "Вы уже получали ключ. Акция действует один раз на человека."
        )
    else:
        # Подписан и ключ ещё не получал — выдаём
        key = get_next_key()
        if key:
            save_user(
                user_id=uid,
                username=callback.from_user.username or "N/A",
                first_name=callback.from_user.first_name or "N/A",
                key=key
            )
            await callback.message.edit_text(
                "🎉 <b>Поздравляем!</b>\n\n"
                f"Вот ваш ключ:\n<code>{key}</code>\n\n"
                f"📖 <b>Инструкция по активации:</b>\n\n{INSTRUCTION_TEXT}\n\n"
                "🔒 Этот ключ выдаётся один раз. Удачи! 🚀",
                reply_markup=get_main_keyboard()
            )
        else:
            await callback.message.edit_text(
                "😔 Ключи закончились. Попробуйте позже!"
            )


# --- Админ: добавить ключи (/addkey) ---
@router.message(Command("addkey"))
async def cmd_add_key(message: Message, state: FSMContext):
    """Админ добавляет ключи через текст сообщения, один ключ на строку"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    text = message.text.replace("/addkey", "").strip()
    if not text:
        await message.answer(
            "📝 <b>Введите ключи через строку:</b>\n\n"
            "<code>/addkey\nXXXX-XXXX-XXXX\nYYYY-YYYY-YYYY\nZZZZ-ZZZZ-ZZZZ</code>"
        )
        return

    new_keys = [k.strip() for k in text.split("\n") if k.strip()]
    if not new_keys:
        await message.answer("❌ Ключи не найдены.")
        return

    existing = load_keys()
    existing.extend(new_keys)
    save_keys(existing)

    await message.answer(
        f"✅ Добавлено <b>{len(new_keys)}</b> ключей.\n"
        f"📊 Всего в базе: <b>{len(existing)}</b> ключей."
    )
    logger.info(f"🗝️ Админ {message.from_user.id} добавил {len(new_keys)} ключей")


# --- Админ: статистика (/stats) ---
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    keys_left = get_keys_count()
    stats = get_stats()
    await message.answer(
        f"📊 <b>Статистика бота:</b>\n\n"
        f"🔑 Осталось ключей: <b>{keys_left}</b>\n"
        f"👤 Выдано ключей: <b>{stats['total_users']}</b>"
    )


# --- Админ: удалить конкретный ключ (/delkey) ---
@router.message(Command("delkey"))
async def cmd_del_key(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    key_to_del = message.text.replace("/delkey", "").strip()
    if not key_to_del:
        await message.answer("Использование: <code>/delkey XXXX-XXXX-XXXX</code>")
        return

    keys = load_keys()
    if key_to_del in keys:
        keys.remove(key_to_del)
        save_keys(keys)
        await message.answer(f"✅ Ключ <code>{key_to_del}</code> удалён.")
    else:
        await message.answer(f"❌ Ключ <code>{key_to_del}</code> не найден в базе.")


# --- Админ: список всех ключей (/listkeys) ---
@router.message(Command("listkeys"))
async def cmd_list_keys(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    keys = load_keys()
    if not keys:
        await message.answer("📭 Список ключей пуст.")
        return

    text = "🔑 <b>Доступные ключи:</b>\n\n"
    for i, k in enumerate(keys, 1):
        text += f"{i}. <code>{k}</code>\n"

    # Телеграм ограничивает 4096 символов — разбиваем если много ключей
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(text)


# --- Админ: смена канала (/setchannel) ---
@router.message(Command("setchannel"))
async def cmd_set_channel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    new_channel = message.text.replace("/setchannel", "").strip()
    if not new_channel:
        await message.answer("Использование: <code>/setchannel @username</code>")
        return

    # Обновляем глобальную переменную (будет работать до перезапуска)
    global CHANNEL_USERNAME
    CHANNEL_USERNAME = new_channel if new_channel.startswith("@") else f"@{new_channel}"

    # Сохраняем в файл настроек
    save_config({"channel": CHANNEL_USERNAME})
    await message.answer(f"✅ Канал обновлён: <code>{CHANNEL_USERNAME}</code>")


# ======================== КОНФИГ-ФАЙЛ ========================
CONFIG_FILE = "config.json"

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# Загружаем канал из конфига при старте (если он там есть)
saved_cfg = load_config()
if "channel" in saved_cfg:
    CHANNEL_USERNAME = saved_cfg["channel"]


# ======================== ЗАПУСК ========================
async def main():
    init_db()
    logger.info("🚀 Бот запущен!")
    logger.info(f"📢 Канал для проверки: {CHANNEL_USERNAME}")
    logger.info(f"🔑 Ключей в базе: {get_keys_count()}")

    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())