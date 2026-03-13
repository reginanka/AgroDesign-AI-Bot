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
from aiogram.types import BufferedInputFile, Message
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
    chat = State() # Режим діалогу

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
        'generating_img': "🎨 Створюю візуалізацію вашого майбутнього саду...",
        'img_error': "❌ Сервіс малювання тимчасово перевантажений, але ми можемо обговорити рослини в чаті!"
    },
    'en': {
        'start': "🌿 Welcome to AgroDesign AI! What's your soil type?",
        'soil_opts': ["Sand", "Black soil", "Clay", "Loam"],
        'sun_q': "Lighting?",
        'sun_opts': ["Full Sun", "Partial Shade", "Full Shade"],
        'water_q': "Watering?",
        'water_opts': ["Automatic", "Manual", "Rarely"],
        'region_q': "Specify your region or country 🌍",
        'photo_q': "Send a photo of your plot 📸",
        'wait': "⏳ AI is choosing real plants for your climate...",
        'result_text': "✅ <b>Recommended plants:</b>\n\n{analysis}\n\n🎨 Rendering design...",
        'generating_img': "🎨 Generating garden visualization...",
        'img_error': "❌ Image service is busy, but we can chat about the plants!"
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

    # 1. Текстовий аналіз (Клімато-орієнтований)
    analysis_prompt = (
        f"Ти — експерт ландшафтний архітектор. Регіон: {data.get('region')}. "
        f"Умови: ґрунт {data.get('soil')}, світло {data.get('sun')}, полив {data.get('watering')}. "
        f"Запропонуй 5 рослин, які точно витримують морози до -20°C (Україна). "
        f"Жодних тропічних рослин чи агав. Для кожної дай назву <b> та поясни чому (1 речення). "
        f"Мова: УКРАЇНСЬКА. Формат: список •. В кінці: PROMPT: та 5 англійських слів."
    )
    
    analysis_text = "Вибачте, сервіс аналізу зараз перевантажений."
    image_keywords = "professional garden design"
    
    async with aiohttp.ClientSession() as session:
        try:
            headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"} if POLLINATIONS_KEY else {}
            payload = {"model": "openai", "messages": [{"role": "user", "content": analysis_prompt}], "temperature": 0.3}
            async with session.post("https://text.pollinations.ai/v1/chat/completions", json=payload, headers=headers, timeout=40) as resp:
                if resp.status == 200:
                    json_resp = await resp.json()
                    full_resp = json_resp['choices'][0]['message']['content']
                    if "PROMPT:" in full_resp:
                        parts = full_resp.split("PROMPT:")
                        analysis_text, image_keywords = parts[0].strip(), parts[1].strip()
                    else:
                        analysis_text = full_resp.strip()
        except Exception as e: print(f"Speech error: {e}")

    await status_msg.edit_text(TEXTS[lang]['result_text'].format(analysis=analysis_text), parse_mode="HTML")
    await state.update_data(last_analysis=analysis_text)
    await message.answer("💬 Ви можете написати мені, щоб змінити рослини або щось уточнити!")

    # 2. Картинка (Fallback моделі)
    image_sent = False
    for model in ["flux", "turbo", "any-dark"]:
        if image_sent: break
        try:
            clean_kw = re.sub(r'[^a-zA-Z0-9\s,]', '', image_keywords)
            url = f"https://image.pollinations.ai/prompt/landscape%20garden%20{quote(clean_kw)}?model={model}&width=1024&height=1024&nologo=true"
            async with session.get(url, timeout=40) as r:
                if r.status == 200:
                    photo = BufferedInputFile(await r.read(), filename="design.jpg")
                    await message.answer_photo(photo=photo, caption="🎨 Ваш дизайн")
                    image_sent = True
        except: continue

    if not image_sent: await message.answer(TEXTS[lang]['img_error'])
    await state.set_state(AgroForm.chat)

@dp.message(AgroForm.chat)
async def chat_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    prompt = (
        f"Ти архітектор. Сад: {data.get('region')}, {data.get('soil')}. "
        f"Минуле: {data.get('last_analysis')}. Запит: {message.text}. "
        f"Відповідай коротко українською."
    )
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"} if POLLINATIONS_KEY else {}
        try:
            payload = {"model": "openai", "messages": [{"role": "user", "content": prompt}]}
            async with session.post("https://text.pollinations.ai/v1/chat/completions", json=payload, headers=headers) as r:
                if r.status == 200:
                    ans = (await r.json())['choices'][0]['message']['content']
                    await message.answer(ans, parse_mode="HTML")
                    await state.update_data(last_analysis=ans)
        except: await message.answer("Помилка зв'язку.")

# --- ЗАПУСК ---

async def on_startup(bot: Bot):
    if RENDER_URL:
        await bot.set_webhook(f"{RENDER_URL}/webhook", drop_pending_updates=True)
    else:
        await bot.delete_webhook(drop_pending_updates=True)

def main():
    if RENDER_URL:
        app = web.Application()
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        dp.startup.register(on_startup)
        web.run_app(app, host="0.0.0.0", port=PORT)
    else:
        async def run():
            await on_startup(bot)
            await dp.start_polling(bot)
        asyncio.run(run())

if __name__ == "__main__":
    main()
