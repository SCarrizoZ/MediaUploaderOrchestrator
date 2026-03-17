import json
import os

import logging

from libs.cloudinary_manager import CloudinaryManager
from libs.utils import sync_and_deploy_web
from libs.cover_manager import process_cover

class MetadataManagerCore:

    def _process_image_upload(self, current_url, show_name, season=None):
        """
        Delega el procesamiento de la imagen al gestor compartido.
        """
        return process_cover(current_url, show_name, season, self.config, self.logger)
    def __init__(self, db_path="data/web_database.json", metadata_path="data/series_metadata.json"):
        self.db_path = db_path
        self.metadata_path = metadata_path 
        
        self.db_data = []
        self.metadata = {}
        self.shows_list = []
        self.shows_seasons_map = {}
        
        # Cargar config para Cloudinary
        try:
            with open("config/config.json", "r") as f:
                self.config = json.load(f)
        except Exception:
            self.config = {}
            
        self.cloudinary = CloudinaryManager(self.config)
        self.logger = logging.getLogger("MetadataManager")

    def load_data(self):
        """Lee la BD para encontrar series y carga los metadatos existentes."""
        if os.path.exists(self.db_path):
            with open(self.db_path, 'r', encoding='utf-8') as f:
                self.db_data = json.load(f)
        
        shows_temp = {}
        for session in self.db_data:
            for reaction in session.get('reactions', []):
                show = reaction.get('show_id', '').strip()
                if not show:
                    show = reaction.get('show', '').strip().upper() # fallback

                season = reaction.get('season')
                season = str(season).strip() if season is not None else ""
                
                if not show:
                    continue
                if not season:
                    season = "1"

                if show not in shows_temp:
                    shows_temp[show] = set()
                shows_temp[show].add(season)
        
        self.shows_list = sorted(list(shows_temp.keys()))
        self.shows_seasons_map = {}
        for k, v in shows_temp.items():
            try:
                sorted_seasons = sorted(list(v), key=lambda x: int(x) if x.isdigit() else x)
            except Exception:
                sorted_seasons = sorted(list(v))
            self.shows_seasons_map[k] = sorted_seasons

        if os.path.exists(self.metadata_path):
            try:
                with open(self.metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
            except json.JSONDecodeError:
                self.metadata = {}
        else:
            self.metadata = {}

    def save_metadata(self):
        """Guarda los cambios en el JSON."""
        try:
            with open(self.metadata_path, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error guardando: {e}")
            return False

    def update_show_data(self, show_name, data):
        """Actualiza los datos de un show específico. El key siempre es el slugificado."""
        from libs.utils import slugify
        slug = slugify(show_name)
        if 'title' not in data:
            data['title'] = show_name.strip()
        self.metadata[slug] = data
        return self.save_metadata()

    def get_series_info(self, name):
        """Retorna la info de la serie por nombre exacto o por slug."""
        if not name:
            return None
        from libs.utils import slugify
        slug = slugify(name)
        
        # Primero intentar por slug directo
        if slug in self.metadata:
            return self.metadata[slug]
            
        # Fallback: buscar si por alguna razon está guardada textualmente (migracion pre-existente o manual)
        return self.metadata.get(name.upper())



    def bulk_cloud_sync(self, progress_callback=None):
        """
        Recorre todos los metadatos, sube imagenes pendientes y sincroniza con Web.
        """
        changes_made = False
        total_items = len(self.metadata)
        processed = 0

        self.logger.info("🚀 Iniciando Sincronización Masiva...")

        for show_name, data in self.metadata.items():
            processed += 1
            if progress_callback: 
                progress_callback(processed, total_items, f"Procesando: {show_name}")

            # 1. Portada Global
            cover = data.get("cover_url", "")
            new_cover, changed = self._process_image_upload(cover, show_name)
            if changed:
                data["cover_url"] = new_cover
                changes_made = True
            
            # 2. Portadas por Temporada
            seasons = data.get("seasons", {})
            for s_num, s_data in seasons.items():
                s_cover = s_data.get("cover_url", "")
                new_s_cover, s_changed = self._process_image_upload(s_cover, show_name, s_num)
                if s_changed:
                    s_data["cover_url"] = new_s_cover
                    changes_made = True

        # Guardar JSON si hubo cambios
        if changes_made:
            self.save_metadata()
            self.logger.info("💾 Metadatos y portadas actualizados localmente.")
        else:
            self.logger.info("✅ No se requirieron actualizaciones.")

        # Sincronizar Web (Copy + Push)
        
        if progress_callback:
            progress_callback(total_items, total_items, "Sincronizando con Web (Git Push)...")
        
        success = sync_and_deploy_web(push_to_git=True)
        
        return success, changes_made