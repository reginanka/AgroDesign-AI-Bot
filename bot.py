import os
import asyncio
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder

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

    # 1. Текстовий аналіз через Pollinations (Claude/Llama)
    analysis_prompt = (
        f"User has {data['soil']} soil, {data['sun']} lighting, and {data['watering']} watering. "
        f"Suggest 5 specific plants for this garden. Output in {lang} language."
    )
    
    async with aiohttp.ClientSession() as session:
        # Запит до текстової моделі
        text_api_url = f"https://text.pollinations.ai/"
        payload = {
            "messages": [{"role": "user", "content": analysis_prompt}],
            "model": "openai-large", # або інша доступна модель
            "key": POLLINATIONS_KEY
        }
        async with session.post(text_api_url, json=payload) as resp:
            analysis = await resp.text()

    await status_msg.edit_text(TEXTS[lang]['result_text'].format(analysis=analysis))

    # 2. Генерація картинки на основі аналізу
    img_prompt = f"Professional landscape garden design with these plants: {analysis[:200]}. Photorealistic, Flux model, 4k."
    encoded_img_prompt = img_prompt.replace(" ", "%20")
    image_url = f"https://image.pollinations.ai/prompt/{encoded_img_prompt}?model=flux&width=1024&height=1024&nologo=true&key={POLLINATIONS_KEY}"

    await message.answer_photo(photo=image_url, caption="✨ Твій персональний дизайн")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
  
