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
    region = State()
    photo = State()

TEXTS = {
    'uk': {
        'start': "🌿 Вітаю в AgroDesign AI! Який у вас ґрунт?",
        'soil_opts': ["Пісок", "Чорнозем", "Глина", "Супісь"],
        'sun_q': "Яке освітлення?",
        'sun_opts': ["Сонце", "Напівтінь", "Тінь"],
        'water_q': "Як щодо поливу?",
        'water_opts': ["Автоматичний", "Вручну", "Рідко"],
        'region_q': "Вкажіть ваш регіон або країну (наприклад: Київська обл., Україна) 🌍",
        'photo_q': "Надішліть фото ділянки 📸",
        'wait': "⏳ ШІ аналізує дані та підбирає реальні рослини для вашого клімату...",
        'result_text': "✅ <b>Рекомендовані рослини:</b>\n\n{analysis}\n\n🎨 Малюю дизайн...",
    },
    'en': {
        'start': "🌿 Welcome to AgroDesign AI! What's your soil type?",
        'soil_opts': ["Sand", "Black soil", "Clay", "Loam"],
        'sun_q': "Lighting conditions?",
        'sun_opts': ["Full Sun", "Partial Shade", "Full Shade"],
        'water_q': "Watering?",
        'water_opts': ["Automatic", "Manual", "Rarely"],
        'region_q': "Specify your region or country (e.g., London, UK) 🌍",
        'photo_q': "Send a photo of your plot 📸",
        'wait': "⏳ AI is choosing real plants for your climate...",
        'result_text': "✅ <b>Recommended plants:</b>\n\n{analysis}\n\n🎨 Rendering design...",
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
    await message.answer(TEXTS[lang]['region_q'], reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(AgroForm.region)

@dp.message(AgroForm.region)
async def process_region(message: types.Message, state: FSMContext):
    lang = get_lang(message)
    await state.update_data(region=message.text)
    await message.answer(TEXTS[lang]['photo_q'])
    await state.set_state(AgroForm.photo)

@dp.message(AgroForm.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    lang = get_lang(message)
    data = await state.get_data()
    status_msg = await message.answer(TEXTS[lang]['wait'])

    # 1. Текстовий аналіз через Pollinations (Екстремально надійний метод)
    analysis_prompt = (
        f"Professional botanist advice for {data.get('region', 'Ukraine')}. "
        f"Soil: {data.get('soil')}, Sun: {data.get('sun')}, Water: {data.get('watering')}. "
        f"List 5 REAL plants in UKRAINIAN language only. Professional style. "
        f"End with PROMPT: and 3-5 English garden keywords."
    )
    
    analysis_text = "Не вдалося отримати аналіз. Можливо, сервіс перевантажений. Спробуйте ще раз через хвилину."
    image_keywords = "beautiful garden design"
    
    # Використовуємо найнадійніші моделі за твоїм монітором
    models_to_try = [
        "qwen-character", # №1 на моніторі (100% успіх, 0.8с)
        "gemini-fast",   # №2 на моніторі
        "openai"         # Запасний варіант
    ]
    
    async with aiohttp.ClientSession() as session:
        for model in models_to_try:
            try:
                print(f"Trying model: {model}...")
                # Використовуємо простий GET запит, він працює навіть коли POST "лежить"
                encoded_prompt = quote(analysis_prompt)
                text_url = f"https://text.pollinations.ai/{encoded_prompt}?model={model}&seed=42"
                
                async with session.get(text_url, timeout=20) as resp:
                    if resp.status == 200:
                        full_resp = await resp.text()
                        if len(full_resp) > 10: # Перевірка чи відповідь не пуста
                            if "PROMPT:" in full_resp:
                                parts = full_resp.split("PROMPT:")
                                analysis_text = parts[0].replace('*', '').strip()
                                image_keywords = parts[1].strip()
                            else:
                                analysis_text = full_resp.replace('*', '').strip()
                            print(f"SUCCESS with {model}!")
                            break
                    else:
                        print(f"Model {model} failed with status {resp.status}")
            except Exception as e:
                print(f"Model {model} error: {e}")
                continue

    # Відправляємо результат
    try:
        await status_msg.edit_text(TEXTS[lang]['result_text'].format(analysis=analysis_text), parse_mode="HTML")
    except Exception:
        # Якщо HTML битий (наприклад, ШІ вставив криві теги), шлемо без форматування
        clean_text = re.sub(r'<[^>]+>', '', analysis_text)
        await status_msg.edit_text(TEXTS[lang]['result_text'].format(analysis=clean_text))

    # 2. Генерація картинки (із спробами)
    img_prompt = f"Professional landscape garden design, {image_keywords}, photorealistic, 4k."
    safe_prompt = quote(img_prompt)
    
    # Використовуємо більш стабільну модель за замовчуванням
    image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&nologo=true"
    if POLLINATIONS_KEY:
        image_url += f"&key={POLLINATIONS_KEY}"

    for attempt in range(2): # 2 спроби
        try:
            await bot.send_chat_action(message.chat.id, "upload_photo")
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40)) as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        photo = BufferedInputFile(image_data, filename="design.jpg")
                        await message.answer_photo(photo=photo, caption="✨ Твій персональний дизайн")
                        await state.clear()
                        return # Успіх!
                    else:
                        print(f"Attempt {attempt+1} failed with status {response.status}")
        except Exception as e:
            print(f"Attempt {attempt+1} error: {e}")
        
        if attempt == 0:
            # Якщо перша спроба не вдалася, пробуємо простіший промпт
            image_url = f"https://image.pollinations.ai/prompt/beautiful%20garden%20landscape%20design?width=1024&height=1024&nologo=true"
            await asyncio.sleep(2) # Пауза перед другою спробою

    await message.answer("❌ На жаль, сервіс малювання зараз дуже зайнятий. Але ваші рекомендації збережено вище! ☝️")
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
