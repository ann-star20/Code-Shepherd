FROM python:3.12-slim

WORKDIR /app

COPY _shared /app/_shared
COPY m6 /app/service

WORKDIR /app/service

RUN pip install --no-cache-dir -e /app/_shared

RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    torch sentence-transformers

EXPOSE 8007

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007"]
