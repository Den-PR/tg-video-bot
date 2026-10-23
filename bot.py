import asyncio
import logging
import tempfile
from aiogram import Bot, Dispatcher
from aiogram.types import Message, FSInputFile
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramRetryAfter
import yt_dlp

from config import (
    BOT_TOKEN,
    ALLOWED_CHAT_IDS,
    MAX_CONCURRENT_DOWNLOADS,
    MAX_QUEUE_SIZE,
)
from downloader import (
    extract_urls,
    download_video_sync,
    VideoTooLargeError,
    DownloadTimeoutError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
active_tasks_count = 0


def is_chat_allowed(chat_id: int) -> bool:
    if not ALLOWED_CHAT_IDS:
        return True
    return chat_id in ALLOWED_CHAT_IDS


def collect_message_urls(message: Message) -> list[str]:
    """Собирает ссылки из текста, подписи к медиа и зашитых text_link."""
    chunks = []
    if message.text:
        chunks.append(message.text)
    if message.caption:
        chunks.append(message.caption)

    for entity in (message.entities or []) + (message.caption_entities or []):
        if entity.type == "text_link" and entity.url:
            chunks.append(entity.url)

    return extract_urls("\n".join(chunks))


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я бот для скачивания видео из Instagram, X (Twitter) и YouTube.\n"
        f"ID этого чата: `{message.chat.id}`",
        parse_mode="Markdown",
    )


@dp.message(Command("id"))
async def cmd_id(message: Message):
    """Вспомогательная команда, чтобы легко узнать ID группы для .env."""
    await message.reply(f"ID этого чата: `{message.chat.id}`", parse_mode="Markdown")


async def process_single_url(message: Message, url: str):
    """Обрабатывает одну ссылку внутри семафора с автоочисткой временной папки."""
    async with download_semaphore:
        with tempfile.TemporaryDirectory(prefix="tg_vid_") as temp_dir:
            try:
                await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, download_video_sync, url, temp_dir)

                video_file = FSInputFile(result.file_path)
                try:
                    await message.reply_video(
                        video=video_file,
                        width=result.width,
                        height=result.height,
                        duration=result.duration,
                        supports_streaming=True,
                    )
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                    await message.reply_video(
                        video=video_file,
                        width=result.width,
                        height=result.height,
                        duration=result.duration,
                        supports_streaming=True,
                    )

            except VideoTooLargeError:
                await message.reply(
                    "⚠️ Не удалось загрузить: видео превышает лимит Telegram (50 МБ) или нет качества от 360p."
                )
            except DownloadTimeoutError:
                await message.reply("⚠️ Превышено время ожидания при загрузке видео.")
            except yt_dlp.utils.DownloadError as e:
                err_text = str(e)
                if any(k in err_text for k in ("max-filesize", "File is larger")):
                    await message.reply(
                        "⚠️ Не удалось загрузить: видео слишком большое для отправки через Telegram (лимит 50 МБ)."
                    )
                elif any(k in err_text for k in ("isn't available to everyone", "certain audiences", "age-restricted", "inappropriate")):
                    await message.reply(
                        "🔞 Это видео имеет возрастное ограничение (18+) или скрыто автором для неавторизованных пользователей."
                    )
                elif any(k in err_text for k in ("login required", "Sign in", "rate-limit", "not available")):
                    logger.warning("Доступ ограничен площадкой для %s: %s", url, err_text)
                    await message.reply(
                        "⚠️ Площадка временно ограничила доступ к этому видео (приватный аккаунт или требуется авторизация)."
                    )
                else:
                    logger.warning("Ошибка yt-dlp при обработке %s: %s", url, err_text)
            except Exception as e:
                logger.exception("Непредвиденная ошибка при обработке видео: %s", type(e).__name__)


@dp.message()
async def handle_messages(message: Message):
    global active_tasks_count

    if not is_chat_allowed(message.chat.id):
        return

    urls = collect_message_urls(message)
    if not urls:
        return

    if active_tasks_count + len(urls) > MAX_QUEUE_SIZE:
        await message.reply("⏳ Очередь загрузок сейчас переполнена, попробуйте чуть позже.")
        return

    active_tasks_count += len(urls)
    try:
        await asyncio.gather(*(process_single_url(message, url) for url in urls))
    finally:
        active_tasks_count -= len(urls)


async def main():
    logger.info("Бот запущен! Разрешенные чаты: %s", ALLOWED_CHAT_IDS if ALLOWED_CHAT_IDS else "ВСЕ (режим теста)")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
