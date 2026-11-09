import os
import json
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    InputMediaPhoto, 
    InlineQueryResultArticle, 
    InputTextMessageContent
)

# Токены теперь берутся из защищенных настроек сервера
BOT_TOKEN = os.getenv('BOT_TOKEN')
BRICKSET_API_KEY = os.getenv('BRICKSET_API_KEY')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def search_brickset(query):
    url = "https://brickset.com/api/v3.asmx/getSets"
    
    if query.isdigit():
        params = {"setNumber": f"{query}-1", "extendedData": 1}
    elif "-" in query and query.replace("-", "").isdigit():
        params = {"setNumber": query, "extendedData": 1}
    else:
        params = {"query": query, "extendedData": 1}
        
    data = {
        "apiKey": BRICKSET_API_KEY,
        "userHash": "",
        "params": json.dumps(params)
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as response:
            if response.status == 200:
                result = await response.json(content_type=None)
                if result.get("status") == "success":
                    return result.get("sets", [])
    return []

async def get_additional_images(set_id):
    url = "https://brickset.com/api/v3.asmx/getAdditionalImages"
    data = {
        "apiKey": BRICKSET_API_KEY,
        "setID": str(set_id)
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as response:
            if response.status == 200:
                result = await response.json(content_type=None)
                if result.get("status") == "success":
                    return result.get("additionalImages", [])
    return []

async def send_lego_result(chat_id, lego_set, status_msg=None):
    set_id = lego_set.get("setID")
    name = lego_set.get("name")
    number = lego_set.get("number")
    year = lego_set.get("year")
    pieces = lego_set.get("pieces", "Нет данных")
    minifigs_count = lego_set.get("minifigs", 0)
    set_url = lego_set.get("bricksetURL")
    
    # ПРАВИЛЬНЫЙ ПУТЬ: Достаем теги из блока extendedData
    extended_data = lego_set.get("extendedData", {})
    tags = extended_data.get("tags", [])
    
    # 1. Проверяем Comic-Con (по обоим возможным тегам)
    is_comic_con = "Comic-Con Events" in tags or "San Diego Comic-Con" in tags
    tag_prefix = "🎪 <b>Эксклюзив Comic-Con!</b>\n" if is_comic_con else ""

    # 2. Вытаскиваем имена минифигурок (все теги, заканчивающиеся на |n)
    minifig_names = [tag.replace("|n", "") for tag in tags if tag.endswith("|n")]
    
    # Формируем красивую строку для минифигурок
    if minifig_names:
        minifigs_text = f"{minifigs_count} ({', '.join(minifig_names)})"
    else:
        minifigs_text = str(minifigs_count)

    main_image_url = None
    if "image" in lego_set and "imageURL" in lego_set["image"]:
        main_image_url = lego_set["image"]["imageURL"]

    caption = (
        f"{tag_prefix}"
        f"🧱 <b>{name}</b> ({number})\n\n"
        f"📅 Год выпуска: {year}\n"
        f"🧩 Деталей: {pieces}\n"
        f"🧍‍♂️ Минифигурок: {minifigs_text}\n\n"
        f"🔗 <a href='{set_url}'>Смотреть на Brickset</a>"
    )

    if main_image_url:
        media_group = [InputMediaPhoto(media=main_image_url, caption=caption, parse_mode="HTML")]
        extra_images = await get_additional_images(set_id)
        
        for img in extra_images[:9]:
            img_url = img.get("imageURL")
            if img_url and img_url != main_image_url:
                media_group.append(InputMediaPhoto(media=img_url))
                
        if len(media_group) > 1:
            await bot.send_media_group(chat_id=chat_id, media=media_group)
        else:
            await bot.send_photo(chat_id=chat_id, photo=main_image_url, caption=caption, parse_mode="HTML")
    else:
        await bot.send_message(chat_id=chat_id, text=caption + "\n\n<i>Фото не найдено.</i>", parse_mode="HTML")

    if status_msg:
        try:
            await status_msg.delete()
        except:
            pass

@dp.inline_query()
async def inline_handler(inline_query: types.InlineQuery):
    text = inline_query.query.strip()
    if not text or len(text) < 2:
        return 
        
    sets = await search_brickset(text)
    results = []
    
    for lego_set in sets[:40]:
        set_id = str(lego_set.get("setID"))
        name = lego_set.get("name")
        number = lego_set.get("number")
        year = lego_set.get("year")
        image_url = None
        if "image" in lego_set and "imageURL" in lego_set["image"]:
            image_url = lego_set["image"]["imageURL"]
            
        results.append(
            InlineQueryResultArticle(
                id=set_id,
                title=f"{number} - {name}",
                description=f"Год: {year}",
                thumbnail_url=image_url, 
                input_message_content=InputTextMessageContent(
                    message_text=f"/lego {number}",
                    parse_mode="HTML"
                )
            )
        )
    await inline_query.answer(results, cache_time=0)

@dp.message(Command("lego", ignore_case=True))
async def lego_command_handler(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return
    query = parts[1].strip()
    status_msg = await message.reply("⏳ Собираю информацию...")
    sets = await search_brickset(query)
    
    if sets:
        await send_lego_result(message.chat.id, sets[0], status_msg)
    else:
        await status_msg.edit_text("❌ Набор не найден.")

async def main():
    print("Бот запущен. Теги Comic-Con и имена фигурок работают!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())