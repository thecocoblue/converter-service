import os
import shutil
import subprocess
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
import httpx
from urllib.parse import urlparse

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------
app = FastAPI(
    title="Servicio de Conversión de Archivos v4",
    description="Un microservicio para convertir archivos subidos o desde una URL.",
    version="4.0.0",
)

# Modelo Pydantic para la petición de conversión desde URL
class UrlConversionRequest(BaseModel):
    url: HttpUrl
    to_format: str

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

CONVERSION_MATRIX = {
    ("docx", "pdf"): "libreoffice", ("doc", "pdf"): "libreoffice",
    ("xlsx", "pdf"): "libreoffice", ("xls", "pdf"): "libreoffice",
    ("pptx", "pdf"): "libreoffice", ("ppt", "pdf"): "libreoffice",
    ("odt", "pdf"): "libreoffice", ("ods", "pdf"): "libreoffice",
    ("odp", "pdf"): "libreoffice",
    ("png", "jpg"): "imagemagick", ("png", "webp"): "imagemagick",
    ("png", "gif"): "imagemagick", ("png", "bmp"): "imagemagick",
    ("jpg", "png"): "imagemagick", ("jpg", "webp"): "imagemagick",
    ("webp", "png"): "imagemagick", ("webp", "jpg"): "imagemagick",
    ("pdf", "txt"): "pdftotext", ("pdf", "png"): "imagemagick",
}

def get_command(tool, input_path, to_format, temp_dir):
    output_path = os.path.join(temp_dir, f"output.{to_format}")
    if tool == "libreoffice":
        return [
            "libreoffice", "--headless", "--convert-to", to_format,
            "--outdir", temp_dir, input_path
        ], output_path
    if tool == "imagemagick":
        if input_path.endswith('.pdf'):
            input_path += "[0]"
        return ["convert", "-density", "300", input_path, output_path], output_path
    if tool == "pdftotext":
        return ["pdftotext", input_path, output_path], output_path
    return [], None

# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@app.get("/health", summary="Verificar estado del servicio", tags=["Monitoring"])
def health_check():
    return {"status": "ok"}

@app.get("/supported-formats", summary="Listar conversiones soportadas", tags=["Información"])
def supported_formats():
    return {"supported_conversions": [f"{k[0]} -> {k[1]}" for k in CONVERSION_MATRIX.keys()]}

@app.post("/convert", summary="Convierte un archivo subido", tags=["Conversión"])
async def convert_file_upload(
    file: UploadFile = File(...),
    to_format: str = Query(..., description="Formato de salida (ej. pdf, jpg)"),
):
    try:
        original_filename = file.filename
        content = await file.read()
        return await process_conversion(original_filename, to_format, content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar el archivo subido: {str(e)}")


@app.post("/convert-from-url", summary="Convierte un archivo desde una URL", tags=["Conversión"])
async def convert_from_url(request: UrlConversionRequest):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(str(request.url), follow_redirects=True, timeout=60)
            response.raise_for_status()
            content = response.content
            
            # Extraer el nombre del archivo de la URL
            path = urlparse(str(request.url)).path
            original_filename = os.path.basename(path)
            
            if not original_filename: # Si no hay nombre de archivo en la URL
                raise HTTPException(status_code=400, detail="No se pudo determinar el nombre del archivo desde la URL.")

            return await process_conversion(original_filename, request.to_format, content)

        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Error al obtener el archivo desde la URL: {e.response.text}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=400, detail=f"No se pudo acceder a la URL: {str(e)}")

# --------------------------------------------------------------------------
# Función de Lógica Principal (Refactorizada)
# --------------------------------------------------------------------------
async def process_conversion(original_filename: str, to_format: str, content: bytes):
    try:
        from_format = original_filename.split('.')[-1].lower()
    except IndexError:
        raise HTTPException(status_code=400, detail="El archivo no tiene extensión.")

    conversion_pair = (from_format, to_format.lower())
    tool = CONVERSION_MATRIX.get(conversion_pair)
    if not tool:
        raise HTTPException(status_code=400, detail=f"Conversión de '{from_format}' a '{to_format}' no soportada.")

    temp_dir = tempfile.mkdtemp()
    try:
        input_path = os.path.join(temp_dir, f"input.{from_format}")
        with open(input_path, "wb") as f:
            f.write(content)

        command, output_path = get_command(tool, input_path, to_format.lower(), temp_dir)
        
        process = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120
        )

        if not os.path.exists(output_path) or process.returncode != 0:
            error_details = process.stderr.decode("utf-8") or process.stdout.decode("utf-8")
            raise HTTPException(
                status_code=500,
                detail=f"Error en la conversión. Herramienta: {tool}. Detalles: {error_details}",
            )
        
        cleanup_task = BackgroundTask(shutil.rmtree, temp_dir)
        output_mime_type = SUPPORTED_MIME_TYPES.get(to_format, "application/octet-stream")
        
        # Generar nombre de archivo de salida
        base_filename = os.path.splitext(original_filename)[0]
        final_output_filename = f"{base_filename}.{to_format.lower()}"

        return FileResponse(
            path=output_path,
            media_type=output_mime_type,
            filename=final_output_filename,
            background=cleanup_task,
        )
    except Exception as e:
        shutil.rmtree(temp_dir)
        raise e
