import json
import os
import shutil
import uuid
from datetime import datetime

class PersistenceManager:
    """
    Gestor Unificado de Datos (Single Source of Truth).
    Maneja: Series (UI), Uploads (Técnico), Web DB (Negocio), Sesiones (Recovery).
    """
    def __init__(self, base_path="data"):
        self.base_path = base_path
        self.files = {
            "series": os.path.join(base_path, "series_history_v2.json"),
            "uploads": os.path.join(base_path, "upload_history.json"),
            "web_db": os.path.join(base_path, "web_database.json"),
            "session": os.path.join(base_path, "last_session.json")
        }
        self.data = {"series": {}, "uploads": {}, "web_db": []}
        self._load_all()

    def _load_all(self):
        for key, filepath in self.files.items():
            if key == "session": continue
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = json.load(f)
                        if key == "web_db" and not isinstance(content, list): content = []
                        if key != "web_db" and not isinstance(content, dict): content = {}
                        self.data[key] = content
                except Exception as e:
                    print(f"⚠️ Error cargando {key}: {e}")
                    self.data[key] = [] if key == "web_db" else {}
            else:
                self.data[key] = [] if key == "web_db" else {}

    def _save(self, key):
        filepath = self.files[key]
        try:
            if os.path.exists(filepath): shutil.copy2(filepath, filepath + ".bak")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.data[key], f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Error guardando {key}: {e}")

    # --- SERIES & UPLOADS (Helpers simples) ---
    def get_series_list(self): 
        titles = []
        for slug, data in self.data["series"].items():
            if "title" in data:
                titles.append(data["title"])
            else:
                titles.append(slug)
        return sorted(list(set(titles)))
    
    def get_last_series_info(self, name):
        from libs.utils import slugify
        slug = slugify(name)
        
        # Intentar por slug (formato nuevo)
        if slug in self.data["series"]:
            return self.data["series"][slug]
            
        # Fallback 1: intentar por el nombre exacto (formato viejo)
        if name in self.data["series"]:
            return self.data["series"][name]
            
        # Fallback 2: buscar iterando por si hay un 'title' que coincida
        for key, data in self.data["series"].items():
            if isinstance(data, dict) and data.get("title") == name:
                return data
                
        return {"season": "", "episode": "", "material_type": "Gameplay"}

    def get_streamer_history(self):
        """Devuelve una lista ordenada y única de todos los streamers registrados en la base de datos."""
        streamers = set()
        for session in self.data["web_db"]:
            streamer = session.get("streamer")
            if streamer:
                streamers.add(streamer.strip().upper())
        return sorted(list(streamers))

    def update_series_info(self, name, season, episode, material_type="Gameplay"):
        from libs.utils import slugify
        slug = slugify(name)
        self.data["series"][slug] = {
            "title": name,
            "season": season, "episode": episode, "material_type": material_type,
            "updated": datetime.now().isoformat()
        }
        self._save("series")

    def is_uploaded(self, filename, platform):
        return self.data["uploads"].get(f"{filename}_{platform}", False)

    def register_successful_upload(self, filename, platform):
        self.data["uploads"][f"{filename}_{platform}"] = True
        self._save("uploads")

    # --- NUEVA LÓGICA DE BASE DE DATOS WEB (Relacional) ---
    def register_session_event(self, session_data):
        """
        Registra un evento completo (VOD + Reacciones).
        Busca si ya existe la sesión (por Streamer + Fecha) para actualizarla, o crea una nueva.
        """
        # Claves compuestas para identificar la sesión única
        target_streamer = session_data.get("streamer")
        target_date = session_data.get("date_str")

        if not target_streamer or not target_date:
            return # Sin fecha ni streamer no podemos indexar

        # Buscar índice existente comparando Streamer Y Fecha (Ignorando mayúsculas/minúsculas)
        idx = next((i for i, x in enumerate(self.data["web_db"]) 
                    if x.get("streamer", "").lower() == target_streamer.lower() 
                    and x.get("date_str", "").lower() == target_date.lower()), None)

        if idx is not None:
            # --- ACTUALIZAR EXISTENTE ---
            existing = self.data["web_db"][idx]
            
            # 1. Actualizar VOD (Solo si el nuevo trae datos relevantes)
            new_vod = session_data.get("youtube_vod", {})
            if new_vod and new_vod.get("filename"): 
                # Si traemos un VOD nuevo, sobrescribimos. 
                # Si no (porque se omitió), mantenemos el que estaba (si había).
                existing["youtube_vod"].update(new_vod)
            
            # 2. Actualizar reacciones (Merge inteligente por nombre de archivo)
            new_reactions = session_data.get("reactions", [])
            existing_reactions = existing.get("reactions", [])
            
            for new_r in new_reactions:
                # Buscamos si esta reacción específica ya existe en la lista
                r_idx = next((i for i, r in enumerate(existing_reactions) if r["filename"] == new_r["filename"]), None)
                if r_idx is not None:
                    existing_reactions[r_idx].update(new_r)
                else:
                    existing_reactions.append(new_r)
            
            existing["reactions"] = existing_reactions
            
            # Actualizar timestamp de modificación
            existing["updated_at"] = datetime.now().isoformat()
            
            self.data["web_db"][idx] = existing
        else:
            # --- CREAR NUEVO ---
            if "id" not in session_data: session_data["id"] = str(uuid.uuid4())
            if "created_at" not in session_data: session_data["created_at"] = datetime.now().isoformat()
            
            # Asegurar estructura mínima si el VOD viene vacío
            if not session_data.get("youtube_vod"):
                session_data["youtube_vod"] = {
                    "filename": None, "status": "skipped", "video_id": "", "url": ""
                }

            self.data["web_db"].append(session_data)

        self._save("web_db")

    # --- SESIONES (Recovery) ---
    def save_session(self, segments, source_file_path):
        session = {"source": source_file_path, "ts": datetime.now().isoformat(), "segments": segments}
        try:
            with open(self.files["session"], 'w', encoding='utf-8') as f:
                json.dump(session, f, indent=4)
        except: pass

    def load_session(self):
        if os.path.exists(self.files["session"]):
            try:
                with open(self.files["session"], 'r') as f: return json.load(f)
            except: pass
        return None