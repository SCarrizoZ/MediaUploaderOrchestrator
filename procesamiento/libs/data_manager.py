import json
import os
from datetime import datetime

class DataManager:
    def __init__(self, base_path):
        self.history_file = os.path.join(base_path, "series_history_v2.json")
        self.web_db_file = os.path.join(base_path, "web_database.json")
        self.load_history()

    def load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history_data = json.load(f)
            except Exception:
                pass
                self.history_data = {}
        else:
            self.history_data = {}

    def save_history(self):
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history_data, f, indent=4, ensure_ascii=False)

    def get_series_list(self):
        """Retorna lista de nombres visuales de series (TITLES) para el Combobox"""
        # Como iteramos sobre dict values, sacamos los 'title' existentes
        titles = []
        for slug, data in self.history_data.items():
            if "title" in data:
                titles.append(data["title"])
            else:
                titles.append(slug)
        return sorted(list(set(titles)))

    def get_last_info(self, series_name):
        """Retorna la última temporada, capítulo y tipo de material de una serie basándose en su nombre"""
        from libs.utils import slugify
        slug = slugify(series_name)
        
        # Intentar por slug (formato nuevo)
        if slug in self.history_data:
            return self.history_data[slug]
            
        # Fallback 1: intentar por el nombre exacto (formato viejo)
        if series_name in self.history_data:
            return self.history_data[series_name]
            
        # Fallback 2: buscar iterando por si hay un 'title' que coincida
        for key, data in self.history_data.items():
            if isinstance(data, dict) and data.get("title") == series_name:
                return data
                
        return {
            "season": "", 
            "episode": "",
            "material_type": "Gameplay"  # Valor por defecto
        }

    def update_series_info(self, series_name, season, episode, material_type="Gameplay"):
        """Actualiza la memoria de la serie guardada bajo un slug."""
        from libs.utils import slugify
        slug = slugify(series_name)
        self.history_data[slug] = {
            "title": series_name,
            "season": season,
            "episode": episode,
            "material_type": material_type,
            "updated": datetime.now().isoformat()
        }
        self.save_history()

    # --- BASE DE DATOS WEB ---
    def register_upload(self, file_info):
        """
        Registra un video procesado para la futura web.
        file_info espera: {
            filename, streamer, show, season, episode, 
            material_type,  # NUEVO
            telegram_status, okru_status
        }
        """
        db_data = []
        if os.path.exists(self.web_db_file):
            try:
                with open(self.web_db_file, 'r', encoding='utf-8') as f:
                    db_data = json.load(f)
            except: pass

        # Agregar timestamp y campos adicionales
        file_info["created_at"] = datetime.now().isoformat()
        file_info["okru_link"] = ""  # Pendiente de sync
        
        # Asegurar que material_type existe
        if "material_type" not in file_info:
            file_info["material_type"] = "N/A"
        
        db_data.append(file_info)

        with open(self.web_db_file, 'w', encoding='utf-8') as f:
            json.dump(db_data, f, indent=4, ensure_ascii=False)