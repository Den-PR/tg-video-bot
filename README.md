# Telegram Video Downloader Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.13-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0.svg?logo=telegram&logoColor=white)](https://github.com/aiogram/aiogram)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-red.svg)](https://github.com/yt-dlp/yt-dlp)

Легковесный Telegram-бот на Python (aiogram 3 + yt-dlp) для автоматической загрузки и отправки видео в групповые чаты из Instagram (Reels), YouTube (Shorts/видео) и X (Twitter).

## Особенности
- **Автоматическая работа:** реагирует на ссылки без специальных команд.
- **Умный выбор качества:** подбирает форматы (720p -> 480p -> 360p, H.264 + AAC) под лимит Telegram (50 МБ) за один проход.
- **Приватность:** автоматически вырезает трекинговые параметры (?igsh=..., ?si=...) из входящих ссылок.
- **Безопасность контейнера:** работает от непривилегированного пользователя, с файловой системой read_only, временным хранилищем в tmpfs и сбросом Linux capabilities.
- **Защита от перегрузки:** семафор на количество параллельных скачиваний и очередь задач.

## Быстрый старт

1. Склонируйте репозиторий:
   git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ>
   cd tg-video-bot

2. Создайте файл конфигурации .env на основе примера:
   cp .env.example .env
   nano .env

3. Запустите контейнер:
   docker compose up -d --build
