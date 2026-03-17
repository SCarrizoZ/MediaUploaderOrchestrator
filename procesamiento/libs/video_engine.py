import os
import json
import subprocess
from datetime import timedelta

class VideoEngine:
    """
    Especialista encargado exclusivamente del procesamiento de video.
    Maneja FFmpeg, ffprobe y manipulación de archivos de video.
    """
    def __init__(self, logger):
        self.logger = logger

    def get_video_info(self, filename):
        """Obtiene duración y tamaño del archivo."""
        if not os.path.exists(filename):
            raise FileNotFoundError("El archivo no existe.")
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', filename]
            dur = float(subprocess.check_output(cmd, creationflags=0x08000000).strip())
            size = os.path.getsize(filename)
            return {"duration": dur, "size": size}
        except Exception as e:
            self.logger.error(f"Error ffprobe: {e}")
            raise e

    def snap_to_keyframes(self, source_file, current_time_sec):
        """Encuentra el keyframe más cercano para cortes precisos."""
        try:
            cmd = [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0', 
                '-show_entries', 'frame=best_effort_timestamp_time,key_frame', 
                '-of', 'json', '-read_intervals', f'{current_time_sec}%+30', 
                source_file
            ]
            output = subprocess.check_output(cmd, creationflags=0x08000000).decode().strip()
            data = json.loads(output)
            
            keyframes = []
            for frame in data.get('frames', []):
                if frame.get('key_frame') == 1:
                    t = frame.get('best_effort_timestamp_time') or frame.get('pkt_pts_time')
                    if t: keyframes.append(float(t))

            if keyframes:
                return min(keyframes, key=lambda x: abs(x - current_time_sec))
            return None
        except Exception as e:
            self.logger.error(f"Error imantando: {e}")
            return None

    def cut_segment(self, source_file, start, end, out_path, precise_mode=False, hw_accel=True):
        """Corta un segmento de video."""
        cmd = ['ffmpeg', '-y']
        
        if precise_mode:
            if hw_accel: cmd.extend(['-hwaccel', 'cuda'])
            cmd.extend(['-ss', str(start), '-i', source_file, '-t', str(end - start)])
            
            if hw_accel:
                cmd.extend(['-c:v', 'h264_nvenc', '-preset', 'p4', '-b:v', '4500k'])
            else:
                cmd.extend(['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23'])
            cmd.extend(['-c:a', 'aac', '-b:a', '128k', out_path])
        else:
            # --- MODO HÍBRIDO (Rápido, Video Copy + Audio Recode) ---
            # Soluciona el desfase de audio (sync drift)

            # Input seeking para velocidad
            cmd.extend(['-ss', str(start), '-i', source_file, '-t', str(end - start)])

            cmd.extend([
                '-map', '0',                  # Mapear todos los streams
                '-c:v', 'copy',               # Copiar Video (NO RE-RENDER)
                '-c:a', 'aac',                # Re-codificar Audio (Arregla Sync)
                '-b:a', '192k',               # Bitrate decente
                '-avoid_negative_ts', 'make_zero', # Forzar timestamps limpios desde 0
                '-fflags', '+genpts',         # Regenerar puntos de tiempo
                out_path
            ])
        
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)

    def generate_youtube_compilation(self, source_file, out_dir, filename, segments_to_cut, total_duration, quality_setting, hw_accel=True):
        """
        Genera el video compilado para YouTube eliminando los segmentos marcados.
        Retorna: (lista_timestamps, ruta_archivo_final)
        """
        # Configuración de calidad
        bitrate = "4500k"
        if "Rápida" in quality_setting: bitrate = "2500k"
        elif "Alta" in quality_setting: bitrate = "6000k"
        
        scale_filter = None
        if "720p" in quality_setting: scale_filter = "scale=-2:720"
        elif "1080p" in quality_setting: scale_filter = "scale=-2:1080"

        # 1. Calcular qué partes MANTENER
        cuts = sorted(segments_to_cut, key=lambda x: x['start'])
        keep_parts = []
        current_pos = 0.0
        timestamps_report = []
        accumulated_duration = 0.0

        for cut in cuts:
            if cut['start'] > current_pos:
                duration = cut['start'] - current_pos
                keep_parts.append({'start': current_pos, 'end': cut['start'], 'dur': duration})
                accumulated_duration += duration
            
            timestamps_report.append({
                'yt_time': accumulated_duration,
                'name': cut['name'],
                'skipped': cut['end'] - cut['start']
            })
            current_pos = max(current_pos, cut['end'])
            
        if current_pos < total_duration:
            duration = total_duration - current_pos
            keep_parts.append({'start': current_pos, 'end': total_duration, 'dur': duration})

        if not keep_parts: return [], None

        # 2. Procesar partes temporales
        temp_files = []
        try:
            list_path = os.path.join(out_dir, "concat_list.txt")
            total_parts = len(keep_parts)
            
            for i, part in enumerate(keep_parts):
                if part['dur'] < 0.1: continue
                part_path = os.path.join(out_dir, f"temp_yt_part_{i}.ts")
                
                # --- INICIO ESTRATEGIA DE SEEKING HÍBRIDO ---
                # Definimos un margen de seguridad (ej: 30 segundos).
                # Esto asegura que el "salto rápido" caiga ANTES del Keyframe problemático.
                buffer_time = 30.0 
                
                # 1. Cálculo del Salto Rápido (Input Seek)
                # Si el corte es en el min 60:00, saltamos al 59:30.
                coarse_seek = max(0.0, part['start'] - buffer_time)
                
                # 2. Cálculo del Ajuste Fino (Output Seek)
                # Calculamos cuánto falta decodificar para llegar al punto exacto.
                fine_seek = part['start'] - coarse_seek
                
                cmd = ['ffmpeg', '-y']
                if hw_accel: cmd.extend(['-hwaccel', 'cuda'])
                
                # A) Aplicamos el Salto Rápido (Antes del input)
                # Esto es instantáneo.
                if coarse_seek > 0:
                    cmd.extend(['-ss', str(coarse_seek)])
                
                cmd.extend(['-i', source_file])
                
                # B) Aplicamos el Ajuste Fino (Después del input)
                # Esto obliga a FFmpeg a "leer" y decodificar esos 30 seg de buffer,
                # eliminando el congelamiento y asegurando precisión perfecta.
                cmd.extend(['-ss', str(fine_seek)])
                
                # C) Definimos la duración
                cmd.extend(['-t', str(part['dur'])])
                # --- FIN ESTRATEGIA ---

                if scale_filter: cmd.extend(['-vf', scale_filter])
                
                if hw_accel:
                    # Nota: Aumentamos un poco el bitrate para asegurar calidad en re-codificación
                    cmd.extend(['-c:v', 'h264_nvenc', '-preset', 'p4', '-b:v', bitrate])
                else:
                    cmd.extend(['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23'])
                
                # Audio: Recodificar siempre es buena práctica aquí para evitar glitches en uniones
                cmd.extend(['-c:a', 'aac', '-b:a', '128k', part_path])
                
                # Ejecución
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
                temp_files.append(part_path)

            # 3. Concatenar
            with open(list_path, 'w', encoding='utf-8') as f:
                for tf in temp_files:
                    safe = tf.replace(os.sep, '/').replace("'", "'\\''")
                    f.write(f"file '{safe}'\n")

            final_out = os.path.join(out_dir, f"{filename}.mp4")
            
            subprocess.run([
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', list_path, 
                '-c', 'copy', '-bsf:a', 'aac_adtstoasc', final_out
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)

            # Limpieza
            os.remove(list_path)
            for tf in temp_files:
                try: os.remove(tf)
                except: pass
            
            return timestamps_report, final_out

        except Exception as e:
            self.logger.error(f"Error en motor de video (YouTube): {e}")
            raise e

    # Utilidades estáticas
    @staticmethod
    def sec_to_hms(seconds):
        return str(timedelta(seconds=int(seconds)))
    
    @staticmethod
    def hms_to_sec(hms):
        try:
            parts = list(map(int, hms.split(':')))
            if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
            if len(parts) == 2: return parts[0]*60 + parts[1]
            return 0
        except: return 0