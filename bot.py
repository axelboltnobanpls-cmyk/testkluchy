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
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

# ======================== ПУТИ (АБСОЛЮТНЫЕ) ========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(BASE_DIR, "keys.json")
DATABASE_FILE = os.path.join(BASE_DIR, "users.db")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# ======================== НАСТРОЙКИ ========================
BOT_TOKEN = "8375269633:AAElLiElz8WvjdR_OxeCR6mBJZo6kzGK8xM"
CHANNEL_USERNAME = "@growagarden_arferno"
ADMIN_IDS = [7079908197]

INSTRUCTION_TEXT = (
    "📖 <b>Инструкция по активации ключа в Steam:</b>\n\n"
    "1️⃣ Открой клиент <b>Steam</b> и войди в свой аккаунт.\n"
    "2️⃣ Нажми на <b>имя профиля</b> в правом верхнем углу.\n"
    "3️⃣ Выбери <b>«Активация продукта»</b>.\n"
    "4️⃣ Нажми <b>«Далее»</b>, поставь галочку → <b>«Я согласен»</b>.\n"
    "5️⃣ Введи полученный ключ в пустое поле.\n"
    "6️⃣ Нажми <b>«Далее»</b> и следуй инструкциям.\n\n"
    "🎮 После активации игра появится в библиотеке!\n\n"
    "💡 Если ключ не подходит — напиши в канал @growagarden_arferno"
)
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()


# ======================== БАЗА ДАННЫХ ========================
def init_db():
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
    logger.info("✅ База данных OK: " + DATABASE_FILE)


def user_exists(user_id: int) -> bool:
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def save_user(user_id: int, username: str, first_name: str, key: str):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (user_id, username, first_name, received_key) VALUES (?, ?, ?, ?)",
        (user_id, username, first_name, key)
    )
    conn.commit()
    conn.close()


def get_stats() -> dict:
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    conn.close()
    return {"total_users": total}


# ======================== РАБОТА С КЛЮЧАМИ ========================
def ensure_keys_file():
    if not os.path.exists(KEYS_FILE):
        logger.warning(f"⚠️ Файл {KEYS_FILE} не найден! Создаём пустой...")
        save_keys([])


def load_keys() -> list:
    ensure_keys_file()
    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            keys = data.get("keys", [])
            logger.info(f"📦 Загружено ключей: {len(keys)}")
            return keys
    except Exception as e:
        logger.error(f"Ошибка чтения keys.json: {e}")
        save_keys([])
        return []


def save_keys(keys: list):
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump({"keys": keys}, f, ensure_ascii=False, indent=2)
    logger.info(f"💾 Сохранено ключей: {len(keys)}")


def get_next_key() -> str | None:
    keys = load_keys()
    if not keys:
        return None
    key = keys.pop(0)
    save_keys(keys)
    logger.info(f"🔑 ВЫДАН: {key[:8]}... (осталось {len(keys)})")
    return key


def get_keys_count() -> int:
    return len(load_keys())


# ======================== КЛАВИАТУРЫ ========================
def get_channel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Перейти в канал", url="https://t.me/growagarden_arferno")],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")]
    ])


def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Наш канал", url="https://t.me/growagarden_arferno")]
    ])


# ======================== ПРОВЕРКА ПОДПИСКИ ========================
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(
            chat_id=CHANNEL_USERNAME,
            user_id=user_id
        )
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Ошибка проверки подписки для {user_id}: {e}")
        return False


# ======================== ОБРАБОТЧИКИ ========================

# --- /start ---
@router.message(CommandStart())
async def cmd_start(message: Message):
    uid = message.from_user.id
    logger.info(f"👋 /start от {uid} ({message.from_user.first_name})")

    count = get_keys_count()
    logger.info(f"🔑 Ключей в базе: {count}")

    if count == 0:
        await message.answer(
            "👋 <b>Приветствуем!</b>\n\n"
            "😔 Бесплатные ключи на данный момент <b>закончились</b>. "
            "Следите за обновлениями!\n\n"
            "📢 Подпишитесь:\n"
            f"🔗 <a href=\"https://t.me/growagarden_arferno\">growagarden_arferno</a>",
            reply_markup=get_channel_keyboard(),
            disable_web_page_preview=True
        )
        return

    if user_exists(uid):
        await message.answer(
            "🔒 <b>Упс!</b>\n\n"
            "Вы уже получали ключ. Акция — <b>один раз</b> на человека. "
            "Пригласите друзей 😉",
            reply_markup=get_main_keyboard()
        )
        return

    is_subscribed = await check_subscription(uid)

    if not is_subscribed:
        await message.answer(
            "👋 <b>Приветствуем вас!</b>\n\n"
            "🎁 Для получения <b>бесплатного ключа</b> подпишитесь на канал:\n\n"
            f"📢 <a href=\"https://t.me/growagarden_arferno\">growagarden_arferno</a>\n\n"
            "✅ После подписки нажмите кнопку <b>«Проверить подписку»</b> 👇",
            reply_markup=get_channel_keyboard(),
            disable_web_page_preview=True
        )
    else:
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
                "🔒 Ключ одноразовый. Удачи! 🚀",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer("😔 Ключи закончились!")


# --- Callback: Проверить подписку ---
@router.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    logger.info(f"🔍 Проверка подписки: {uid}")

    if get_keys_count() == 0:
        await callback.message.edit_text(
            "😔 Ключи <b>закончились</b>.",
            reply_markup=None
        )
        return

    is_subscribed = await check_subscription(uid)

    if not is_subscribed:
        await callback.message.edit_text(
            "❌ <b>Подписка не обнаружена!</b>\n\n"
            f"📢 Подпишитесь: <a href=\"https://t.me/growagarden_arferno\">growagarden_arferno</a>\n"
            "Затем нажмите <b>«Проверить подписку»</b> ещё раз.",
            reply_markup=get_channel_keyboard(),
            disable_web_page_preview=True
        )
    elif user_exists(uid):
        await callback.message.edit_text(
            "🔒 Уже получали ключ. Акция — один раз."
        )
    else:
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
                "🔒 Ключ одноразовый. Удачи! 🚀",
                reply_markup=get_main_keyboard()
            )
        else:
            await callback.message.edit_text("😔 Ключи закончились!")


# --- Админ: /addkey ---
@router.message(Command("addkey"))
async def cmd_add_key(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав.")
        return
    text = message.text.replace("/addkey", "").strip()
    if not text:
        await message.answer("📝 <code>/addkey\nXXXX-XXXX-XXXX\nYYYY-YYYY-YYYY</code>")
        return
    new_keys = [k.strip() for k in text.split("\n") if k.strip()]
    existing = load_keys()
    existing.extend(new_keys)
    save_keys(existing)
    await message.answer(f"✅ Добавлено <b>{len(new_keys)}</b> ключей.\nВсего: <b>{len(existing)}</b>")


# --- Админ: /stats ---
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав.")
        return
    keys_left = get_keys_count()
    stats = get_stats()
    await message.answer(
        f"📊 <b>Статистика:</b>\n\n"
        f"🔑 Осталось: <b>{keys_left}</b>\n"
        f"👤 Выдано: <b>{stats['total_users']}</b>"
    )


# --- Админ: /delkey ---
@router.message(Command("delkey"))
async def cmd_del_key(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав.")
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
        await message.answer(f"❌ Ключ не найден.")


# --- Админ: /listkeys ---
@router.message(Command("listkeys"))
async def cmd_list_keys(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    keys = load_keys()
    if not keys:
        await message.answer("📭 Ключей нет.")
        return
    text = "🔑 <b>Доступные ключи:</b>\n\n"
    for i, k in enumerate(keys, 1):
        text += f"{i}. <code>{k}</code>\n"
    if len(text) > 4000:
        for part in [text[i:i+4000] for i in range(0, len(text), 4000)]:
            await message.answer(part)
    else:
        await message.answer(text)


# --- Админ: /setchannel ---
@router.message(Command("setchannel"))
async def cmd_set_channel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    new_channel = message.text.replace("/setchannel", "").strip()
    if not new_channel:
        await message.answer("Использование: <code>/setchannel @username</code>")
        return
    global CHANNEL_USERNAME
    CHANNEL_USERNAME = new_channel if new_channel.startswith("@") else f"@{new_channel}"
    save_config({"channel": CHANNEL_USERNAME})
    await message.answer(f"✅ Канал: <code>{CHANNEL_USERNAME}</code>")


# ======================== КОНФИГ ========================
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


saved_cfg = load_config()
if "channel" in saved_cfg:
    CHANNEL_USERNAME = saved_cfg["channel"]


# ======================== ЗАПУСК ========================
async def main():
    init_db()
    ensure_keys_file()
    logger.info("=" * 50)
    logger.info("🚀 Бот запущен!")
    logger.info(f"📢 Канал: {CHANNEL_USERNAME}")
    logger.info(f"🔑 Ключей: {get_keys_count()}")
    logger.info(f"🗄️ keys.json: {KEYS_FILE}")
    logger.info(f"🗄️ users.db: {DATABASE_FILE}")
    logger.info("=" * 50)
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
