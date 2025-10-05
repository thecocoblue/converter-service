import os
import shutil
import subprocess
import tempfile
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

# --------------------------------------------------------------------------
# Configuración de la Aplicación
# --------------------------------------------------------------------------
app = FastAPI(
    title="Servicio de Conversión de Archivos",
    description="Un microservicio para convertir archivos de un formato a otro.",
    version="0.1.0",
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
    6.  Devuelve el archivo PDF al cliente.
    7.  Limpia el directorio temporal y sus contenidos.
    """
    # Validación del tipo de archivo
    if file.content_type not in [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ]:
        raise HTTPException(
            status_code=400,
            detail=f"Formato de archivo no soportado: {file.content_type}. Se requiere un archivo DOCX.",
        )

    # Crear un directorio de trabajo temporal y seguro
    temp_dir = tempfile.mkdtemp()
    input_path = os.path.join(temp_dir, file.filename)
    
    # Asignar un nombre de archivo de salida predecible
    base_filename = os.path.splitext(file.filename)[0]
    output_filename = f"{base_filename}.pdf"
    output_path = os.path.join(temp_dir, output_filename)

    try:
        # Guardar el archivo subido en el disco temporal
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Comando para ejecutar LibreOffice en modo headless
        # --convert-to pdf: Especifica el formato de salida
        # --outdir <dir>: Especifica el directorio de salida
        # <input_path>: Archivo de entrada
        command = [
            "libreoffice",
            "--headless",
            "--writer",
            "--convert-to",
            "pdf",
            "--outdir",
            temp_dir,
            input_path,
        ]

        # Ejecutar el proceso de conversión
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30  # Timeout de 30 segundos para evitar procesos colgados
        )

        # Verificar si la conversión fue exitosa
        if process.returncode != 0:
            error_message = process.stderr.decode("utf-8")
            raise HTTPException(
                status_code=500,
                detail=f"Error durante la conversión con LibreOffice: {error_message}",
            )

        if not os.path.exists(output_path):
            raise HTTPException(
                status_code=500,
                detail="El archivo convertido no se encontró después de la ejecución.",
            )

        # Devolver el archivo PDF. FastAPI se encarga de la limpieza del FileResponse.
        return FileResponse(
            path=output_path,
            media_type="application/pdf",
            filename=output_filename,
        )

    except Exception as e:
        # Captura cualquier excepción no esperada para un logging más detallado
        raise HTTPException(status_code=500, detail=f"Un error inesperado ocurrió: {str(e)}")

    finally:
        # Asegurar la limpieza del directorio temporal y todos sus contenidos
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)