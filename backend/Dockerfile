FROM python:3.12-slim
WORKDIR /app
RUN apt-get update -qq && apt-get install -y -qq \
    tesseract-ocr tesseract-ocr-chi-sim \
    ffmpeg \
    libsqlcipher-dev gcc \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt constraints.txt .
RUN pip install --no-cache-dir -c constraints.txt -r requirements.txt
# Fail the image build if SQLCipher support cannot be installed. Silently
# falling back to plaintext SQLite when a deployment supplies an encryption
# key would make its security configuration misleading.
RUN pip install --no-cache-dir pysqlcipher3
COPY . .
RUN mkdir -p /app/data
EXPOSE 8000
# Seeds run on first initialization and must all succeed before the API starts.
CMD ["python3", "scripts/docker_initialize.py"]
