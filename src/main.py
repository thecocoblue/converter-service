import os
import shutil
import subprocess
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse

# --------------------------------------------------------------------------
# Configuración de la Aplicación
# --------------------------------------------------------------------------
app = FastAPI(
    title="Servicio de Conversión de Archivos",
    description="Un microservicio para convertir archivos de un formato a otro.",
    version="0.2.0", # Versión actualizada
)

# --------------------------------------------------------------------------
# Endpoint de Health Check
# --------------------------------------------------------------------------
@app.get("/health", summary="Verificar estado del servicio", tags=["Monitoring"])
def health_check():
    """
    Endpoint simple para verificar que el servicio está activo.
    """
    return {"status": "ok"}

# --------------------------------------------------------------------------
# Endpoint de Conversión DOCX a PDF
# --------------------------------------------------------------------------
@app.post(
    "/convert/docx-to-pdf",
    summary="Convierte un archivo DOCX a PDF",
    tags=["Conversión"],
)
async def convert_docx_to_pdf(file: UploadFile = File(...)):
    """
    Recibe un archivo DOCX, lo convierte a PDF usando LibreOffice y lo devuelve.

    **Proceso:**
    1.  Valida que el archivo sea de tipo DOCX.
    2.  Crea un directorio temporal único para la operación.
    3.  Guarda el archivo DOCX subido en el directorio temporal.
    4.  Ejecuta el comando de LibreOffice para la conversión.
    5.  Verifica que el archivo PDF haya sido creado.
    6.  Devuelve el archivo PDF y agenda la limpieza del directorio temporal.
    """
    if file.content_type not in [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ]:
        raise HTTPException(
            status_code=400,
            detail=f"Formato de archivo no soportado: {file.content_type}. Se requiere un archivo DOCX.",
        )

    temp_dir = tempfile.mkdtemp()
    try:
        input_path = os.path.join(temp_dir, file.filename)
        base_filename = os.path.splitext(file.filename)[0]
        output_filename = f"{base_filename}.pdf"
        output_path = os.path.join(temp_dir, output_filename)

        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        command = [
            "libreoffice",
            "--headless",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            temp_dir,
            input_path,
        ]

        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60  # Aumentado a 60s para archivos grandes
        )

        if not os.path.exists(output_path) or process.returncode != 0:
            error_details = process.stderr.decode("utf-8") or process.stdout.decode("utf-8")
            raise HTTPException(
                status_code=500,
                detail=f"Error en la conversión. LibreOffice no generó el archivo. Detalles: {error_details}",
            )

        # Correcto: Agendar la limpieza para DESPUÉS de que el archivo sea enviado
        cleanup_task = BackgroundTask(shutil.rmtree, temp_dir)
        
        return FileResponse(
            path=output_path,
            media_type="application/pdf",
            filename=output_filename,
            background=cleanup_task,
        )
    except Exception as e:
        # En caso de cualquier otro error, asegurarse de limpiar.
        shutil.rmtree(temp_dir)
        # Re-lanzar la excepción para que FastAPI la maneje
        raise e
