import os
import re
import threading
from libs.persistence_manager import PersistenceManager
from libs.data_manager import DataManager
from libs.upload_orchestrator import UploadOrchestrator
from libs.utils import setup_logger
from libs.name_parser import parse_filename, parse_show_info

class ManualUploadCore:
    def __init__(self, log_queue=None):
        self.logger = setup_logger("ManualCore", log_queue)
        self.pm = PersistenceManager("data")
        self.dm = DataManager("data")
        self.orchestrator = None
        self.is_processing = False

    # ==========================================================
    # 1. PARSEO INTELIGENTE DE NOMBRES
    # ==========================================================
    def parse_filename(self, file_path):
        """Wrapper de libs/name_parser.py para la UI de Manual Uploader"""
        # Extraemos historial para mejorar la heurística de adivinacion
        history = self.pm.data.get("series", {}) if self.pm and self.pm.data else {}
        return parse_filename(file_path, history_data=history)

    def _parse_show_info(self, text):
        """Wrapper de libs/name_parser.py para la UI de Manual Uploader"""
        history = self.pm.data.get("series", {}) if self.pm and self.pm.data else {}
        return parse_show_info(text, history_data=history)

    # ==========================================================
    # 2. FUNCIONES DE AYUDA (Autocompletado y Archivos)
    # ==========================================================
    def get_auto_description(self, video_path):
        """Busca si existe un .txt con el mismo nombre que el video."""
        base_path = os.path.splitext(video_path)[0]
        txt_path = base_path + ".txt"
        if os.path.exists(txt_path):
            try:
                with open(txt_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                self.logger.error(f"Error parseando descripciones {e}")
        return ""

    def check_upload_status(self, filename, platform):
        """Consulta al PersistenceManager si ya se subió."""
        from libs.utils import slugify
        parsed_info = self.parse_filename(filename)
        slug_show = slugify(parsed_info.get("show", ""))
        
        for sess in self.pm.data["web_db"]:
            for r in sess.get("reactions", []):
                if r.get("show_id") == slug_show and str(r.get("episode")) == str(parsed_info.get("episode")):
                    # Check the actual platform status in the DB
                    if platform == "okru" and r.get("ok_status") == "uploaded": return True
                    if platform == "telegram" and r.get("tg_status") == "uploaded": return True
        return False

    def get_series_history(self):
        """Devuelve historial para autocompletar comboboxes."""
        return self.dm.get_series_list()

    def get_streamer_history(self):
        """Devuelve historial de streamers desde web_db para autocompletar."""
        return self.pm.get_streamer_history()

    def get_last_info(self, series_name):
        """Devuelve info de la última vez que se subió esa serie."""
        return self.dm.get_last_info(series_name)

    # ==========================================================
    # 3. EJECUCIÓN DEL ORQUESTADOR
    # ==========================================================
    def _parse_youtube_chapters(self, desc_text):
        chapters = []
        if not desc_text: return chapters
        
        lines = desc_text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line: 
                continue
            if "REACCIONES EN ESTE VIDEO" in line.upper() or "LISTA DE REACCIONES" in line.upper():
                break # Solo procesamos la primera parte (timestamps con saltados)
            
            # Formato: 00:00:00 - TITULO [Saltado: 00:15:00]
            if line[0].isdigit() and '-' in line:
                parts = line.split('-', 1)
                timestamp = parts[0].strip()
                rest = parts[1].strip()
                
                title = rest
                skipped = ""
                if "[Saltado:" in rest or "[saltado:" in rest.lower():
                    m = re.search(r'\[[Ss]altado:\s*(.*?)\]', rest)
                    if m:
                        skipped = m.group(1).strip()
                        title = re.sub(r'\s*\[[Ss]altado:.*?\]', '', rest).strip()
                        
                chapters.append({
                    "timestamp": timestamp,
                    "title": title,
                    "skipped": skipped
                })
        return chapters

    def start_upload(self, config, job_config, ui_callbacks):
        """
        Construye el diccionario maestro y lanza el UploadOrchestrator.
        
        job_config espera:
        {
            "streamer": "TUTIS", "date": "01 ENERO 2026",
            "vod": { "path": "...", "desc": "...", "enabled": True },
            "reactions": [
                { "path": "...", "show": "...", "ep": "...", "type": "...", 
                  "ok": True, "tg": True }
            ],
            "close_chrome": True
        }
        """
        if self.is_processing:
            self.logger.warning("⚠️ Ya hay un proceso activo.")
            return

        self.is_processing = True
        
        # 1. Preparar lista de archivos para el Orquestador
        files_to_upload = []

        # A) VOD Compilado
        vod_data = job_config.get("vod", {})
        if vod_data.get("enabled") and vod_data.get("path"):
            vod_path = vod_data["path"]
            if os.path.exists(vod_path):
                files_to_upload.append((vod_path, {
                    "is_youtube": True,
                    "meta_type": "Compilado",
                    "dest_ok": False, # VODs no suelen ir a OK/TG en este flujo
                    "dest_tg": False
                }))

        # B) Reacciones
        for r in job_config.get("reactions", []):
            if os.path.exists(r["path"]):
                meta = {
                    "is_youtube": False,
                    "name": os.path.basename(r["path"]), # Nombre para Telegram
                    "meta_show": r.get("show", ""),
                    "meta_season": r.get("season", ""),
                    "meta_ep": r.get("ep", ""),
                    "meta_type": r.get("type", "Otro"),
                    "dest_ok": r.get("ok", False),
                    "dest_tg": r.get("tg", False)
                }
                files_to_upload.append((r["path"], meta))
                
                # Update series history
                if meta["meta_show"] and meta["dest_ok"]:
                    self.pm.update_series_info(meta["meta_show"], meta["meta_season"], meta["meta_ep"], meta["meta_type"])

        # 2. Estructura Maestra
        upload_job_data = {
            "session_info": {
                "streamer": job_config["streamer"],
                "date": job_config["date"],
                "youtube_vod_filename": os.path.basename(vod_data["path"]) if vod_data.get("enabled", False) and vod_data.get("path") else None,
                "youtube_chapters": self._parse_youtube_chapters(vod_data.get("desc", ""))
            },
            "files": files_to_upload
        }

        # 3. Lanzar en hilo separado
        threading.Thread(target=self._run_orchestrator, args=(config, upload_job_data, job_config["close_chrome"], ui_callbacks)).start()

    def _run_orchestrator(self, config, data, close_chrome, callbacks):
        try:
            self.orchestrator = UploadOrchestrator(config, self.logger, self.pm)
            self.orchestrator.run_upload_process(data, close_chrome_after=close_chrome, ui_callbacks=callbacks)
        except Exception as e:
            self.logger.error(f"❌ Error crítico en ManualCore: {e}")
        finally:
            self.is_processing = False
            if callbacks.get("on_finish"):
                callbacks["on_finish"]()

    def stop(self):
        if self.orchestrator:
            self.orchestrator.stop()