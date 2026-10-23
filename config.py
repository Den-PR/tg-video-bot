import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не задана!")

# Парсим список разрешенных chat_id (через запятую). Если пусто — разрешены все чаты.
_raw_chats = os.getenv("ALLOWED_CHAT_IDS", "").strip()
ALLOWED_CHAT_IDS: set[int] = {
    int(x.strip()) for x in _raw_chats.split(",") if x.strip().lstrip("-").isdigit()
}

# Лимиты безопасности
MAX_FILESIZE_BYTES = int(os.getenv("MAX_FILESIZE_BYTES", 48_000_000))  # ~48 МБ запас под лимит ТГ
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", 2))
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", 20))
DOWNLOAD_TIMEOUT_SEC = int(os.getenv("DOWNLOAD_TIMEOUT_SEC", 180))

# Опционально: прокси (например, socks5://127.0.0.1:1080) и путь к cookies.txt
PROXY_URL = os.getenv("PROXY_URL", "").strip() or None
_raw_cookies = os.getenv("COOKIES_FILE", "").strip() or None

# Если задан файл кук, копируем его в доступный для записи /tmp (tmpfs)
COOKIES_FILE = None
if _raw_cookies and os.path.exists(_raw_cookies):
    import shutil
    COOKIES_FILE = "/tmp/active_cookies.txt"
    try:
        shutil.copyfile(_raw_cookies, COOKIES_FILE)
    except Exception:
        COOKIES_FILE = _raw_cookies

# Белый список поддерживаемых доменов
ALLOWED_DOMAINS = {
    "instagram.com", "www.instagram.com", "ddinstagram.com",
    "x.com", "www.x.com", "twitter.com", "www.twitter.com", "vxtwitter.com", "fxtwitter.com",
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
}
