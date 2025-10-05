# ==============================================================================
# Fase 1: Entorno de Construcción y Ejecución
# ==============================================================================
# Usar una imagen base de Python delgada (Debian) que es compatible con LibreOffice
FROM python:3.11-slim-bookworm

# Etiqueta para mantener el software y su autor
LABEL maintainer="NexusDev"
LABEL description="Microservicio para la conversión de archivos DOCX a PDF usando FastAPI y LibreOffice."

# Establecer variables de entorno para evitar diálogos interactivos durante la instalación
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# ==============================================================================
# Instalación de Dependencias del Sistema (LibreOffice)
# ==============================================================================
# Actualizar los repositorios e instalar LibreOffice en modo headless (sin GUI)
# --no-install-recommends reduce el tamaño final de la imagen
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libreoffice-writer \
    && \
    # Limpiar la caché de apt para mantener la imagen ligera
    rm -rf /var/lib/apt/lists/*

# ==============================================================================
# Configuración del Entorno de la Aplicación
# ==============================================================================
# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar el archivo de requerimientos primero para aprovechar el cache de capas de Docker
COPY requirements.txt .

# Instalar las dependencias de Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente de la aplicación
COPY ./src .

# ==============================================================================
# Ejecución
# ==============================================================================
# Exponer el puerto en el que correrá la aplicación
EXPOSE 8000

# Comando para iniciar la aplicación FastAPI con Uvicorn
# --host 0.0.0.0 es crucial para que sea accesible desde fuera del contenedor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]