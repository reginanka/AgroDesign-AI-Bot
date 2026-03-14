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
    model = State()

AVAILABLE_MODELS = {
    "🎨 Z-Image (Найшвидша)": "zimage",
    "🚀 Turbo Speed": "turbo",
    "⚡ FLUX (Якість)": "flux",
    "✨ Sana 4K": "sana"
}

TEXTS = {
    'uk': {
        'start': "🌿 Вітаю в AgroDesign AI! Який у вас ґрунт?",
        'soil_opts': ["Пісок", "Чорнозем", "Глина", "Супісь"],
        'sun_q': "Яке освітлення на ділянці?",
        'sun_opts': ["Сонце", "Напівтінь", "Тінь"],
        'water_q': "Який плануєте полив?",
        'water_opts': ["Автоматичний", "Вручну", "Рідко"],
        'region_q': "Вкажіть ваш регіон (напр. Київська обл.) 🌍",
        'photo_q': "Надішліть фото ділянки 📸",
        'wait': "⏳ Професійний аналіз даних (використовую ваш API ключ)...",
        'result_text': "✅ <b>Рекомендовані рослини для України:</b>\n\n{analysis}",
        'generating_img': "🎨 Малюю ваш дизайн у високій якості (Z-Image Turbo)...",
        'img_error': "❌ Сервіс малювання тимчасово недоступний. Спробуйте пізніше!"
    }
}

def get_lang(message: Message):
    return 'uk'

# --- ОБРОБНИКИ FLOW ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    # Отримуємо поточну модель перед очищенням
    data = await state.get_data()
    current_model = data.get('model', 'zimage')
    
    # Очищаємо дані форми, але зберігаємо модель
    await state.clear()
    await state.update_data(model=current_model)
    
    builder = ReplyKeyboardBuilder()
    builder.button(text="🌱 Почати дизайн")
    builder.button(text="🎨 Обрати модель")
    builder.adjust(2)
    
    await message.answer(
        "🌿 Вітаю в AgroDesign AI!\n\n"
        "Я допоможу створити професійний дизайн вашого саду.\n"
        "Обрана модель: <b>" + [n for n, m in AVAILABLE_MODELS.items() if m == current_model][0] + "</b>",
        reply_markup=builder.as_markup(resize_keyboard=True),
        parse_mode="HTML"
    )

@dp.message(F.text == "🌱 Почати дизайн")
async def start_design(message: Message, state: FSMContext):
    builder = ReplyKeyboardBuilder()
    for opt in TEXTS['uk']['soil_opts']: builder.button(text=opt)
    await message.answer(TEXTS['uk']['start'], reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(AgroForm.soil)

@dp.message(F.text == "🎨 Обрати модель")
@dp.message(Command("model"))
async def cmd_model(message: Message):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for name, m_id in AVAILABLE_MODELS.items():
        builder.button(text=name, callback_data=f"set_model:{m_id}")
    builder.adjust(2)
    await message.answer("Оберіть модель для генерації зображень:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("set_model:"))
async def process_model_select(callback: types.CallbackQuery, state: FSMContext):
    model_id = callback.data.split(":")[1]
    await state.update_data(model=model_id)
    model_name = [n for n, m in AVAILABLE_MODELS.items() if m == model_id][0]
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Почати дизайн з цією моделлю", callback_data="start_flow")
    
    await callback.answer(f"Вибрано: {model_name}")
    await callback.message.edit_text(
        f"✅ Тепер я буду малювати сади через: <b>{model_name}</b>\n\nТепер ви можете почати створення дизайну!",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "start_flow")
async def start_flow_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    builder = ReplyKeyboardBuilder()
    for opt in TEXTS['uk']['soil_opts']: builder.button(text=opt)
    await callback.message.answer(TEXTS['uk']['start'], reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(AgroForm.soil)

@dp.message(AgroForm.soil)
async def process_soil(message: Message, state: FSMContext):
    await state.update_data(soil=message.text)
    builder = ReplyKeyboardBuilder()
    for opt in TEXTS['uk']['sun_opts']: builder.button(text=opt)
    await message.answer(TEXTS['uk']['sun_q'], reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(AgroForm.sun)

@dp.message(AgroForm.sun)
async def process_sun(message: Message, state: FSMContext):
    await state.update_data(sun=message.text)
    builder = ReplyKeyboardBuilder()
    for opt in TEXTS['uk']['water_opts']: builder.button(text=opt)
    await message.answer(TEXTS['uk']['water_q'], reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(AgroForm.watering)

@dp.message(AgroForm.watering)
async def process_water(message: Message, state: FSMContext):
    await state.update_data(watering=message.text)
    await message.answer(TEXTS['uk']['region_q'], reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(AgroForm.region)

@dp.message(AgroForm.region)
async def process_region(message: Message, state: FSMContext):
    await state.update_data(region=message.text)
    await message.answer(TEXTS['uk']['photo_q'])
    await state.set_state(AgroForm.photo)

@dp.message(AgroForm.photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    status_msg = await message.answer(TEXTS['uk']['wait'])

    # 1. ТЕКСТОВИЙ АНАЛІЗ (З КЛЮЧЕМ)
    prompt = (
        f"Ти — досвідчений ландшафтний архітектор. Регіон: {data.get('region')}. "
        f"Умови: {data.get('soil')} ґрунт, освітлення {data.get('sun')}, полив {data.get('watering')}. "
        f"Запропонуй 5 рослин, що витримують морози до -20°C (Україна). "
        f"Для кожної дай назву <b> та поясни чому (1 речення). "
        f"Мова: УКРАЇНСЬКА. Формат: список •. В кінці: PROMPT: та 5-7 англійських слів для саду."
    )
    
    analysis_text = "❌ Не вдалося отримати аналіз. Перевірте API ключ."
    img_kw = "professional garden design"

    async with aiohttp.ClientSession() as session:
        try:
            # Використовуємо Bearer Auth для ключа
            headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"} if POLLINATIONS_KEY else {}
            payload = {
                "model": "openai", 
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7
            }
            async with session.post("https://text.pollinations.ai/v1/chat/completions", json=payload, headers=headers) as r:
                if r.status == 200:
                    json_res = await r.json()
                    res = json_res['choices'][0]['message']['content']
                    if "PROMPT:" in res:
                        parts = res.split("PROMPT:")
                        analysis_text, img_kw = parts[0].strip(), parts[1].strip()
                    else:
                        analysis_text = res.strip()
                else:
                    print(f"Text API Error: {r.status} {await r.text()}")
        except Exception as e:
            print(f"Connection Error: {e}")

    await status_msg.edit_text(TEXTS['uk']['result_text'].format(analysis=analysis_text), parse_mode="HTML")
    await state.update_data(last_analysis=analysis_text)
    
    # 2. МАЛЮВАННЯ (Z-IMAGE TURBO З КЛЮЧЕМ)
    await message.answer(TEXTS['uk']['generating_img'])
    clean_kw = re.sub(r'[^a-zA-Z0-9\s]', '', img_kw)
    seed = random.randint(1, 999999)
    current_model = data.get('model', 'zimage')
    
    # Пряме посилання з ключем у параметрах (для платного доступу)
    img_url = (
        f"https://gen.pollinations.ai/image/{quote(clean_kw)}?"
        f"model={current_model}&"
        f"seed={seed}&"
        f"width=1024&height=1024&"
        f"nologo=true&private=true"
    )
    if POLLINATIONS_KEY:
        img_url += f"&key={POLLINATIONS_KEY}"

    try:
        await state.update_data(last_img_kw=clean_kw)
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        
        # Кнопки для швидкого перемикання між обраними моделями
        builder.button(text="🎨 Z-Image", callback_data="regen:zimage")
        builder.button(text="🚀 Turbo", callback_data="regen:turbo")
        builder.button(text="⚡ FLUX", callback_data="regen:flux")
        builder.adjust(3)
        
        caption = f"✨ Ваш візуальний проект (модель: {current_model})\n\nМожете змінити модель нижче 👇"
        await message.answer_photo(photo=img_url, caption=caption, reply_markup=builder.as_markup())
            
    except Exception as e:
        print(f"Image Error: {e}")
        # Спробуємо надіслати повідомлення, що обрана модель може бути недоступна
        await message.answer(
            f"⚠️ Певні складнощі з моделлю <b>{current_model}</b>.\n"
            "Спробуйте натиснути кнопку 🔄 Turbo нижче — вона найстабільніша!",
            parse_mode="HTML"
        )
        # Все одно покажемо кнопки для перемикання
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Спробувати Turbo", callback_data="regen:turbo")
        builder.button(text="🎨 Спробувати Z-Image", callback_data="regen:zimage")
        builder.adjust(2)
        await message.answer("Оберіть іншу модель:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("regen:"))
async def process_regen(callback: types.CallbackQuery, state: FSMContext):
    model_id = callback.data.split(":")[1]
    data = await state.get_data()
    kw = data.get('last_img_kw', 'garden design')
    
    seed = random.randint(1, 999999)
    img_url = (
        f"https://gen.pollinations.ai/image/{quote(kw)}?"
        f"model={model_id}&"
        f"seed={seed}&"
        f"width=1024&height=1024&"
        f"nologo=true&private=true"
    )
    if POLLINATIONS_KEY:
        img_url += f"&key={POLLINATIONS_KEY}"
        
    try:
        caption = f"✨ Новий варіант (модель: {model_id})"
        await callback.message.answer_photo(photo=img_url, caption=caption)
        await callback.answer()
        
        # Виправлено помилку: використовуємо callback.message замість message
        await callback.message.answer("💬 Ви можете написати мені щось у чат, щоб уточнити деталі або змінити рослини!")
        await state.set_state(AgroForm.chat)
    except Exception as e:
        print(f"Regen Error: {e}")
        await callback.answer("❌ Ця модель зараз недоступна. Спробуйте іншу!", show_alert=True)

@dp.message(AgroForm.chat)
async def chat_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    prompt = (
        f"Ти архітектор. Ми розробляємо сад у регіоні {data.get('region')}. "
        f"Попередні поради: {data.get('last_analysis')}. Питання користувача: {message.text}. "
        f"Відповідай коротко українською."
    )
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {POLLINATIONS_KEY}"} if POLLINATIONS_KEY else {}
            payload = {"model": "openai", "messages": [{"role": "user", "content": prompt}]}
            async with session.post("https://text.pollinations.ai/v1/chat/completions", json=payload, headers=headers) as r:
                res_json = await r.json()
                ans = res_json['choices'][0]['message']['content']
                await message.answer(ans, parse_mode="HTML")
                await state.update_data(last_analysis=ans)
    except:
        await message.answer("Помилка зв'язку з ШІ.")

# --- ЗАПУСК ---

async def on_startup(bot: Bot, *args, **kwargs):
    # Налаштуємо меню команд (кнопка "Menu" біля поля вводу)
    commands = [
        types.BotCommand(command="start", description="Запустити бота / Почати спочатку"),
        types.BotCommand(command="model", description="Змінити модель малювання")
    ]
    await bot.set_my_commands(commands)
    
    if RENDER_URL:
        # ПРИМУСОВЕ СКИНУТИ СТАРІ НАЛАШТУВАННЯ ТА ЧЕРГУ
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(f"{RENDER_URL}/webhook", drop_pending_updates=True)
        print(f"✅ Webhook successfully set to: {RENDER_URL}/webhook")

def main():
    if RENDER_URL:
        app = web.Application()
        handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        handler.register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        dp.startup.register(on_startup)
        web.run_app(app, host="0.0.0.0", port=PORT)
    else:
        async def run_polling():
            await on_startup(bot)
            await dp.start_polling(bot)
        asyncio.run(run_polling())

if __name__ == "__main__":
    main()
