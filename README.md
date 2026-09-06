# AutoPKT

Aplicación de escritorio en Python/PySide6 para convertir una imagen de una topología en un archivo de Cisco Packet Tracer, con configuración opcional.

## Instalación

Requiere Python 3.10 o posterior. Desde la raíz del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe interfaz.py
```

En macOS/Linux, sustituye `.venv\Scripts\python.exe` por `.venv/bin/python`.

Crea `.env` en la raíz (está excluido de Git):

```dotenv
GEMINI_API_KEY=tu_clave
GEMINI_MODEL=gemini-2.5-flash
```

`GEMINI_MODEL` es opcional y permite seleccionar un modelo disponible en tu cuenta. La API recibe la imagen al pulsar **Analizar imagen**, con un tiempo de espera de 90 segundos por solicitud. Un fallo de autenticación, disponibilidad o formato se muestra en la interfaz y permite reintentar. No hay llamadas a la API durante las pruebas automatizadas.

Adaptador basado en el [SDK oficial de Google Gen AI](https://github.com/googleapis/python-genai) y la [referencia generateContent](https://ai.google.dev/api/generate-content).

## Flujo

1. **Cargar imagen:** selecciona PNG, JPG o WEBP, analiza y revisa los dispositivos detectados. La API produce conexiones y posiciones, que se validan antes de cargar la topología. No se requieren CSV de conexiones o posiciones del usuario.
2. **Configurar (opcional):** define segmentos por rama, combina direcciones automáticas, manuales e importadas, selecciona protocolos por router y pulsa **Generar IP y validar configuración**. Revisa las direcciones resultantes en la tabla inferior.
3. **Crear archivo:** guarda `.pkt` o exporta exactamente **cisco.md** (switches y routers) y **pcs.md** (PCs y servidores con IP/máscara/puerta de enlace).

Puedes saltar directamente de la primera pestaña a la tercera. La casilla **Incluir la configuración validada** permite elegir explícitamente el modo de salida. Sin configuración, los equipos conservan sus enlaces y posiciones pero no reciben IP, VLAN adicionales ni protocolos. Los Markdown también reflejan ese modo.

Seleccionar otra imagen reinicia la sesión. Editar segmentos, IP o protocolos invalida la configuración anterior; hay que validarla otra vez para incluirla en la salida. Los errores de validación no aplican cambios parciales.

## Segmentos e IP

- Cada rama/router tiene una cantidad de segmentos editable. Los campos CIDR vacíos reciben redes automáticas; los no vacíos se respetan.
- Las redes manuales deben ser direcciones de red, por ejemplo `192.168.10.0/24`, no `192.168.10.25/24`.
- La asignación automática utiliza subredes `/24` libres en `10.0.0.0/8`; los enlaces entre routers usan `/30`. Primero se reservan todas las redes manuales e importadas, incluidos los enlaces entre routers.
- Se rechazan segmentos repetidos o superpuestos, IP duplicadas, máscaras inválidas, direcciones de red/broadcast, conflictos con la puerta de enlace y segmentos sin capacidad suficiente.
- El primer segmento corresponde a VLAN 1 y contiene la administración de los switches. Los segmentos siguientes corresponden a VLAN 2, 3, etc. Los equipos finales se reparten de forma circular entre ellos; una IP manual/importada determina el segmento del equipo.
- La primera IP de cada segmento se reserva para la puerta de enlace del router. Se puede cambiar la de la interfaz física mediante una IP manual o importada de esa interfaz.
- Las IP importadas pueden introducir segmentos nuevos en los campos automáticos disponibles. Si no hay espacio, aumenta la cantidad de segmentos o modifica los CIDR. Una IP importada no reemplaza silenciosamente una red manual.
- Las LAN sin router también se admiten y no reciben una puerta de enlace ficticia.

CSV de IP, con encabezado opcional, UTF-8, máscara decimal o prefijo:

```csv
dispositivo,ip,mascara
PC1,192.168.10.10,255.255.255.0
SW1,192.168.10.2,/24
R1@GigabitEthernet0/0,192.168.10.254,24
```

Usa los nombres exactos mostrados en la tabla. Los routers necesitan el nombre de la interfaz porque pueden tener más de una IP. Las filas importadas sustituyen las de esos dispositivos; las demás IP manuales permanecen. Puedes editar los valores antes de validar. Deja IP y máscara vacías para asignación automática.

## Protocolos y límites del generador

Cada router admite **Sin protocolo**, **OSPF** (proceso 1, área 0), **RIP v2** o **EIGRP** (AS 100). No se limita artificialmente la cantidad de protocolos distintos, pero no se generan rutas por defecto ni redistribución entre protocolos distintos. Elegirlos no garantiza conectividad entre esos dominios.

La detección de ramas reutiliza el recorrido del grafo existente. Una LAN compartida por varias interfaces/routers puede generarse sin configuración, pero la configuración automática la rechaza con un mensaje explícito: resolverla requiere definir el diseño de capa 2 y las puertas de enlace redundantes, que no se infieren de la imagen. Varias VLAN requieren al menos un switch. El generador mantiene sus límites de puertos y rechaza topologías que los superan.

Los nombres que devuelve la API se restringen a letras ASCII, números, guion y guion bajo, empezando por letra. No se permiten archivos arbitrarios ni instrucciones de la imagen como respuesta ejecutable.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las pruebas cubren validación y combinación de direccionamiento, VLAN, protocolos, carga de otra topología, los dos modos de salida, parsing de respuesta de API, exportación Markdown y acciones de la interfaz. Los PKT se descodifican y se comprueba su XML; esto no sustituye abrirlos en la versión de Packet Tracer utilizada por el usuario.

`tests/test_ui.py` utiliza Qt sin ventana visible y guarda capturas en `artifacts/` (excluido de Git). El aspecto usa tonos claros, navegación oscura y acentos verde agua/coral, con títulos ligeros y espaciados inspirados en las referencias visuales.

## Organización

- `interfaz.py`: entrada de la aplicación.
- `UI/main_window.py`: flujo de tres pestañas y análisis en segundo plano.
- `UI/theme.py`: tema de escritorio.
- `api_gemini/procesador.py`: llamada a Gemini y validación de archivos devueltos.
- `core/workflow.py`: sesión de topología, validación y planificación transaccional, exportación Markdown.
- `core/`: dispositivos, conexiones y detección de ramas existentes.
- `core_xml/main.py`: generación de XML/PKT y comandos Cisco reutilizados por Markdown.

Las páginas antiguas se conservan como referencia; la ventana principal usa el nuevo flujo.
