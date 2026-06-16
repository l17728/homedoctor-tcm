FROM python:3.10-slim
WORKDIR /app
RUN apt-get update -qq && apt-get install -y -qq tesseract-ocr tesseract-ocr-chi-sim && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["sh", "-c", "python3 scripts/seed_herbs_batch1.py && python3 scripts/seed_herbs_batch2.py && python3 scripts/seed_herbs_batch3.py && python3 scripts/seed_formulas.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
