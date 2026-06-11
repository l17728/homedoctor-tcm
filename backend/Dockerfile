FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Create data directory (volume mount point)
RUN mkdir -p /app/data
EXPOSE 8000
# Start server: uvicorn + seed data on first run
CMD ["sh", "-c", "python3 scripts/seed_herbs_batch1.py && python3 scripts/seed_herbs_batch2.py && python3 scripts/seed_herbs_batch3.py && python3 scripts/seed_formulas.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
