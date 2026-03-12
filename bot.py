import os
import asyncio
import aiohttp
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
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# --- НАЛАШТУВАННЯ ---
load_dotenv()
API_TOKEN = os.getenv('TELEGRAM_TOKEN')
POLLINATIONS_KEY = os.getenv('POLLINATIONS_KEY')
RENDER_URL = os.getenv('RENDER_EXTERNAL_URL') # Render сам надає цю змінну
PORT = int(os.getenv('PORT', 10000))

# --- БОТ ТА ДИСПЕТЧЕР ---
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

# --- ОБРОБНИКИ КОМАНД ---

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

    # 1. Текстовий аналіз через Pollinations
    analysis_prompt = (
        f"User has {data['soil']} soil, {data['sun']} lighting, and {data['watering']} watering. "
        f"Suggest 5 specific plants for this garden. Output in {lang} language."
    )
    
    analysis = "Не вдалося отримати аналіз."
    try:
        async with aiohttp.ClientSession() as session:
            text_api_url = "https://text.pollinations.ai/"
            payload = {
                "messages": [{"role": "user", "content": analysis_prompt}],
                "model": "openai",
                "key": POLLINATIONS_KEY
            }
            async with session.post(text_api_url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    analysis = await resp.text()
    except Exception as e:
        print(f"Text AI Error: {e}")

    await status_msg.edit_text(TEXTS[lang]['result_text'].format(analysis=analysis))

    # 2. Генерація картинки
    # Очищаємо промпт
    clean_plants = re.sub(r'[*#\-_>\(\)]', ' ', analysis[:300])
    clean_plants = " ".join(clean_plants.split())
    
    img_prompt = f"Professional landscape garden design with these plants: {clean_plants}. Photorealistic, 4k, cinematic lighting."
    safe_prompt = quote(img_prompt)
    
    image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?model=flux&width=1024&height=1024&nologo=true"
    if POLLINATIONS_KEY:
        image_url += f"&key={POLLINATIONS_KEY}"

    try:
        timeout = aiohttp.ClientTimeout(total=70)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(image_url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    photo = BufferedInputFile(image_data, filename="design.jpg")
                    await message.answer_photo(photo=photo, caption="✨ Твій персональний дизайн")
                else:
                    await message.answer("❌ Сервер генерації зображень перевантажений. Спробуйте пізніше.")
    except Exception as e:
        print(f"Image Error: {e}")
        await message.answer("❌ Виникла помилка при генерації фото.")
    
    await state.clear()

# --- ЗАПУСК ---

async def on_startup(bot: Bot):
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/webhook"
        print(f"Setting webhook: {webhook_url}")
        await bot.set_webhook(webhook_url, drop_pending_updates=True)
    else:
        print("Starting in Polling mode...")
        await bot.delete_webhook(drop_pending_updates=True)

def main():
    if RENDER_URL:
        # Режим Webhook для Render
        app = web.Application()
        webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_requests_handler.register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        
        # Реєструємо функцію запуску
        dp.startup.register(on_startup)
        
        web.run_app(app, host="0.0.0.0", port=PORT)
    else:
        # Режим Polling для локального тестування
        async def run_polling():
            await on_startup(bot)
            await dp.start_polling(bot)
        
        asyncio.run(run_polling())

if __name__ == "__main__":
    main()
