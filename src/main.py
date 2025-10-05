import os
import shutil
import subprocess
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse, PlainTextResponse

# --------------------------------------------------------------------------
# Configuración de la Aplicación
# --------------------------------------------------------------------------
app = FastAPI(
    title="Servicio de Conversión de Archivos v3",
    description="Un microservicio genérico para convertir archivos de ofimática e imágenes.",
    version="3.0.0",
)

# --------------------------------------------------------------------------
# Lógica de Conversión y Definiciones
# --------------------------------------------------------------------------
SUPPORTED_MIME_TYPES = {
    "pdf": "application/pdf", "txt": "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "odp": "application/vnd.oasis.opendocument.presentation",
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp",
}

def get_command(tool, input_path, output_path, to_format, temp_dir):
    """Construye el comando de conversión adecuado."""
    if tool == "libreoffice":
        return [
            "libreoffice", "--headless", "--convert-to", to_format,
            "--outdir", temp_dir, input_path
        ]
    if tool == "imagemagick":
        # Para convertir la primera página de un PDF a imagen
        if input_path.endswith('.pdf'):
            input_path += "[0]" # Sintaxis para seleccionar la primera página
        return ["convert", "-density", "300", input_path, output_path]
    if tool == "pdftotext":
        return ["pdftotext", input_path, output_path]
    return []

# Matriz de conversiones soportadas: (formato_entrada, formato_salida): herramienta
CONVERSION_MATRIX = {
    # Ofimática a PDF (con LibreOffice)
    ("docx", "pdf"): "libreoffice", ("doc", "pdf"): "libreoffice",
    ("xlsx", "pdf"): "libreoffice", ("xls", "pdf"): "libreoffice",
    ("pptx", "pdf"): "libreoffice", ("ppt", "pdf"): "libreoffice",
    ("odt", "pdf"): "libreoffice", ("ods", "pdf"): "libreoffice",
    ("odp", "pdf"): "libreoffice",
    
    # Conversiones entre Imágenes (con ImageMagick)
    ("png", "jpg"): "imagemagick", ("png", "webp"): "imagemagick",
    ("png", "gif"): "imagemagick", ("png", "bmp"): "imagemagick",
    ("jpg", "png"): "imagemagick", ("jpg", "webp"): "imagemagick",
    ("webp", "png"): "imagemagick", ("webp", "jpg"): "imagemagick",

    # Soluciones pragmáticas desde PDF
    ("pdf", "txt"): "pdftotext",
    ("pdf", "png"): "imagemagick", # PDF (primera página) a PNG
}

# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@app.get("/health", summary="Verificar estado del servicio", tags=["Monitoring"])
def health_check():
    return {"status": "ok"}

@app.get("/supported-formats", summary="Listar conversiones soportadas", tags=["Información"])
def supported_formats():
    """Devuelve una lista de todas las conversiones posibles."""
    return {"supported_conversions": [f"{k[0]} -> {k[1]}" for k in CONVERSION_MATRIX.keys()]}

@app.post("/convert", summary="Convierte un archivo", tags=["Conversión"])
async def convert_file(
    file: UploadFile = File(...),
    to_format: str = Query(..., description="Formato de salida deseado (ej. pdf, jpg, png, txt)"),
):
    try:
        from_format = file.filename.split('.')[-1].lower()
    except IndexError:
        raise HTTPException(status_code=400, detail="El archivo no tiene extensión.")

    conversion_pair = (from_format, to_format.lower())
    tool = CONVERSION_MATRIX.get(conversion_pair)

    if not tool:
        raise HTTPException(
            status_code=400,
            detail=f"Conversión de '{from_format}' a '{to_format}' no soportada."
        )

    temp_dir = tempfile.mkdtemp()
    try:
        # Preparar nombres de archivo
        # Usar un nombre de entrada genérico para evitar problemas con caracteres especiales
        input_filename = f"input.{from_format}"
        input_path = os.path.join(temp_dir, input_filename)
        
        base_filename = os.path.splitext(file.filename)[0]
        output_filename = f"{base_filename}.{to_format}"
        output_path = os.path.join(temp_dir, f"input.{to_format}")
        
        # Guardar archivo
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Obtener y ejecutar comando
        command = get_command(tool, input_path, output_path, to_format, temp_dir)
        process = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120
        )

        if not os.path.exists(output_path) or process.returncode != 0:
            error_details = process.stderr.decode("utf-8") or process.stdout.decode("utf-8")
            raise HTTPException(
                status_code=500,
                detail=f"Error en la conversión. Herramienta: {tool}. Detalles: {error_details}",
            )
        
        # Agendar limpieza
        cleanup_task = BackgroundTask(shutil.rmtree, temp_dir)
        output_mime_type = SUPPORTED_MIME_TYPES.get(to_format, "application/octet-stream")

        return FileResponse(
            path=output_path,
            media_type=output_mime_type,
            filename=output_filename,
            background=cleanup_task,
        )
    except Exception as e:
        shutil.rmtree(temp_dir)
        raise e
