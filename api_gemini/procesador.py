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
    Usa exactamente este formato de encabezados con bloques de código Markdown:
    ### ARCHIVO: pos.csv
    <nombre_dispositivo>,<pos_x>,<pos_y>
    Asigna posiciones estimadas para formar la misma estructura de la imagen en X e Y para Cisco Packet Tracer de modo que no se sobrepongan entre dispositivos y tengan una separacion aceptable. Minimamente deben estar distribuidos desde la posicion (100,100) hacia adelante, sin tener posiciones negativas

    ### ARCHIVO: conexiones.csv
    <nombre_device1>:<tipo_device1>,<tipo_cable>,<nombre_device2>:<tipo_device2>
    Tipos de cable:
    - cs: cobre segmentado (líneas punteadas entre switches)
    - c: cobre (línea sólida)
    - s: serial (entre routers)
    Tipos de dispositivo: r (router), sw (switch o hubs), pc (PC), srv (Servidor).

    Genera ÚNICAMENTE los bloques de código CSV sin texto explicativo.
    no agreges encabezados ni comentarios dentro de los .csv
    """

    config = types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=16384
    )

    modelos_a_probar = [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
    ]

    response = None

    for modelo in modelos_a_probar:
        try:
            print(f"Intentando enviar solicitud a la API con el modelo: {modelo}...")
            response = client.models.generate_content(
                model=modelo,
                contents=[img_topologia, prompt],
                config=config
            )
            print(f"Respuesta recibida exitosamente con {modelo}")
            break  # Éxito: salimos del bucle
            
        except APIError as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e) or "429" in str(e):
                print(f"El modelo {modelo} está saturado o no disponible (Error). Probando con el siguiente modelo...")
                time.sleep(2)
                continue
            else:
                raise e

    if not response:
        raise RuntimeError("Ninguno de los modelos de respaldo pudo completar la solicitud debido a alta demanda.")

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
