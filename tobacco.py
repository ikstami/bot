import logging
import os
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.executor import start_polling
from fuzzywuzzy import process
import psycopg2

# Базовая настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Подключение к базе данных
DATABASE_URL = os.getenv("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# Создание таблицы, если её нет
cursor.execute("""
    CREATE TABLE IF NOT EXISTS tobaccos (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE,
        taste FLOAT,
        molasses FLOAT,
        smoke_time FLOAT,
        heat_resistance FLOAT,
        comment TEXT
    )
""")
conn.commit()

# Фейковый веб-сервер для Render
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running!"

# Состояния для FSM
class TobaccoForm(StatesGroup):
    name = State()
    taste = State()
    molasses = State()
    smoke_time = State()
    heat_resistance = State()
    comment = State()

# Главное меню
main_menu = ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.add(KeyboardButton("Добавить табак"))
main_menu.add(KeyboardButton("Поиск табака"))
main_menu.add(KeyboardButton("Редактировать табак"))
main_menu.add(KeyboardButton("Удалить табак"))

# Обработчик команды /start
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    await message.answer("Привет! Этот бот поможет тебе хранить информацию о табаках.", reply_markup=main_menu)

# Обработчик кнопки 'Добавить табак'
@dp.message_handler(lambda message: message.text == "Добавить табак")
async def add_tobacco(message: types.Message):
    await TobaccoForm.name.set()
    await message.answer("Введите название табака:")

# Поиск табака
@dp.message_handler(lambda message: message.text == "Поиск табака")
async def search_tobacco(message: types.Message):
    await message.answer("Введите название табака для поиска:")

@dp.message_handler()
async def process_search(message: types.Message):
    cursor.execute("SELECT name FROM tobaccos")
    tobaccos = [row[0] for row in cursor.fetchall()]
    results = process.extract(message.text, tobaccos, limit=5)

    if results:
        keyboard = InlineKeyboardMarkup()
        for result in results:
            if result[1] > 60:  # Порог схожести
                keyboard.add(InlineKeyboardButton(result[0], callback_data=f"select_{result[0]}"))
        if keyboard.inline_keyboard:
            await message.answer("Выберите табак:", reply_markup=keyboard)
        else:
            await message.answer("Табак не найден.")
    else:
        await message.answer("Табак не найден.")

@dp.callback_query_handler(lambda c: c.data.startswith("select_"))
async def show_tobacco(callback_query: types.CallbackQuery):
    tobacco_name = callback_query.data.split("_", 1)[1]
    cursor.execute("SELECT * FROM tobaccos WHERE name = %s", (tobacco_name,))
    tobacco = cursor.fetchone()
    if tobacco:
        response = (f"Название: {tobacco[1]}\nВкус: {tobacco[2]}\nМелассность: {tobacco[3]}\n"
                    f"Время курения: {tobacco[4]}\nЖаростойкость: {tobacco[5]}\nКомментарий: {tobacco[6]}")

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("Редактировать", callback_data=f"edit_{tobacco[1]}"))
        keyboard.add(InlineKeyboardButton("Удалить", callback_data=f"delete_{tobacco[1]}"))

        await bot.send_message(callback_query.from_user.id, response, reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("delete_"))
async def delete_tobacco(callback_query: types.CallbackQuery):
    tobacco_name = callback_query.data.split("_", 1)[1]
    cursor.execute("DELETE FROM tobaccos WHERE name = %s", (tobacco_name,))
    conn.commit()
    await bot.send_message(callback_query.from_user.id, "Табак удален.")

if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000))), daemon=True).start()
    start_polling(dp, skip_updates=True)
