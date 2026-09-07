import os
import re
import time
from PIL import Image
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError

def procesar_topologia_red(ruta_img_topologia, carpeta_destino="data"):
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("No se encontró GEMINI_API_KEY. Revisa tu archivo .env en la raíz del proyecto.")
    client = genai.Client(api_key=api_key)
    if not os.path.exists(ruta_img_topologia):
        raise FileNotFoundError(f"No se encontró la imagen de topología en: {ruta_img_topologia}")
    img_topologia = Image.open(ruta_img_topologia)
    prompt = """
    Analiza la imagen adjunta de la topología de red y genera 2 archivos CSV.
    > PARA pos.csv:
    segun la imagen, quiero que generes una lista en formato csv, con formato: <nombre dispositivo>,<pos x>,<pos y> esto es para cisco packet tracer, asi que toma en cuenta eso para asignar las posiciones de modo que no se sobrepongan, al final las posiciones deben formar la misma que de la imagen
    las posiciones minimamente deben ser a partir de 100,100 para adelante, no hay posiciones negativas
    > PARA conexiones.csv:
    segun la imagen quiero que generes un csv que indique las conexiones entre los dispositivos, con el siguiente formato: 
    -  <nombre_device1>:< tipo_device1>,<tipo_cable>,<nombre_device2>:< tipo_device2>
    - Ejemplo: PC1:pc,c,SW2:sw
    los cables que existen son: 
    - cs: cobre segmentado (líneas punteadas entre switches)
    - c: cobre (línea sólida)
    - s: serial (entre routers)
    no omitas la existencia de 'cobre segmentado' de existir, debes indicarlo.
    los tipo device son:
    - r: Router
    - sw: Switch
    - pc: PC 
    - srv: Servidor

    Genera ÚNICAMENTE los bloques de código CSV sin texto explicativo.
    no agreges encabezados ni comentarios dentro de los .csv
    Para el analisis solo toma en cuenta los tipos de dispositivos mencionados, si ves modems internet u otros no los tomes en cuenta, y su nombre si es que se indica en la imagen, no tomes en cuenta las ips, vlans o interfaces
    """
    config = types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=16384
    )
    modelos_a_probar = [
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite"
    ]
    response = None
    indice = 0
    while True:
        modelo = modelos_a_probar[indice]
        try:
            print(f"Intentando enviar solicitud a la API con el modelo: {modelo}...")
            response = client.models.generate_content(
                model=modelo,
                contents=[img_topologia, prompt],
                config=config
            )
            print(f"Respuesta recibida exitosamente con {modelo}")
            break  
        except APIError as e:
            # Captura errores de saturación (503/429/UNAVAILABLE) o modelo no encontrado (404)
            if any(err in str(e) for err in ["503", "UNAVAILABLE", "429", "404", "NOT_FOUND"]):
                print(f"El modelo {modelo} falló o no está disponible ({e}). Avanzando al siguiente...")
            else:
                print(f"Error inesperado en {modelo}: {e}. Reintentando con el siguiente...")
            indice = (indice + 1) % len(modelos_a_probar)
    os.makedirs(carpeta_destino, exist_ok=True)
    patron = r"### ARCHIVO:\s*([\w\.-]+)\s*```(?:csv)?\n(.*?)```"
    bloques = re.findall(patron, response.text, re.DOTALL)
    if not bloques:
        patron_alt = r"```(?:csv)?\n(.*?)```"
        bloques_raw = re.findall(patron_alt, response.text, re.DOTALL)
        nombres = ["pos.csv", "conexiones.csv"]
        bloques = list(zip(nombres, bloques_raw))
    archivos_generados = []
    for nombre_archivo, contenido in bloques:
        ruta_salida = os.path.join(carpeta_destino, nombre_archivo.strip())
        with open(ruta_salida, "w", encoding="utf-8") as f:
            f.write(contenido.strip() + "\n")
        archivos_generados.append(ruta_salida)
        print(f"Archivo generado: {ruta_salida}")
    if hasattr(response, 'usage_metadata'):
        print("\n--- Métricas de la Consulta ---")
        print(f"Tokens Entrada: {response.usage_metadata.prompt_token_count}")
        print(f"Tokens Salida: {response.usage_metadata.candidates_token_count}")
        print(f"Total Tokens: {response.usage_metadata.total_token_count}")
    return archivos_generados