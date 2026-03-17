import subprocess
import os
import json
import logging
from libs.utils import slugify

logger = logging.getLogger("VideoUtils")

def get_video_duration(file_path):
    """Retorna la duración exacta en segundos (float) usando ffprobe."""
    try:
        cmd = [
            'ffprobe', 
            '-v', 'error', 
            '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', 
            file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"Error obteniendo duración de {file_path}: {e}")
        return 0.0

def generate_smart_thumbnail(video_path, output_dir, position_percent=0.45):
    """
    Genera un thumbnail jpg capturando el frame al X% de la duración.
    Esto evita fallos en videos muy cortos (ej < 5s).
    """
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        duration = get_video_duration(video_path)
        if duration <= 0: return None

        timestamp = duration * position_percent
        
        filename = slugify(os.path.splitext(os.path.basename(video_path))[0])
        output_path = os.path.join(output_dir, f"{filename}.jpg")

        # Comando FFmpeg para extraer 1 frame
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(timestamp),
            '-i', video_path,
            '-frames:v', '1',
            '-q:v', '2', # Calidad alta jpg
            output_path
        ]
        
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
        if os.path.exists(output_path):
            return output_path
        return None

    except Exception as e:
        logger.error(f"Error generando thumbnail para {video_path}: {e}")
        return None
