FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --no-cache-dir .

# Nothing here needs root once the dependencies are installed.
RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
