# Dockerfile (в корне site-for-mpu)
FROM python:3.10-slim

# где внутри контейнера будет лежать бот
WORKDIR /app

# копируем pip‑зависимости
COPY requirements.txt ./

# ставим зависимости
RUN pip install --no-cache-dir -r requirements.txt

# копируем весь код бота
COPY src/ ./src/

# запускаем бота
CMD ["python", "-m", "src.main.bot"]
