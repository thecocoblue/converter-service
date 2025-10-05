# ==============================================================================
# Fase 1: Entorno de Construcción y Ejecución
# ==============================================================================
FROM python:3.11-slim-bookworm

LABEL maintainer="NexusDev"
LABEL description="Microservicio para la conversión de archivos usando FastAPI, LibreOffice, ImageMagick y Poppler."

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# ==============================================================================
# Instalación de Dependencias del Sistema
# ==============================================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libreoffice \
    imagemagick \
    poppler-utils \
    && \
    rm -rf /var/lib/apt/lists/*

# ==============================================================================
# Configuración del Entorno de la Aplicación
# ==============================================================================
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
COPY ./src .

# ==============================================================================
# Ejecución
# ==============================================================================
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
