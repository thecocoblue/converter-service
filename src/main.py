import os
import shutil
import subprocess
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse

# --------------------------------------------------------------------------
# Configuración de la Aplicación
# --------------------------------------------------------------------------
app = FastAPI(
    title="Servicio de Conversión de Archivos v2",
    description="Un microservicio genérico para convertir archivos.",
    version="2.0.0",
)

SUPPORTED_MIME_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}

# --------------------------------------------------------------------------
# Endpoint de Health Check
# --------------------------------------------------------------------------
@app.get("/health", summary="Verificar estado del servicio", tags=["Monitoring"])
def health_check():
    return {"status": "ok"}

# --------------------------------------------------------------------------
# Endpoint de Conversión Genérico
# --------------------------------------------------------------------------
@app.post("/convert", summary="Convierte un archivo de un formato a otro", tags=["Conversión"])
async def convert_file(
    file: UploadFile = File(...),
    to_format: str = Query(..., description="Formato de salida deseado (ej. pdf, jpg)"),
):
    """
    Recibe un archivo, detecta su formato de entrada por la extensión y lo 
    convierte al formato de salida especificado.

    **Conversiones Soportadas:**
    - `docx` -> `pdf`
    - `png`  -> `jpg`
    """
    
    # 1. Determinar el formato de entrada por la extensión del archivo
    try:
        from_format = file.filename.split('.')[-1].lower()
    except IndexError:
        raise HTTPException(
            status_code=400,
            detail="El archivo no tiene una extensión válida."
        )

    temp_dir = tempfile.mkdtemp()
    try:
        input_path = os.path.join(temp_dir, file.filename)
        base_filename = os.path.splitext(file.filename)[0]
        output_filename = f"{base_filename}.{to_format}"
        output_path = os.path.join(temp_dir, output_filename)

        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 2. Lógica de enrutamiento basada en los formatos
        command = []
        if from_format == "docx" and to_format == "pdf":
            command = [
                "libreoffice", "--headless", "--convert-to", "pdf:writer_pdf_Export",
                "--outdir", temp_dir, input_path
            ]
        elif from_format == "png" and to_format == "jpg":
            command = [
                "convert", input_path, output_path
            ]
        else:
            shutil.rmtree(temp_dir)
            raise HTTPException(
                status_code=400,
                detail=f"Conversión de '{from_format}' a '{to_format}' no está soportada."
            )
        
        # 3. Ejecutar el comando de conversión
        process = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60
        )

        if not os.path.exists(output_path) or process.returncode != 0:
            error_details = process.stderr.decode("utf-8") or process.stdout.decode("utf-8")
            raise HTTPException(
                status_code=500,
                detail=f"Error en la conversión. Detalles: {error_details}",
            )

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
