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
from aiogram.types import Message, BufferedInputFile, InputMediaPhoto
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web  # КРИТИЧНО: Не видаляти!

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
        'wait': "⏳ Складаю ідеальний план саду та малюю кілька варіантів дизайну...",
        'result_text': "✅ <b>Рекомендовані рослини:</b>\n\n{analysis}",
        'generating_img': "🎨 Працюю над візуалізацією (модель Z-Image Turbo)...",
        'img_error': "❌ Сервіс малювання перевантажений. Але ваші поради готові! ☝️"
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
        'wait': "⏳ Designing your garden...",
        'result_text': "✅ <b>Plants:</b>\n\n{analysis}",
        'generating_img': "🎨 Generating visuals...",
        'img_error': "❌ Image service busy."
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

    # 1. Текстовий аналіз (Gemini/OpenAI)
    prompt = (
        f"Ти професійний ландшафтний архітектор. Регіон: {data.get('region')}. "
        f"Ґрунт {data.get('soil')}, світло {data.get('sun')}, полив {data.get('watering')}. "
        f"Дай 5 рослин для відкритого ґрунту України. Жодної екзотики. "
        f"Для кожної дай назву <b> та поясни чому (1 речення). "
        f"Мова: українська. Формат: список •. В кінці: PROMPT: та 5 слів англійською."
    )
    
    analysis_text = "Вибачте, сервіс аналізу зараз перевантажений."
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
    except Exception as e:
        print(f"API Error: {e}")

    await status_msg.edit_text(TEXTS[lang]['result_text'].format(analysis=analysis_text), parse_mode="HTML")
    await state.update_data(last_analysis=analysis_text)
    
    # 2. Малювання 5-ти варіантів (Z-Image Turbo)
    await message.answer(TEXTS[lang]['generating_img'])
    clean_kw = re.sub(r'[^a-zA-Z0-9\s]', '', img_kw)
    
    media_group = []
    # Генеруємо 4-5 різних варіантів з різними сідами
    for i in range(4):
        seed = random.randint(1, 1000000)
        # Використовуємо саме модель TURBO (Z-Image)
        url = f"https://image.pollinations.ai/prompt/professional%20landscape%20garden%20design%20{quote(clean_kw)}?width=1024&height=1024&nologo=true&seed={seed}&model=turbo"
        media_group.append(InputMediaPhoto(media=url))

    try:
        await bot.send_media_group(chat_id=message.chat.id, media=media_group)
    except Exception as e:
        print(f"Media Group Error: {e}")
        # Одиночна спроба як запасний варіант
        try:
            solo_url = f"https://image.pollinations.ai/prompt/garden%20design?model=turbo&seed=42"
            await message.answer_photo(photo=solo_url, caption="🎨 Ваш дизайн")
        except:
            await message.answer(TEXTS[lang]['img_error'])

    await message.answer("💬 Ви можете написати мені, щоб змінити проект або запитати про ці рослини!")
    await state.set_state(AgroForm.chat)

@dp.message(AgroForm.chat)
async def chat_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    prompt = (
        f"Ти архітектор. Сад: {data.get('region')}, {data.get('soil')}. "
        f"Поради: {data.get('last_analysis')}. Запит: {message.text}. "
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
    except:
        await message.answer("Сервіс тимчасово недоступний для чату.")

# --- СТАРТ ---

async def on_startup(bot_instance: Bot):
    if RENDER_URL:
        await bot_instance.set_webhook(f"{RENDER_URL}/webhook", drop_pending_updates=True)
        print(f"Webhook set to {RENDER_URL}/webhook")
    else:
        await bot_instance.delete_webhook(drop_pending_updates=True)
        print("Polling mode started")

def main():
    if RENDER_URL:
        app = web.Application()
        # Важливо: використовуємо SimpleRequestHandler для обробки вебхуків
        handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        handler.register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        
        dp.startup.register(on_startup)
        
        print(f"Starting Web Application on port {PORT}")
        web.run_app(app, host="0.0.0.0", port=PORT)
    else:
        async def run():
            await on_startup(bot)
            await dp.start_polling(bot)
        asyncio.run(run())

if __name__ == "__main__":
    main()
