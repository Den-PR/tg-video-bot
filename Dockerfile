FROM python:3.13-slim

# Устанавливаем ffmpeg (нужен для склейки потоков без перекодирования)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Создаем непривилегированного пользователя
RUN useradd --create-home --shell /bin/bash botuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY config.py downloader.py bot.py ./
RUN chown -R botuser:botuser /app

USER botuser

CMD ["python", "-u", "bot.py"]
