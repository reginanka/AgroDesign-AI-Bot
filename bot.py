import os
import asyncio
import aiohttp
import re
import random
from urllib.parse import quote
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import Message, BufferedInputFile
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# --- НАЛАШТУВАННЯ ---
load_dotenv()
API_TOKEN = os.getenv('TELEGRAM_TOKEN')
POLLINATIONS_KEY = os.getenv('POLLINATIONS_KEY')
RENDER_URL = os.getenv('RENDER_EXTERNAL_URL')
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
    chat = State()

TEXTS = {
    'uk': {
        'start': "🌿 Вітаю в AgroDesign AI! Який у вас ґрунт?",
        'soil_opts': ["Пісок", "Чорнозем", "Глина", "Супісь"],
        'sun_q': "Яке освітлення на ділянці?",
        'sun_opts': ["Сонце", "Напівтінь", "Тінь"],
        'water_q': "Який плануєте полив?",
        'water_opts': ["Автоматичний", "Вручну", "Рідко"],
        'region_q': "Вкажіть ваш регіон (напр. Київська обл.) 🌍",
        'photo_q': "Надішліть фото під розробку 📸",
        'wait': "⏳ Складаю ідеальний план саду...",
        'result_text': "✅ <b>Рекомендовані рослини:</b>\n\n{analysis}",
        'generating_img': "🎨 Малюю ваш дизайн, зачекайте кілька секунд...",
        'img_error': "❌ Картинка малюється занадто довго. Спробуйте запитати бота ще раз у чаті!"
    },
    'en': {
        'start': "🌿 Welcome! What's your soil?",
        'soil_opts': ["Sand", "Black soil", "Clay", "Loam"],
        'sun_q': "Sunlight?",
        'sun_opts': ["Full Sun", "Partial Shade", "Shade"],
        'water_q': "Watering?",
        'water_opts': ["Auto", "Manual", "Rarely"],
        'region_q': "Region? 🌍",
        'photo_q': "Send plot photo 📸",
        'wait': "⏳ Analyzing...",
        'result_text': "✅ <b>Plants:</b>\n\n{analysis}",
        'generating_img': "🎨 Rendering...",
        'img_error': "❌ Image error."
    }
}

def get_lang(message: Message):
    return 'uk' if message.from_user.language_code == 'uk' else 'en'

# --- ОБРОБНИКИ FLOW ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    lang = get_lang(message)
    builder = ReplyKeyboardBuilder()
    for opt in TEXTS[lang]['soil_opts']: builder.button(text=opt)
    await message.answer(TEXTS[lang]['start'], reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(AgroForm.soil)

@dp.message(AgroForm.soil)
async def process_soil(message: Message, state: FSMContext):
    lang = get_lang(message)
    await state.update_data(soil=message.text)
    builder = ReplyKeyboardBuilder()
    for opt in TEXTS[lang]['sun_opts']: builder.button(text=opt)
    await message.answer(TEXTS[lang]['sun_q'], reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(AgroForm.sun)

@dp.message(AgroForm.sun)
async def process_sun(message: Message, state: FSMContext):
    lang = get_lang(message)
    await state.update_data(sun=message.text)
    builder = ReplyKeyboardBuilder()
    for opt in TEXTS[lang]['water_opts']: builder.button(text=opt)
    await message.answer(TEXTS[lang]['water_q'], reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(AgroForm.watering)

@dp.message(AgroForm.watering)
async def process_water(message: Message, state: FSMContext):
    lang = get_lang(message)
    await state.update_data(watering=message.text)
    await message.answer(TEXTS[lang]['region_q'], reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(AgroForm.region)

@dp.message(AgroForm.region)
async def process_region(message: Message, state: FSMContext):
    lang = get_lang(message)
    await state.update_data(region=message.text)
    await message.answer(TEXTS[lang]['photo_q'])
    await state.set_state(AgroForm.photo)

@dp.message(AgroForm.photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    lang = get_lang(message)
    data = await state.get_data()
    status_msg = await message.answer(TEXTS[lang]['wait'])

    # 1. Текстовий аналіз (Gemini через Новий API)
    prompt = (
        f"Ти - професійний ландшафтний дизайнер. Регіон: {data.get('region')}. "
        f"Ґрунт {data.get('soil')}, світло {data.get('sun')}, полив {data.get('watering')}. "
        f"Дай 5 рослин для відкритого ґрунту України (-20°C). Кожній дай опис. "
        f"Мова: українська. Формат: список •. В кінці: PROMPT: та 5 слів англійською для саду."
    )
    
    analysis_text = "Вибачте, сервіс зайнятий."
    img_kw = "beautiful garden"

    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"} if POLLINATIONS_KEY else {}
            payload = {"model": "openai", "messages": [{"role": "user", "content": prompt}]}
            async with session.post("https://text.pollinations.ai/v1/chat/completions", json=payload, headers=headers) as r:
                if r.status == 200:
                    res = (await r.json())['choices'][0]['message']['content']
                    if "PROMPT:" in res:
                        parts = res.split("PROMPT:")
                        analysis_text, img_kw = parts[0].strip(), parts[1].strip()
                    else:
                        analysis_text = res.strip()
    except: pass

    await status_msg.edit_text(TEXTS[lang]['result_text'].format(analysis=analysis_text), parse_mode="HTML")
    await state.update_data(last_analysis=analysis_text)
    
    # 2. Швидке малювання (метод Z-Image Turbo)
    await message.answer(TEXTS[lang]['generating_img'])
    clean_kw = re.sub(r'[^a-zA-Z0-9\s]', '', img_kw)
    seed = random.randint(1, 99999)
    # Використовуємо турбо модель для миттєвого результату
    img_url = f"https://image.pollinations.ai/prompt/landscape%20garden%20design%20{quote(clean_kw)}?width=1024&height=1024&nologo=true&seed={seed}&model=turbo"
    
    try:
        # Надсилаємо як посилання, щоб Телеграм сам завантажив - це найшвидше
        await message.answer_photo(photo=img_url, caption="✨ Твій персональний садовий дизайн")
    except:
        await message.answer(TEXTS[lang]['img_error'])

    await message.answer("💬 Ви можете написати мені, щоб змінити щось у проекті або запитати про рослини!")
    await state.set_state(AgroForm.chat)

@dp.message(AgroForm.chat)
async def chat_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    prompt = (
        f"Ти архітектор. Умови: {data.get('region')}, {data.get('soil')}. "
        f"Минуле: {data.get('last_analysis')}. Питання: {message.text}. "
        f"Відповідай коротко українською."
    )
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"} if POLLINATIONS_KEY else {}
            payload = {"model": "openai", "messages": [{"role": "user", "content": prompt}]}
            async with session.post("https://text.pollinations.ai/v1/chat/completions", json=payload, headers=headers) as r:
                ans = (await r.json())['choices'][0]['message']['content']
                await message.answer(ans, parse_mode="HTML")
                await state.update_data(last_analysis=ans)
    except: await message.answer("Сервіс тимчасово недоступний для чату.")

# --- СТАРТ ---

async def on_startup(bot: Bot):
    if RENDER_URL:
        await bot.set_webhook(f"{RENDER_URL}/webhook", drop_pending_updates=True)
    else:
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
        
        print(f"Starting Webhook on port {PORT}")
        web.run_app(app, host="0.0.0.0", port=PORT)
    else:
        # Режим Polling
        async def run_poll():
            await on_startup(bot)
            await dp.start_polling(bot)
        print("Starting Polling...")
        asyncio.run(run_poll())

if __name__ == "__main__":
    main()
