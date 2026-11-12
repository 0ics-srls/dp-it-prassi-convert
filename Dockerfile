# dp-it-prassi-convert production image (Python). proc-protocol stdin loop on main.py. tesseract + Italian data for the local OCR (no paid service).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-ita && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
COPY src ./src
ENV PYTHONPATH=/app/src
ENTRYPOINT ["python", "main.py"]
