import os
import threading
import time
import socket

from libs.telegram_client import TelegramUploader
from libs.okru_client import OkruUploader
from libs.youtube_client import YoutubeUploader
from libs.cloudinary_manager import CloudinaryManager
from libs.utils import sync_and_deploy_web, slugify, generate_youtube_description
from libs.thumbnail_manager import process_thumbnail

class UploadOrchestrator:
    def __init__(self, config, logger, persistence_manager):
        self.config = config
        self.logger = logger
        self.pm = persistence_manager
        self._stop_event = threading.Event()
        
        # Init Cloudinary
        self.cloudinary = CloudinaryManager(config)

    def stop(self):
        self.logger.warning("🛑 Solicitud de cancelación recibida...")
        self._stop_event.set()

    def _check_internet(self, host="8.8.8.8", port=53, timeout=3):
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except socket.error: return False

    def _wait_for_internet(self):
        retries = 0
        while not self._check_internet() and not self._stop_event.is_set():
            self.logger.warning(f"⚠️ Sin internet. Reintentando... ({retries+1}/10)")
            time.sleep(10)
            retries += 1
            if retries >= 10:
                self.logger.error("❌ Abortado por falta de red.")
                return False
        return not self._stop_event.is_set()

    def run_upload_process(self, upload_job_data, close_chrome_after=True, ui_callbacks=None):
        self._stop_event.clear()
        session = upload_job_data["session_info"]
        files = upload_job_data["files"]

        # 1. Preparar Estructura Base del Evento DB Web
        web_db_event = {
            "streamer": session.get("streamer"), "date_str": session.get("date"),
            "youtube_vod": {
                "filename": session.get("youtube_vod_filename"),
                "status": "pending", "video_id": "", "url": "", "chapters": session.get("youtube_chapters", [])
            },
            "reactions": []
        }

        # Inicializar Clientes
        log_queue = getattr(self.logger.handlers[1], 'log_queue', None) if len(self.logger.handlers) > 1 else None
        
        needs_ok = any(f[1].get('dest_ok') for f in files)
        needs_yt = any(f[1].get('is_youtube') for f in files)
        
        yt_client = YoutubeUploader(self.config, log_queue) if needs_yt else None
        ok_client = OkruUploader(self.config, log_queue) if needs_ok else None
        tg_client = TelegramUploader(self.config, log_queue) 

        try:
            vod_entry = next((f for f in files if f[1].get('is_youtube') and f[1].get('meta_type') == "Compilado"), None)
            reaction_entries = [f for f in files if not (f[1].get('is_youtube') and f[1].get('meta_type') == "Compilado")]

            # ==========================================================
            # PASO 1: YOUTUBE VOD (Opcional)
            # ==========================================================
            if vod_entry and yt_client and not self._stop_event.is_set():
                self.logger.info("=== 🚀 PASO 1: YOUTUBE VOD ===")
                path, info = vod_entry
                filename = os.path.basename(path)

                if self.pm.is_uploaded(filename, 'youtube'):
                    self.logger.info("   ⏭️ VOD ya en YouTube.")
                    web_db_event["youtube_vod"]["status"] = "uploaded"
                else:
                    if self._wait_for_internet():
                        # Generemos la string final a partir de los chapters justo antes de la subida
                        desc_str = generate_youtube_description(session.get("streamer"), session.get("date"), session.get("youtube_chapters", []))
                        vid = yt_client.upload_video(path, description=desc_str)
                        if vid and vid != "QUOTA_LIMIT":
                            self.pm.register_successful_upload(filename, 'youtube')
                            web_db_event["youtube_vod"].update({"status": "uploaded", "video_id": vid, "url": f"https://youtu.be/{vid}"})
                        else:
                            web_db_event["youtube_vod"]["status"] = "failed" if vid != "QUOTA_LIMIT" else "quota_exceeded"
                
                # Update parcial
                self.pm.register_session_event(web_db_event)

            if self._stop_event.is_set(): return

            # ==========================================================
            # PASO 2: OK.RU
            # ==========================================================
            if reaction_entries and ok_client and not self._stop_event.is_set():
                self.logger.info("=== 🚀 PASO 2: OK.RU (REACCIONES) ===")
                try:
                    for i, (path, info) in enumerate(reaction_entries):
                        if self._stop_event.is_set(): break
                        if not info.get('dest_ok'): continue

                        filename = os.path.basename(path)
                        if self.pm.is_uploaded(filename, 'okru'):
                            self.logger.info(f"   ⏭️ (OK) {filename} ya subido.")
                            continue

                        self.logger.info(f"   📤 (OK) Subiendo {i+1}/{len(reaction_entries)}: {filename}")
                        if self._wait_for_internet():
                            def ok_cb(p, t):
                                if ui_callbacks and 'tg_progress' in ui_callbacks:
                                    ui_callbacks['tg_progress'](None, t)
                            success, vid_id = ok_client.upload_video(path, gui_callback=ok_cb)
                            if success and vid_id:
                                self.pm.register_successful_upload(filename, 'okru')
                                info['ok_id'] = vid_id
                finally:
                    if close_chrome_after:
                        self.logger.info("🛑 Cerrando Chrome...")
                        ok_client.close()

            if self._stop_event.is_set(): return

            # ==========================================================
            # PASO 3: THUMBNAILS & CLOUDINARY & DB UPDATE
            # ==========================================================
            self.logger.info("=== 🚀 PASO 3: THUMBNAILS & DATA PREP ===")
            
            for path, info in reaction_entries:
                if self._stop_event.is_set(): break
                
                # Delegar en el gestor de thumbnails
                cloud_url = process_thumbnail(path, self.cloudinary, self.logger)
                
                # 3c. Construir entrada DB
                filename = os.path.basename(path)
                ok_status = "uploaded" if self.pm.is_uploaded(filename, 'okru') else "failed"
                if not info.get('dest_ok'): ok_status = "skipped"
                
                ok_url = f"https://ok.ru/video/{info.get('ok_id', '')}" if info.get('ok_id') else ""

                r_entry = {
                    "filename": filename,
                    "show_id": slugify(info.get('meta_show', '')), 
                    "episode": info.get('meta_ep', ''),
                    "season": info.get('meta_season') if info.get('meta_season') else None,
                    "ok_status": ok_status,
                    "ok_url": ok_url,
                    "thumbnail_url": cloud_url,
                    "tg_status": "pending" if info.get('dest_tg') else "skipped"
                }
                web_db_event["reactions"].append(r_entry)

            # Persistir datos locales (con Telegram pendiente)
            self.pm.register_session_event(web_db_event)

            # ==========================================================
            # PASO 4: TELEGRAM
            # ==========================================================
            self.logger.info("=== 🚀 PASO 4: TELEGRAM ===")
            
            # Actualizar estado a uploaded conforme avanzamos
            
            for i, (path, info) in enumerate(reaction_entries):
                if self._stop_event.is_set(): break
                if not info.get('dest_tg'): continue

                filename = os.path.basename(path)
                
                if self.pm.is_uploaded(filename, 'telegram'):
                     self.logger.info(f"   ⏭️ (TG) {filename} ya subido.")
                     # Actualizar estado en memoria
                     for r in web_db_event["reactions"]:
                         if r["filename"] == filename: r["tg_status"] = "uploaded"
                     continue

                self.logger.info(f"   📤 (TG) Subiendo {i+1}/{len(reaction_entries)}: {filename}")
                if self._wait_for_internet():
                    cb = ui_callbacks.get('tg_progress') if ui_callbacks else None
                    success, sent_messages = tg_client.upload_video(path, f"Reacción: {info['name']}", gui_callback=cb)
                    
                    if success and sent_messages:
                        self.pm.register_successful_upload(filename, 'telegram')
                        
                        # Construir objeto de metadatos de Telegram
                        telegram_data = {
                            "status": "uploaded",
                            "uploaded_messages": []
                        }
                        
                        for msg in sent_messages:
                            try:
                                # Intento de extraer datos seguros
                                msg_data = {
                                    "message_id": msg.id,
                                    "file_unique_id": getattr(msg.file, 'id', 'unknown'),
                                    "file_size": getattr(msg.file, 'size', 0),
                                    "date": msg.date.isoformat() if hasattr(msg, 'date') else ""
                                }
                                telegram_data["uploaded_messages"].append(msg_data)
                            except Exception as e:
                                self.logger.error(f"⚠️ Error extrayendo info del mensaje TG: {e}")

                        # Actualizar en memoria y PERSISTIR INMEDIATAMENTE
                        for r in web_db_event["reactions"]:
                            if r["filename"] == filename: 
                                r["tg_status"] = "uploaded"
                                r["telegram_data"] = telegram_data
                        
                        # Guardado Crítico
                        self.pm.register_session_event(web_db_event)
                        self.logger.info(f"   💾 Metadata Telegram guardada para {filename}")
                    
                    if cb: cb(0, "") # Reset bar

            # ==========================================================
            # PASO 5: GUARDADO FINAL LOCAL & SYNC CON PUSH
            # ==========================================================
            self.logger.info("=== 🏁 PASO 5: ACTUALIZACIÓN FINAL LOCAL Y SINCRONIZACIÓN WEB ===")
            
            # Guardamos estado final de Telegram en DB local
            self.pm.register_session_event(web_db_event)
            
            if not self._stop_event.is_set():
                sync_and_deploy_web(push_to_git=True)
            else:
                self.logger.warning("⚠️ Saltando Sync Web por parada solicitada.")

        except Exception as e:
            self.logger.error(f"❌ Error Orquestador: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if tg_client: tg_client.disconnect()
            self.logger.info("🏁 Proceso Finalizado.")