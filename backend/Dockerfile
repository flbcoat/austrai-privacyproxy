FROM python:3.12-slim

WORKDIR /app

# System-Pakete: Tesseract OCR mit deutscher Sprachunterstuetzung + Bibliotheken
# Build-Tools fuer optionale C-Extensions (llama-cpp-python)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-deu \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    gcc \
    g++ \
    cmake \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Optional: Install llama-cpp-python for local LLM summarization (CPU-only).
# The GGUF model is NOT baked into the image — it downloads on first use (~350MB).
# Set INSTALL_LOCAL_LLM=1 at build time to enable: docker build --build-arg INSTALL_LOCAL_LLM=1 .
ARG INSTALL_LOCAL_LLM=0
RUN if [ "$INSTALL_LOCAL_LLM" = "1" ]; then \
      pip install --no-cache-dir 'llama-cpp-python>=0.3'; \
    fi

RUN python -m spacy download de_core_news_lg
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
