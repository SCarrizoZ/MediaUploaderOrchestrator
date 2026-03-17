import json
import os
import shutil
from datetime import datetime

from libs.data_manager import DataManager

class DatabaseManagerCore:
    def __init__(self, db_path="data/web_database.json"):
        self.db_path = db_path
        self.data = []
        self.dm = DataManager(os.path.dirname(db_path))
        self.load_db()

    def load_db(self):
        """Carga la base de datos JSON en memoria."""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"❌ Error cargando DB: {e}")
                self.data = []
        else:
            self.data = []

    def save_db(self):
        """Guarda los cambios en el JSON, creando primero un backup .bak."""
        # 1. Crear Backup de seguridad
        if os.path.exists(self.db_path):
            try:
                shutil.copy(self.db_path, self.db_path + ".bak")
            except Exception as e:
                print(f"⚠️ No se pudo crear backup: {e}")
        
        # 2. Guardar JSON
        try:
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Error guardando DB: {e}")

    def sync_to_cloud(self):
        """Sincroniza la BD a github/public_data."""
        from libs.utils import sync_and_deploy_web
        return sync_and_deploy_web(push_to_git=True, source_dir="data")

    def process_pending_thumbnails(self):
        """Busca thumbnails pendientes en JSON y los sube a Cloudinary."""
        from libs.thumbnail_manager import process_static_thumbnail
        from libs.cloudinary_manager import CloudinaryManager
        
        config = {}
        if os.path.exists('config/config.json'):
            try:
                with open('config/config.json') as f: config = json.load(f)
            except: pass
            
        cloudinary_mgr = CloudinaryManager(config)
        if not cloudinary_mgr.enabled: return
        
        updated = False
        import logging
        logger = logging.getLogger("DatabaseManagerCore")
        
        for session in self.data:
            reactions = session.get("reactions", [])
            for r in reactions:
                t_url = r.get("thumbnail_url", "")
                if t_url:
                    # Chequear si debe subirse a Cloudinary (no cloduinary y no relativo local).
                    if not t_url.startswith("http") and not t_url.startswith("/"):
                        pass # Local absolute path
                    elif t_url.startswith("http") and "res.cloudinary.com" not in t_url:
                        pass # External URL, non-cloudinary
                    else:
                        continue
                    
                    logger.info(f"Subiendo thumbnail pendiente: {t_url}")
                    new_url = process_static_thumbnail(t_url, cloudinary_mgr)
                    if new_url:
                        r["thumbnail_url"] = new_url
                        updated = True
        
        if updated:
            self.save_db()

    # ==========================================================
    # LECTURA (READ)
    # ==========================================================
    def get_all_sessions(self):
        """Devuelve la lista completa de sesiones para poblar el árbol."""
        # Aseguramos cargar la última versión por si hubo cambios externos
        self.load_db() 
        return self.data
        
    def get_streamer_history(self):
        """Devuelve una lista ordenada y única de todos los streamers registrados en la base de datos."""
        streamers = set()
        for session in self.data:
            streamer = session.get("streamer")
            if streamer:
                streamers.add(streamer.strip().upper())
        return sorted(list(streamers))
        
    def get_series_history(self):
        """Devuelve la lista de series para el combobox."""
        return self.dm.get_series_list() if hasattr(self, 'dm') else []
        
    def get_last_info(self, show_id):
        """Devuelve la información de la última reacción de la serie (temporada, episodio, tipo)."""
        return self.dm.get_last_info(show_id) if hasattr(self, 'dm') else {}

    def get_item_data(self, session_idx, reaction_idx=None):
        """
        Obtiene los datos. MODIFICADO: Ahora incluye URLs y IDs crudos.
        """
        if session_idx >= len(self.data): return None
        
        session = self.data[session_idx]
        
        if reaction_idx is None:
            # --- Retornar datos de la SESIÓN (VOD) ---
            vod = session.get("youtube_vod", {})
            return {
                "type": "session",
                "streamer": session.get("streamer", ""),
                "date_str": session.get("date_str", ""),
                "vod_filename": vod.get("filename") or "",
                "vod_status": vod.get("status", "pending"),
                "vod_id": vod.get("video_id", ""),
                "vod_url": vod.get("url", ""),       # <--- AGREGADO
                "vod_chapters": vod.get("chapters", []),
                "raw_json": session                  # <--- AGREGADO (Para vista JSON)
            }
        else:
            # --- Retornar datos de la REACCIÓN ---
            reactions = session.get("reactions", [])
            if reaction_idx >= len(reactions): return None
            r = reactions[reaction_idx]
            
            result = {
                "type": "reaction",
                "filename": r.get("filename", ""),
                "show_id": r.get("show_id", ""),
                "season": r.get("season", ""),
                "episode": r.get("episode", ""),
                "material_type": r.get("material_type", "Otro"),
                "ok_status": r.get("ok_status", "pending"),
                "tg_status": r.get("tg_status", "pending"),
                "ok_url": r.get("ok_url", ""),       # <--- AGREGADO
                "ok_id": r.get("ok_id", ""),         # <--- AGREGADO
                "tg_message_id": r.get("tg_message_id", ""),
                "tg_file_unique_id": r.get("tg_file_unique_id", ""),
                "tg_file_size": r.get("tg_file_size", ""),
                "tg_split_parts": r.get("tg_split_parts", ""),
                "thumbnail_url": r.get("thumbnail_url", ""),
                "raw_json": r                        # <--- AGREGADO (Para vista JSON)
            }
            
            # Since material_type was moved to series_metadata.json, query it if missing or "Otro"
            if result["material_type"] == "Otro" and hasattr(self, 'dm'):
                info = self.dm.get_last_info(result["show_id"])
                if "material_type" in info:
                    result["material_type"] = info["material_type"]
                    
            return result

    # ==========================================================
    # ACTUALIZACIÓN (UPDATE)
    # ==========================================================
    def update_session(self, idx, new_data):
        """Actualiza los metadatos de una sesión y su VOD."""
        if idx >= len(self.data): return False
        
        session = self.data[idx]
        
        # Actualizar Datos Básicos
        session["streamer"] = new_data.get("streamer", session["streamer"]).strip().upper()
        session["date_str"] = new_data.get("date_str", session["date_str"]).strip().upper()
        
        # Actualizar Datos VOD (Manteniendo estructura)
        if "youtube_vod" not in session: session["youtube_vod"] = {}
        vod = session["youtube_vod"]
        
        vod["filename"] = new_data.get("vod_filename") or None
        vod["status"] = new_data.get("vod_status", "pending")
        vod["video_id"] = new_data.get("vod_id", "").strip()
        
        # Guardar chapters directamente (ya viene parseado desde la UI)
        vod["chapters"] = new_data.get("vod_chapters", [])
        
        # Lógica inteligente: Si hay ID, generar URL automáticamente
        if vod["video_id"]:
            vod["url"] = f"https://youtu.be/{vod['video_id']}"
        elif not vod["video_id"]:
            vod["url"] = ""

        # Actualizar timestamp interno
        session["updated_at"] = datetime.now().isoformat()
        
        self.save_db()
        return True

    def update_reaction(self, session_idx, reaction_idx, new_data):
        """Actualiza los metadatos. MODIFICADO: Guarda URLs."""
        if session_idx >= len(self.data): return False
        reactions = self.data[session_idx].get("reactions", [])
        if reaction_idx >= len(reactions): return False
        
        r = reactions[reaction_idx]
        
        # Actualizamos campos
        r["filename"] = new_data.get("filename", r["filename"])
        
        # Guardar en show_id asegurándonos de que sea un slug
        from libs.utils import slugify
        raw_show = new_data.get("show_id", "")
        if not raw_show: raw_show = new_data.get("show", "") # Fallback por si UI envia 'show'
        r["show_id"] = slugify(raw_show)
        season = new_data.get("season", "")
        r["season"] = str(season).strip().upper() if season is not None else ""
        r["episode"] = new_data.get("episode", "").strip().upper()
        r["material_type"] = new_data.get("material_type", "Otro")
        r["ok_status"] = new_data.get("ok_status", "pending")
        r["tg_status"] = new_data.get("tg_status", "pending")
        
        # --- NUEVOS CAMPOS DE URL Y TG ---
        r["ok_url"] = new_data.get("ok_url", "").strip()
        # Si cambiamos la URL manualmente, intenta extraer el ID si es posible (opcional)
        if "ok_id" in new_data:
             r["ok_id"] = new_data.get("ok_id", "").strip()
             
        # Guardar metadatos técnicos de Telegram
        if "tg_message_id" in new_data: r["tg_message_id"] = new_data.get("tg_message_id", "").strip()
        if "tg_file_unique_id" in new_data: r["tg_file_unique_id"] = new_data.get("tg_file_unique_id", "").strip()
        if "tg_file_size" in new_data: r["tg_file_size"] = new_data.get("tg_file_size", "").strip()
        if "tg_split_parts" in new_data: r["tg_split_parts"] = new_data.get("tg_split_parts", "").strip()
        
        # Guardar thumbnail (si viene en data)
        if "thumbnail_url" in new_data:
             r["thumbnail_url"] = new_data.get("thumbnail_url", "").strip()
        
        self.save_db()
        return True

    # ==========================================================
    # CREACIÓN (CREATE)
    # ==========================================================
    def create_session(self, streamer="NUEVO STREAMER", date="01 ENERO 2026"):
        """Crea una nueva sesión vacía al principio de la lista."""
        new_entry = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S"), # ID único simple
            "created_at": datetime.now().isoformat(),
            "streamer": streamer,
            "date_str": date,
            "youtube_vod": {
                "filename": None, 
                "status": "pending", 
                "video_id": "", 
                "url": "", 
                "chapters": []
            },
            "reactions": []
        }
        self.data.insert(0, new_entry) # Insertar al inicio para verla rápido
        self.save_db()
        return 0 # Retorna índice 0 (el nuevo)

    def create_reaction(self, session_idx):
        """Añade una reacción vacía a la sesión indicada."""
        if session_idx >= len(self.data): return False
        
        new_reac = {
            "filename": "video_nuevo.mp4",
            "show_id": "nueva-serie", 
            "episode": "1", 
            "material_type": "Otro",
            "ok_status": "pending", 
            "tg_status": "pending"
        }
        
        if "reactions" not in self.data[session_idx]:
            self.data[session_idx]["reactions"] = []
            
        self.data[session_idx]["reactions"].append(new_reac)
        self.save_db()
        return True

    # ==========================================================
    # ELIMINACIÓN (DELETE)
    # ==========================================================
    def delete_item(self, session_idx, reaction_idx=None):
        """Elimina una sesión completa o una reacción específica."""
        if session_idx >= len(self.data): return False
        
        if reaction_idx is None:
            # Borrar Sesión Completa
            del self.data[session_idx]
        else:
            # Borrar Reacción específica
            reactions = self.data[session_idx].get("reactions", [])
            if reaction_idx >= len(reactions): return False
            del reactions[reaction_idx]
            
        self.save_db()
        return True