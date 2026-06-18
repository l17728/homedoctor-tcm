FROM python:3.10-slim
WORKDIR /app
RUN apt-get update -qq && apt-get install -y -qq \
    tesseract-ocr tesseract-ocr-chi-sim \
    libsqlcipher-dev gcc \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir pysqlcipher3 || echo "pysqlcipher3 build failed — encryption disabled"
COPY . .
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["sh", "-c", "python3 scripts/seed_herbs_batch1.py && python3 scripts/seed_herbs_batch2.py && python3 scripts/seed_herbs_batch3.py && python3 scripts/seed_herbs_batch4.py && python3 scripts/seed_herbs_batch5.py && python3 scripts/seed_formulas.py && python3 scripts/seed_classics.py && python3 scripts/seed_therapies.py && python3 scripts/seed_modifications.py && python3 scripts/seed_knowledge_entities.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
