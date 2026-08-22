FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends --yes ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 similubot \
    && mkdir --parents /app/data /app/temp \
    && chown --recursive similubot:similubot /app

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=similubot:similubot main.py ./
COPY --chown=similubot:similubot similubot/ ./similubot/

USER similubot

CMD ["python", "main.py"]
