import os
import time
import logging
import threading
import shutil
import subprocess
import re
import unicodedata

# Configuración por defecto
PUBLIC_DATA_DIR = r"D:\Programas\PaginaWeb_ReaccionesTutis\public\data"

REPO_ROOT = r"D:\Programas\PaginaWeb_ReaccionesTutis"

CONTENT_TYPE = ["Gameplay", "Reacción", "Otro"]

MESES_ES = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL", 5: "MAYO", 6: "JUNIO",
    7: "JULIO", 8: "AGOSTO", 9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"
}

class QueueHandler(logging.Handler):
    """Envía logs a la cola de la GUI"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(record)

def setup_logger(name, log_queue=None):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers = [] # Limpiar previos

    # Formato
    formatter = logging.Formatter('%(asctime)s - [%(name)s] - %(message)s', datefmt='%H:%M:%S')

    # 1. Siempre a consola (CMD) por seguridad
    c_handler = logging.StreamHandler()
    c_handler.setFormatter(formatter)
    logger.addHandler(c_handler)

    # 2. A la GUI si existe cola
    if log_queue:
        q_handler = QueueHandler(log_queue)
        q_handler.setFormatter(formatter)
        logger.addHandler(q_handler)

    return logger

def is_file_stable(file_path, wait_seconds=3):
    if not os.path.exists(file_path): return False
    try:
        size1 = os.path.getsize(file_path)
        time.sleep(wait_seconds)
        size2 = os.path.getsize(file_path)
        return size1 == size2 and size1 > 0
    except: return False

def slugify(value):
    """
    Convierte un string a un slug amigable (útil para URLs o IDs).
    """
    if not value: return ""
    value = str(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')

def format_spanish_date(date_obj):
    """
    Formatea un objeto datetime a la string estándar del programa (Ej: 18 FEBRERO 2026).
    """
    if not date_obj: return ""
    try:
        month_str = MESES_ES.get(date_obj.month, "ENERO")
        return f"{date_obj.day:02d} {month_str} {date_obj.year}"
    except Exception:
        return str(date_obj)

def generate_youtube_description(streamer_name, date_str, chapters):
    """
    Toma los datos puros del JSON y construye el string con el formato
    exacto que requiere la descripción del video en YouTube.
    """
    if not chapters:
        return ""
        
    description_lines = ["TIMESTAMPS:\n"]
    
    for cap in chapters:
        line = f"{cap.get('timestamp', '')} - {streamer_name.upper()} {date_str.upper()} {cap.get('title', '')}"
        if cap.get('skipped'):
            line += f" [Saltado: {cap.get('skipped')}]"
        description_lines.append(line)
        
    description_lines.append("\nREACCIONES EN ESTE VIDEO:")
    
    for cap in chapters:
        clean_line = f"{cap.get('timestamp', '')} - {streamer_name.upper()} {date_str.upper()} {cap.get('title', '')}"
        description_lines.append(clean_line)
        
    return "\n".join(description_lines)

PUBLIC_DATA_REL_PATH = os.path.join("public", "data") # public/data

def sync_and_deploy_web(push_to_git=True, source_dir="data"):
    """
    Copia los JSONs a public/data y hace Push desde la raíz.
    """
    logger = logging.getLogger("SyncWeb")
    
    files = ["web_database.json", "series_metadata.json"]
    
    # Ruta absoluta destino: D:\...\public\data
    dest_abs_path = os.path.join(REPO_ROOT, PUBLIC_DATA_REL_PATH)

    try:
        # 1. Copia de Archivos
        if not os.path.exists(dest_abs_path):
            logger.error(f"❌ Directorio destino no existe: {dest_abs_path}")
            return False

        for f in files:
            src = os.path.join(source_dir, f) # Origen (donde corre el script python)
            dst = os.path.join(dest_abs_path, f) # Destino (Next.js public/data)
            
            if os.path.exists(src):
                shutil.copy2(src, dst)
                logger.info(f"✅ Copiado {f} -> {dst}")
            else:
                logger.warning(f"⚠️ Archivo fuente no encontrado: {src}")

        # 2. Git Automation (Ejecutado desde la RAÍZ)
        if push_to_git:
            logger.info("🚀 Iniciando Git Push...")
            
            # Construimos las rutas relativas para git add
            # Ej: public/data/web_database.json
            files_to_add = [os.path.join(PUBLIC_DATA_REL_PATH, f) for f in files]
            
            # También agregar carpeta de covers (por si hay nuevas imágenes)
            covers_path = os.path.join("public", "images", "covers")
            files_to_add.append(covers_path)
            
            # El comando add debe ser una lista plana
            cmd_add = ['git', 'add'] + files_to_add
            
            cmds = [
                cmd_add,
                ['git', 'commit', '-m', "Auto-update: Nuevos videos y thumbnails"],
                ['git', 'push']
            ]
            
            for cmd in cmds:
                result = subprocess.run(
                    cmd,
                    cwd=REPO_ROOT,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                if result.returncode != 0:
                    # Ignoramos error si es "nothing to commit"
                    err_msg = result.stderr.decode()
                    if "nothing to commit" in err_msg or "clean" in result.stdout.decode():
                        logger.info("ℹ️ Nada nuevo que commitear.")
                    else:
                        logger.error(f"❌ Error en comando {cmd[0]}: {err_msg}")
                        return False
            
            logger.info("🎉 Git Push completado correctamente.")

        return True

    except Exception as e:
        logger.error(f"❌ Error General en Sync: {e}")
        return False