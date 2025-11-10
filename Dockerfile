FROM python:3.14-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY pyproject.toml .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir .

COPY . .

CMD ["python", "-m", "cherubini.main"]
