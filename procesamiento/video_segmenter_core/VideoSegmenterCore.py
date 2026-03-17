import os
import uuid
import re
import logging
from libs.persistence_manager import PersistenceManager
from libs.utils import setup_logger
from libs.video_engine import VideoEngine
from libs.upload_orchestrator import UploadOrchestrator
from libs.name_parser import parse_filename, parse_show_info
from libs.utils import MESES_ES
from libs.utils import CONTENT_TYPE as TIPOS_MATERIAL

class VideoSegmenterCore:
    """
    Coordinador Principal.
    - Gestiona estado (segmentos, archivo).
    - Persistencia (Sessions, History).
    - Control (Start/Stop procesos).
    """
    def __init__(self, log_queue=None):
        self.log_queue = log_queue
        self.logger = setup_logger("Core", self.log_queue)
        
        # --- Estado del Archivo Actual ---
        self.source_file = ""
        self.duration_sec = 0.0
        self.file_size_bytes = 0
        self.segments = [] 
        
        # --- Subsistemas ---
        # 1. Persistencia Unificada
        try:
            self.pm = PersistenceManager("data")
            self.logger.info("💾 PersistenceManager cargado correctamente.")
        except Exception as e: 
            self.logger.error(f"❌ Error fatal cargando PersistenceManager: {e}")
            self.pm = None

        # 2. Motor de Video
        self.video_engine = VideoEngine(self.logger)
        
        # 3. Orquestador (se instancia bajo demanda, pero mantenemos referencia para poder detenerlo)
        self.upload_orchestrator = None 

    # ==========================================
    # 1. GESTIÓN DE ARCHIVOS Y METADATOS
    # ==========================================

    def load_video(self, filename):
        try:
            info = self.video_engine.get_video_info(filename)
            
            self.source_file = filename
            self.duration_sec = info['duration']
            self.file_size_bytes = info['size']
            
            # Intentar recuperar sesión previa si es el mismo archivo
            # (Opcional: podrías implementar aquí la lógica de "Continuar sesión anterior")
            self.segments = [] 
            
            return {
                "duration": self.duration_sec,
                "size": self.file_size_bytes,
                "filename": os.path.basename(filename)
            }
        except Exception as e:
            self.logger.error(f"Error en load_video: {e}")
            raise e

    def parse_filename_smart(self, filename):
        """Wrapper over libs/name_parser.py para la retrocompatibilidad con la UI de Video Segmenter"""
        return parse_filename(filename, history_data=None)

    def parse_series_info(self, text):
        """Wrapper over libs/name_parser.py"""
        return parse_show_info(text, history_data=None)

    # Wrappers para la UI usando PersistenceManager
    def get_series_history(self):
        return self.pm.get_series_list() if self.pm else []

    def get_last_series_info(self, series_name):
        return self.pm.get_last_series_info(series_name) if self.pm else {}

    def get_streamer_history(self):
        return self.pm.get_streamer_history() if self.pm else []

    def update_series_info_db(self, show, season, ep, m_type):
        if self.pm and show:
            self.pm.update_series_info(show, season, ep, m_type)

    # ==========================================
    # 2. CRUD DE SEGMENTOS
    # ==========================================

    def add_segment(self, start, end, name, opts, meta):
        if start >= end: raise ValueError("Inicio >= Fin")

        should_save = opts.get('save_db', True)

        if meta['show'] and opts['ok'] and should_save:
            self.update_series_info_db(meta['show'], meta['season'], meta['ep'], meta['type'])

        new_seg = {
            'id': str(uuid.uuid4()), 
            'start': start, 'end': end, 'name': name,
            'dest_ok': opts.get('ok', True), 'dest_tg': opts.get('tg', True), 'yt_cut': opts.get('yt_cut', True),
            'save_db': should_save, 'meta_show': meta.get('show', ''), 'meta_season': meta.get('season', ''),
            'meta_ep': re.sub(r'\s*-\s*', '-', str(meta.get('ep', '')).strip()), 'meta_type': meta.get('type', TIPOS_MATERIAL[0])
        }
        self.segments.append(new_seg)
        self.segments.sort(key=lambda x: x['start'])
        return new_seg

    def update_segment(self, seg_id, start, end, name, opts, meta):
        if start >= end: raise ValueError("Inicio >= Fin")
        for seg in self.segments:
            if seg['id'] == seg_id:
                seg.update({
                    'start': start, 'end': end, 'name': name,
                    'dest_ok': opts.get('ok'), 'dest_tg': opts.get('tg'), 'yt_cut': opts.get('yt_cut'), 'save_db': opts.get('save_db', True),
                    'meta_type': meta.get('type')
                })
                if 'show' in meta: seg['meta_show'] = meta['show']
                if 'season' in meta: seg['meta_season'] = meta['season']
                if 'ep' in meta: 
                    # Normalize "1 - 5" to "1-5"
                    seg['meta_ep'] = re.sub(r'\s*-\s*', '-', str(meta['ep']).strip())
                return True
        return False

    def delete_segments_by_id(self, ids_list):
        self.segments = [s for s in self.segments if s['id'] not in ids_list]

    def get_segment_by_id(self, seg_id):
        return next((s for s in self.segments if s['id'] == seg_id), None)

    # ==========================================
    # 3. PROCESAMIENTO Y CONTROL
    # ==========================================

    def stop_processing(self):
        """Detiene el orquestador si está corriendo."""
        if self.upload_orchestrator:
            self.logger.warning("🛑 Enviando señal de parada al Orquestador...")
            self.upload_orchestrator.stop()
        else:
            self.logger.info("ℹ️ No hay procesos activos para detener.")

    def process_all(self, out_dir, config, options, ui_callbacks=None):
        if not self.segments and not options.get('allow_empty', False):
            self.logger.warning("No hay cortes para procesar.")
            return

        self.logger.info("⚙️ Iniciando procesamiento (Core V8.5)...")
        
        # Guardar sesión actual por seguridad (Recovery Point)
        if self.pm: self.pm.save_session(self.segments, self.source_file)

        files_to_upload = []      
        report_reacciones = []
        
        try:
            # --- FASE 1: CORTAR VIDEOS ---
            self.logger.info("✂️ Fase 1: Generando clips de video...")
            for seg in self.segments:
                clean_name = seg['name']
                out_path = os.path.join(out_dir, f"{clean_name}.mp4")
                
                # Check si archivo ya existe para no re-procesar (Opcional, ayuda en crashes)
                if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
                    self.video_engine.cut_segment(
                        self.source_file, seg['start'], seg['end'], out_path, 
                        precise_mode=options['precise_mode'], hw_accel=options['hw_accel']
                    )
                else:
                    self.logger.info(f"   ⏭️ Clip ya existe (saltando render): {clean_name}")
                
                files_to_upload.append((out_path, seg))
                report_reacciones.append(seg)

            # --- FASE 2: COMPILADO YOUTUBE ---
            youtube_ts = []
            yt_path = None

            if options.get('gen_youtube'):
                self.logger.info("🎬 Fase 2: Compilando VOD YouTube...")
                yt_name = f"{options['streamer_name']} {options['date_str']} VOD".strip().upper()
                
                # Generar video
                youtube_ts, yt_path = self.video_engine.generate_youtube_compilation(
                    self.source_file, out_dir, yt_name,
                    [s for s in self.segments if s['yt_cut']], 
                    self.duration_sec, options['quality_yt'], options['hw_accel']
                )

                # Construir arreglo Chapters para la DB
                yt_chapters = []
                if youtube_ts:
                    for item in youtube_ts:
                        hms = self.sec_to_hms(item['yt_time'])
                        skipped = self.sec_to_hms(item['skipped'])
                        yt_chapters.append({
                            "timestamp": hms,
                            "title": item['name'],
                            "skipped": skipped
                        })

                if yt_path and os.path.exists(yt_path):
                    self.logger.info(f"   ✅ VOD Listo: {os.path.basename(yt_path)}")
                    yt_info = {
                        'name': yt_name, 'dest_ok': False, 'dest_tg': False, 
                        'is_youtube': True, 'meta_type': "Compilado"
                    }
                    files_to_upload.append((yt_path, yt_info))

            self._write_report(out_dir, report_reacciones, youtube_ts, yt_name)

            # --- FASE 3: SUBIDA INTELIGENTE ---
            if options.get('auto_upload'):
                # Instanciar Orquestador
                self.upload_orchestrator = UploadOrchestrator(config, self.logger, self.pm)
                
                # Datos estructurados para la nueva DB relacional
                upload_job_data = {
                    "session_info": {
                        "streamer": options['streamer_name'],
                        "date": options['date_str'],
                        "youtube_vod_filename": os.path.basename(yt_path) if yt_path else None,
                        "youtube_chapters": yt_chapters
                    },
                    "files": files_to_upload
                }
                
                self.upload_orchestrator.run_upload_process(
                    upload_job_data,
                    close_chrome_after=options['close_chrome'],
                    ui_callbacks=ui_callbacks
                )
            else:
                self.logger.info("🏁 Procesamiento finalizado (Subida omitida).")

        except Exception as e:
            self.logger.error(f"❌ Error crítico en process_all: {e}")
            raise e

    def _write_report(self, out_dir, segmentos, youtube_ts, filename_base):
        try:
            path = os.path.join(out_dir, f"{filename_base}.txt")
            with open(path, 'w', encoding='utf-8') as f:
                f.write("TIMESTAMPS PARA YOUTUBE\n=======================\n\n")
                if youtube_ts:
                    for item in youtube_ts:
                        f.write(f"{self.sec_to_hms(item['yt_time'])} - {item['name']}\n")
                else:
                    f.write("(No se generaron cortes)\n")
                f.write("\nLISTA DE REACCIONES:\n")
                for s in segmentos:
                    f.write(f"{self.sec_to_hms(s['start'])} - {s['name']}\n")
            self.logger.info(f"📄 Reporte generado: {os.path.basename(path)}")
        except: pass

    # Utils
    def snap_to_keyframes(self, current_time): return self.video_engine.snap_to_keyframes(self.source_file, current_time)
    def sec_to_hms(self, s): return self.video_engine.sec_to_hms(s)
    def hms_to_sec(self, h): return self.video_engine.hms_to_sec(h)