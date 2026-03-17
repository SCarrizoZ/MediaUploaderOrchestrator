import os
import time
import random
import http.client
import httplib2
import logging

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .utils import setup_logger

# Scopes necesarios para subir videos
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

class YoutubeUploader:
    def __init__(self, config, log_queue=None):
        self.logger = setup_logger("YouTube", log_queue)
        self.secrets_file = os.path.abspath("config/client_secrets.json")
        self.token_file = os.path.abspath("config/token.json") # Usaremos el formato estándar de Google
        self.api_service_name = "youtube"
        self.api_version = "v3"
        self.service = None

    def _get_authenticated_service(self):
        """Maneja la autenticación OAuth2 nativa."""
        creds = None
        
        # 1. Cargar token existente
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            except Exception as e:
                self.logger.warning(f"⚠️ Token corrupto, se recreará: {e}")

        # 2. Si no hay credenciales válidas, loguear
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                self.logger.info("🔄 Refrescando token de YouTube...")
                try:
                    creds.refresh(Request())
                except Exception:
                    self.logger.warning("⚠️ Fallo al refrescar. Se requiere login nuevo.")
                    creds = None

            if not creds:
                if not os.path.exists(self.secrets_file):
                    self.logger.error("❌ Falta client_secrets.json")
                    return None
                
                self.logger.info("🔐 Iniciando autorización OAuth...")
                flow = InstalledAppFlow.from_client_secrets_file(self.secrets_file, SCOPES)
                # Esto abrirá el navegador localmente
                creds = flow.run_local_server(port=0)
            
            # Guardar credenciales para la próxima
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        try:
            return build(self.api_service_name, self.api_version, credentials=creds, cache_discovery=False)
        except Exception as e:
            self.logger.error(f"❌ Error construyendo servicio API: {e}")
            return None

    def upload_video(self, file_path, description="Uploaded via Python"):
        """Sube el video usando subida resumible (chunks)."""
        if not os.path.exists(file_path): return False
        
        # 1. Autenticar
        if not self.service:
            self.service = self._get_authenticated_service()
        if not self.service: return False

        title = os.path.splitext(os.path.basename(file_path))[0].replace('_', ' ')
        self.logger.info(f"🚀 Iniciando subida nativa: {title}")

        # 2. Preparar Cuerpo de la Petición
        body = {
            'snippet': {
                'title': title[:100],
                'description': description,
                'categoryId': '22' # Gente y Blogs
            },
            'status': {
                'privacyStatus': 'unlisted',
                'selfDeclaredMadeForKids': False
            }
        }

        # 3. Preparar Archivo (Chunk size = 4MB * multiplicador)
        chunk_size = 4 * 1024 * 1024 # 4MB por chunk
        media = MediaFileUpload(file_path, chunksize=chunk_size, resumable=True, mimetype='video/mp4')

        # 4. Crear solicitud de inserción
        insert_request = self.service.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        # 5. Bucle de Subida (Resumable)
        response = None
        error = None
        retry = 0
        
        while response is None:
            try:
                status, response = insert_request.next_chunk()
                
                if status:
                    progress = int(status.progress() * 100)
                    # Loguear progreso cada 20% para no saturar
                    if progress % 20 == 0:
                        self.logger.info(f"   📊 Subiendo YouTube: {progress}%")
                        
            except HttpError as e:
                if e.resp.status in [500, 502, 503, 504]:
                    error = f"Error recuperable API: {e}"
                    retry += 1
                else:
                    self.logger.error(f"🛑 Error API fatal: {e}")
                    return False
            except (httplib2.HttpLib2Error, IOError, http.client.NotConnected, http.client.IncompleteRead) as e:
                error = f"Error de red: {e}"
                retry += 1
            
            if error:
                if retry > 10:
                    self.logger.error("❌ Demasiados reintentos. Abortando.")
                    return False
                
                wait_time = (2 ** retry) + random.random()
                self.logger.warning(f"⚠️ {error}. Reintentando en {wait_time:.1f}s...")
                time.sleep(wait_time)
                error = None # Reset error

        # 6. Finalización
        if response and 'id' in response:
            video_id = response['id']
            self.logger.info(f"✅ Subida exitosa. ID: {video_id}")
            return video_id
        else:
            self.logger.error("❌ Respuesta inesperada al finalizar subida.")
            return False