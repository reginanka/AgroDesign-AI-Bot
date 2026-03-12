import asyncio
import aiohttp
from aiohttp import web
import os
import re
from urllib.parse import quote
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import BufferedInputFile

# Завантажуємо секрети
load_dotenv()
API_TOKEN = os.getenv('TELEGRAM_TOKEN')
POLLINATIONS_KEY = os.getenv('POLLINATIONS_KEY')

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class AgroForm(StatesGroup):
    soil = State()
    sun = State()
    watering = State()
    photo = State()

TEXTS = {
    'uk': {
        'start': "🌿 Вітаю в AgroDesign AI! Який у вас ґрунт?",
        'soil_opts': ["Пісок", "Чорнозем", "Глина", "Супісь"],
        'sun_q': "Яке освітлення?",
        'sun_opts': ["Сонце", "Напівтінь", "Тінь"],
        'water_q': "Як щодо поливу?",
        'water_opts': ["Автоматичний", "Вручну", "Рідко"],
        'photo_q': "Надішліть фото ділянки 📸",
        'wait': "⏳ ШІ аналізує дані та підбирає рослини...",
        'result_text': "✅ Рекомендовані рослини:\n\n{analysis}\n\n🎨 Малюю дизайн...",
    },
    'en': {
        'start': "🌿 Welcome to AgroDesign AI! What's your soil type?",
        'soil_opts': ["Sand", "Black soil", "Clay", "Loam"],
        'sun_q': "Lighting conditions?",
        'sun_opts': ["Full Sun", "Partial Shade", "Full Shade"],
        'water_q': "Watering?",
        'water_opts': ["Automatic", "Manual", "Rarely"],
        'photo_q': "Send a photo of your plot 📸",
        'wait': "⏳ AI is analyzing data and choosing plants...",
        'result_text': "✅ Recommended plants:\n\n{analysis}\n\n🎨 Rendering design...",
    }
}

def get_lang(message: types.Message):
    return 'uk' if message.from_user.language_code == 'uk' else 'en'

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    lang = get_lang(message)
    builder = ReplyKeyboardBuilder()
    for opt in TEXTS[lang]['soil_opts']:
        builder.button(text=opt)
    await message.answer(TEXTS[lang]['start'], reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(AgroForm.soil)

@dp.message(AgroForm.soil)
async def process_soil(message: types.Message, state: FSMContext):
    lang = get_lang(message)
    await state.update_data(soil=message.text)
    builder = ReplyKeyboardBuilder()
    for opt in TEXTS[lang]['sun_opts']:
        builder.button(text=opt)
    await message.answer(TEXTS[lang]['sun_q'], reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(AgroForm.sun)

@dp.message(AgroForm.sun)
async def process_sun(message: types.Message, state: FSMContext):
    lang = get_lang(message)
    await state.update_data(sun=message.text)
    builder = ReplyKeyboardBuilder()
    for opt in TEXTS[lang]['water_opts']:
        builder.button(text=opt)
    await message.answer(TEXTS[lang]['water_q'], reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(AgroForm.watering)

@dp.message(AgroForm.watering)
async def process_water(message: types.Message, state: FSMContext):
    lang = get_lang(message)
    await state.update_data(watering=message.text)
    await message.answer(TEXTS[lang]['photo_q'], reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(AgroForm.photo)

@dp.message(AgroForm.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    lang = get_lang(message)
    data = await state.get_data()
    status_msg = await message.answer(TEXTS[lang]['wait'])

    # 1. Текстовий аналіз через Pollinations (отримуємо назви рослин)
    analysis_prompt = (
        f"User has {data['soil']} soil, {data['sun']} lighting, and {data['watering']} watering. "
        f"Suggest 5 specific plants for this garden. Output in {lang} language."
    )
    
    async with aiohttp.ClientSession() as session:
        text_api_url = "https://text.pollinations.ai/"
        payload = {
            "messages": [{"role": "user", "content": analysis_prompt}],
            "model": "openai",
            "key": POLLINATIONS_KEY
        }
        async with session.post(text_api_url, json=payload) as resp:
            analysis = await resp.text()

    # Оновлюємо статусне повідомлення з текстом від ШІ
    await status_msg.edit_text(TEXTS[lang]['result_text'].format(analysis=analysis))

    # 2. Генерація картинки
    # Очищаємо текст від маркдауну та зайвих символів для стабільної роботи Image API
    clean_plants = re.sub(r'[*#\-_>\(\)]', '', analysis[:300])
    # Видаляємо зайві пробіли та переноси рядків
    clean_plants = " ".join(clean_plants.split())
    
    img_prompt = f"Beautiful landscape garden design, style of professional gardening magazine. Plants: {clean_plants}. High quality, photorealistic, cinematic lighting."
    safe_prompt = quote(img_prompt)
    
    # Додаємо ключ тільки якщо він є
    image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?model=flux&width=1024&height=1024&nologo=true"
    if POLLINATIONS_KEY:
        image_url += f"&key={POLLINATIONS_KEY}"

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(image_url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    photo = BufferedInputFile(image_data, filename="design.jpg")
                    await message.answer_photo(photo=photo, caption="✨ Твій персональний дизайн")
                else:
                    await message.answer(f"❌ Не вдалося згенерувати фото (Помилка {response.status}). Але ось ваші рекомендації: {analysis[:500]}...")
    except Exception as e:
        print(f"Error fetching image: {e}")
        await message.answer("❌ Виникла помилка при завантаженні зображення.")
    
    await state.clear()

# Простий веб-сервер для Render (Free Tier Web Service)
# Він потрібен, щоб Render бачив, що додаток "живий" через відкритий порт
async def handle_health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render передає порт через змінну оточення PORT
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server started on port {port}")

async def main():
    # Видаляємо вебхук (якщо був) та очищуємо чергу повідомлень для уникнення конфліктів
    await bot.delete_webhook(drop_pending_updates=True)
    # Запускаємо веб-сервер та бота одночасно
    await asyncio.gather(
        start_web_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped")
    
