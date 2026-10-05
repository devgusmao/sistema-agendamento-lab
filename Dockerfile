FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Usuário sem privilégios: o processo web não roda como root.
RUN useradd --create-home --uid 1000 app

COPY --chown=app:app . /app/
RUN chmod +x /app/entrypoint.sh && chown app:app /app

USER app

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
