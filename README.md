# 🎬 MediaUploader Orchestrator
 
![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Required-green.svg)
![Selenium](https://img.shields.io/badge/Selenium-Automated-orange.svg)
![Telethon](https://img.shields.io/badge/Telethon-Telegram-blue.svg)
 
**MediaUploader Orchestrator** es una solución *end-to-end* diseñada para automatizar la captura, edición, procesamiento, gestión de metadatos y distribución de contenido de video a múltiples plataformas (YouTube, OK.ru, Telegram, Cloudinary).
 
> 💡 **Nota de contexto:** Este es un proyecto de uso puramente personal diseñado para optimizar un flujo de trabajo específico (utilizando una arquitectura estilo Jamstack / GitOps para la actualización sin bases de datos en la nube de un sitio web estático). Se encuentra público a modo de portafolio para demostrar la capacidad de orquestación, integración de APIs, concurrencia y manejo de arquitectura de datos.
 
---
 
## 🚀 Características Principales
 
El sistema se divide en un *pipeline* de dos etapas principales: **Ingesta** y **Procesamiento/Distribución**, ambas conectadas a través de librerías *core* compartidas.
 
### 1. Ingesta Inteligente (`SmartStreamRecorder`)
 
- **Monitoreo Automático:** Detecta cuando un canal de Twitch entra en directo usando un *wrapper* de `streamlink`.
- **Detección de Anuncios:** Analiza los logs en tiempo real de `streamlink` (mediante un *daemon thread*) para generar reportes exactos con los *timestamps* de los anuncios, facilitando los cortes posteriores.
- **Manejo de Sesión:** Soporta reconexiones automáticas, interrupciones de stream y segmenta los videos por partes (con un *timeout* configurable de 15 minutos).
- **Sanitización FFmpeg (Nuclear Patch):** Ejecuta un proceso en lote que repara automáticamente problemas de desincronización de *timestamps* (`-fflags +genpts`) y compatibilidad de códecs H.264 en los archivos `.ts`.
 
### 2. Procesamiento y Edición
 
Ofrece dos interfaces gráficas (GUI) construidas con Tkinter según la necesidad del flujo de trabajo:
 
- **Video Segmenter UI:** Un editor de video con línea de tiempo. Permite definir cortes precisos, asignar metadatos a cada segmento, ajustarse al *keyframe* más cercano y exportar usando aceleración por hardware (NVENC). También genera automáticamente una compilación de video omitiendo segmentos marcados (ideal para evitar *strikes* en YouTube).
- **Manual Uploader UI:** Interfaz diseñada para la carga por lotes de archivos de video (VODs) y reacciones ya procesadas. Facilita la edición rápida de metadatos (serie, temporada, episodio) apoyada en un autocompletado inteligente en base al historial del motor de datos.
 
### 3. Orquestación Multi-Plataforma (`UploadOrchestrator`)
 
Un orquestador central asíncrono y tolerante a fallos que distribuye el contenido en 5 fases lógicas, garantizando consistencia (incluso ante reinicios o interrupciones):
 
1. **YouTube (VOD):** Sube el video principal compilado a YouTube mediante la API de Google y recupera el ID generado.
2. **OK.ru (Reacciones):** Automatización del navegador con Selenium WebDriver para subir los segmentos, sorteando la falta de API pública con un detector heurístico de *stalls* (cuelgues) de la interfaz.
3. **Cloudinary (Thumbnails):** Extrae *frames* clave de los videos, los optimiza a WebP y los sube al CDN de Cloudinary.
4. **Telegram (Respaldo):** Sube archivos usando Telethon, dividiendo automáticamente (mediante FFmpeg) los videos que superen el límite nativo de casi 2GB.
5. **Sincronización Web (GitOps):** Actualiza el JSON local (`web_database.json`) y realiza un *commit/push* automáticamente a un repositorio de Next.js para activar un redespliegue de la página web del proyecto.
 
---
 
## 🏗️ Arquitectura y Tecnologías
 
- **Lenguaje:** Python 3.8+
- **Procesamiento de Multimedia:** FFmpeg, FFprobe, Streamlink, Pillow (PIL)
- **Automatización Web:** Selenium WebDriver
- **APIs y SDKs:**
  - `telethon` / `FastTelethonhelper` (Telegram MTProto API)
  - `google-api-python-client` (YouTube Data API v3)
  - `cloudinary` (CDN y Transformación)
- **Capa de Persistencia:** Manejo centralizado tipo *Single Source of Truth* (`PersistenceManager`) para prevenir condiciones de carrera y gestionar respaldos automáticos `.bak` sobre los archivos JSON.
- **Concurrencia:** Uso extensivo de `threading`, `asyncio`, y `queue.Queue` para asegurar operaciones de I/O pesadas sin bloquear las interfaces gráficas.
 
---
 
## ⚙️ Instalación y Requisitos
 
### Prerrequisitos
 
1. [Python 3.8+](https://www.python.org/downloads/) instalado.
2. [FFmpeg](https://ffmpeg.org/download.html) instalado y agregado a las variables de entorno (PATH) del sistema.
3. Google Chrome instalado (para la automatización web).
 
### Instalación
 
1. Clona el repositorio:
 
```bash
git clone https://github.com/SCarrizoZ/MediaUploaderOrchestrator.git
cd MediaUploaderOrchestrator
```
 
2. Instala las dependencias requeridas:
 
```bash
pip install -r requirements.txt
```
 
---
 
## 🔒 Configuración de Entorno
 
Por seguridad, los secretos y tokens no se incluyen en el código fuente (están ignorados vía `.gitignore`). Para ejecutar el proyecto de manera local, se deben crear dos archivos:
 
#### 1. `ingestion/config_recorder.json`
 
Configuración del módulo de captura de streams:
 
```json
{
    "base_path": "D:/Ruta/A/Tus/Grabaciones",
    "quality": "best",
    "twitch_auth_token": "oauth:tu_token_de_twitch",
    "streamers_history": []
}
```
 
#### 2. `procesamiento/config/config.json`
 
Configuración del orquestador y credenciales para las distintas plataformas:
 
```json
{
  "telegram": {
    "api_id": "TU_API_ID",
    "api_hash": "TU_API_HASH",
    "session_name": "config/",
    "channel_id": "-100123456789"
  },
  "okru": {
    "profile_path": "config/chrome_profile_okru",
    "headless": false
  },
  "paths": {
    "backup_folder": "D:/Rutas/Backups"
  },
  "cloudinary": {
    "cloud_name": "CLOUD_NAME",
    "api_key": "API_KEY",
    "api_secret": "API_SECRET"
  }
}
```
 
> **Nota:** Para usar la API de YouTube, también debes colocar los archivos `client_secrets.json` y `token.json` generados en Google Cloud Console dentro del directorio `procesamiento/config/`.
 
---
 
## 💻 Uso
 
El repositorio cuenta con 3 puntos de entrada principales que operan como herramientas independientes:
 
**1. Monitoreo y Grabación de Twitch (Ingesta):**
 
```bash
python ingestion/SmartStreamRecorder.py
```
 
**2. Edición y Segmentación de VODs con línea de tiempo:**
 
```bash
python procesamiento/VideoSegmenterUI.py
```
 
**3. Carga masiva e introducción ágil de Metadatos:**
 
```bash
python procesamiento/ManualUploaderUI.py
```
