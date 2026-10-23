import os
import re
import time
import logging
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
import yt_dlp

from config import (
    ALLOWED_DOMAINS,
    MAX_FILESIZE_BYTES,
    DOWNLOAD_TIMEOUT_SEC,
    PROXY_URL,
    COOKIES_FILE,
)

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https?://[^\s<>\"'`]+")


class VideoTooLargeError(Exception):
    """Видео превышает лимит 48 МБ даже в 360p или нет подходящих форматов."""
    pass


class DownloadTimeoutError(Exception):
    """Превышено время ожидания загрузки."""
    pass


@dataclass
class VideoResult:
    file_path: str
    width: int | None = None
    height: int | None = None
    duration: int | None = None


def normalize_domain(url: str) -> str:
    """Меняет альтернативные домены (vxtwitter/ddinstagram) на оригинальные для yt-dlp."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in ("vxtwitter.com", "fxtwitter.com"):
        return url.replace(host, "x.com", 1)
    if host == "ddinstagram.com":
        return url.replace(host, "instagram.com", 1)
    return url


def strip_tracking_params(url: str) -> str:
    """
    Очищает URL от следящих и реферальных параметров, защищая приватность пользователей:
    - Instagram: igsh, exln, srtk, utm_*
    - X / Twitter: s, t
    - YouTube: si, feature (но оставляет полезный таймкод ?t=)
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    # Для Instagram и X/Twitter любые параметры в URL поста — это трекеры
    if any(h in host for h in ("instagram.com", "ddinstagram.com", "x.com", "twitter.com", "vxtwitter.com", "fxtwitter.com")):
        return urlunparse(parsed._replace(query="", fragment=""))

    # Для YouTube удаляем трекеры, но сохраняем таймкод ?t= и id ролика ?v=
    if any(h in host for h in ("youtube.com", "youtu.be")):
        if "/shorts/" in parsed.path:
            return urlunparse(parsed._replace(query="", fragment=""))

        qs = parse_qs(parsed.query, keep_blank_values=True)
        # Список трекинговых параметров Google/YouTube
        for tracker in ("si", "feature", "pp", "ab_channel", "utm_source", "utm_medium", "utm_campaign"):
            qs.pop(tracker, None)

        new_query = urlencode(qs, doseq=True)
        return urlunparse(parsed._replace(query=new_query, fragment=""))

    return url


def extract_urls(text: str) -> list[str]:
    """Извлекает уникальные валидные ссылки из текста, очищая их от трекеров."""
    if not text:
        return []
    seen = set()
    valid_urls = []
    for match in URL_REGEX.finditer(text):
        raw_url = match.group(0).rstrip(".,!?;:)>]")
        parsed = urlparse(raw_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme in ("http", "https") and host in ALLOWED_DOMAINS:
            clean_url = normalize_domain(raw_url)
            clean_url = strip_tracking_params(clean_url)
            if clean_url not in seen:
                seen.add(clean_url)
                valid_urls.append(clean_url)
    return valid_urls


def _get_short_side(fmt: dict) -> int | None:
    """Возвращает меньшую сторону кадра (для корректной оценки 16:9 и 9:16 видео)."""
    w = fmt.get("width")
    h = fmt.get("height")
    if w and h:
        return min(w, h)
    return h or w


def _estimate_format_size(fmt: dict, duration: float | None) -> int | None:
    """Оценивает размер формата в байтах по метаданным или битрейту."""
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if size:
        return int(size)
    tbr = fmt.get("tbr")
    if tbr and duration:
        return int((tbr * 1000 / 8) * duration)
    return None


def _select_target_res(info: dict) -> int:
    """Выбирает целевое разрешение (720, 480 или 360), умещающееся в лимит."""
    duration = info.get("duration")
    formats = info.get("formats") or []

    if duration and duration > 2700:
        raise VideoTooLargeError("Видео слишком длинное для лимита 50 МБ.")

    for target_res in (720, 480, 360):
        candidates = [
            f for f in formats
            if f.get("vcodec") not in (None, "none")
            and (_get_short_side(f) is None or (360 <= _get_short_side(f) <= target_res))
        ]
        if not candidates:
            continue

        for fmt in candidates:
            est_size = _estimate_format_size(fmt, duration)
            if est_size is None or est_size < (MAX_FILESIZE_BYTES - 3_000_000):
                return target_res

    for fmt in formats:
        if fmt.get("vcodec") not in (None, "none"):
            est_size = _estimate_format_size(fmt, duration)
            if est_size is None or est_size < (MAX_FILESIZE_BYTES - 3_000_000):
                return 1080

    raise VideoTooLargeError("Все доступные форматы превышают 48 МБ.")


def download_video_sync(url: str, temp_dir: str) -> VideoResult:
    """Синхронная функция скачивания видео."""
    start_time = time.monotonic()

    def progress_hook(d: dict):
        if time.monotonic() - start_time > DOWNLOAD_TIMEOUT_SEC:
            raise DownloadTimeoutError("Превышен лимит времени на скачивание.")
        if d.get("status") == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if downloaded > MAX_FILESIZE_BYTES or total > MAX_FILESIZE_BYTES:
                raise VideoTooLargeError("Размер потока превысил 48 МБ.")

    base_opts = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 15,
        "geo_bypass": True,
        "allowed_extractors": ["youtube", "youtube:tab", "instagram", "twitter", "twitter:card"],
    }
    if PROXY_URL:
        base_opts["proxy"] = PROXY_URL
    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        base_opts["cookiefile"] = COOKIES_FILE

    with yt_dlp.YoutubeDL(base_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError("Не удалось получить метаданные видео.")
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise ValueError("Пустой плейлист или карусель.")
            info = entries[0]

    target_res = _select_target_res(info)
    output_template = os.path.join(temp_dir, "video.%(ext)s")

    dl_opts = {
        **base_opts,
        "format": "bestvideo+bestaudio/best",
        "format_sort": [
            f"res:{target_res}",
            "vcodec:h264",
            "acodec:aac",
            "ext:mp4:m4a",
            f"filesize:{MAX_FILESIZE_BYTES}",
        ],
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "max_filesize": MAX_FILESIZE_BYTES,
        "progress_hooks": [progress_hook],
    }

    with yt_dlp.YoutubeDL(dl_opts) as ydl:
        dl_info = ydl.extract_info(url, download=True)
        if "entries" in dl_info:
            dl_info = dl_info["entries"][0]

    final_path = os.path.join(temp_dir, "video.mp4")
    if not os.path.exists(final_path):
        files = [os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if not f.endswith(".part")]
        if not files:
            raise VideoTooLargeError("Файл не был создан (сработал лимит max_filesize).")
        final_path = files[0]

    actual_size = os.path.getsize(final_path)
    if actual_size == 0 or actual_size > MAX_FILESIZE_BYTES:
        raise VideoTooLargeError(f"Итоговый файл ({actual_size} байт) превышает лимит.")

    short_side = _get_short_side(dl_info)
    if short_side and short_side < 360 and "youtube" in url:
        raise VideoTooLargeError(f"Доступно только слишком низкое разрешение ({short_side}p).")

    return VideoResult(
        file_path=final_path,
        width=dl_info.get("width"),
        height=dl_info.get("height"),
        duration=int(dl_info["duration"]) if dl_info.get("duration") else None,
    )
