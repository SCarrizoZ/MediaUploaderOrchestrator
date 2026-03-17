import os
import requests
import uuid
import logging
from libs.image_optimizer import optimize_cover
from libs.utils import REPO_ROOT

# Rutas Base Hardcoded (tomadas de MetadataManagerCore)
PUBLIC_DATA_REL_PATH = os.path.join("public", "images", "covers")
PUBLIC_COVERS_PATH = os.path.join(REPO_ROOT, PUBLIC_DATA_REL_PATH)

def process_cover(current_url, show_name, season=None, config=None, logger=None):
    """
    Procesa una portada (descarga/copia -> optimiza -> guarda en repo web).
    
    Args:
        current_url: Ruta local, URL http, o ID Cloudinary.
        show_name: Nombre de la serie.
        season: Temporada (opcional).
        config: Dict de configuración (necesario para migrar de Cloudinary).
        logger: Logger opcional.

    Returns:
        (web_path, changed): Ruta web relativa y booleano indicando si cambió.
        Si falla, retorna (current_url, False).
    """
    if not logger:
        logger = logging.getLogger("CoverManager")
        
    if not current_url: return "", False

    # Nombre fichero destino
    safe_name = "".join([c for c in show_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(" ", "_")
    if season: safe_name += f"_S{season}"
    
    filename = f"{safe_name}.webp"
    dest_abs_path = os.path.join(PUBLIC_COVERS_PATH, filename)
    web_path = f"/images/covers/{filename}" # Ruta para el JSON (Next.js public)

    # Verificar si ya es la ruta correcta
    if current_url == web_path:
         if os.path.exists(dest_abs_path):
             return current_url, False
         # Si está en JSON pero no en disco, intentamos regenerar si 'current_url' fuera la fuente...
         # Pero aquí 'current_url' ES el destino, así que no tenemos fuente. 
         # Retornamos así para no romper nada, el usuario deberá re-subir si falta.
         return current_url, False

    temp_input = None
    is_local = os.path.exists(current_url)
    is_external = current_url.startswith("http")
    
    try:
        if is_local:
            temp_input = current_url
        else:
            download_url = current_url
            # Detectar ID Cloudinary antiguo (si no es http y no es ruta relativa válida)
            # Ej: "covers/naruto"
            if not is_external and not current_url.startswith("/images/covers/") and not os.path.isabs(current_url):
                cloud_name = config.get('cloudinary', {}).get('cloud_name') if config else None
                if cloud_name:
                    download_url = f"https://res.cloudinary.com/{cloud_name}/image/upload/{current_url}"
                    logger.info(f"🌍 Detectado ID Cloudinary. Migrando: {download_url}")
                else:
                    return current_url, False # No se puede construir URL

            # Descargar
            logger.info(f"⬇️ Descargando imagen: {download_url}")
            try:
                resp = requests.get(download_url, timeout=15)
                if resp.status_code == 200:
                    temp_file = f"temp_cover_{uuid.uuid4()}.jpg"
                    with open(temp_file, 'wb') as f:
                        f.write(resp.content)
                    temp_input = temp_file
                else:
                    logger.error(f"Error descargando {download_url}: {resp.status_code}")
                    return current_url, False
            except Exception as e:
                logger.error(f"Excepcion descarga: {e}")
                return current_url, False

        # 2. Optimizar y Guardar
        if temp_input:
            logger.info(f"Optimizando cover para: {show_name} -> {filename}")
            if optimize_cover(temp_input, dest_abs_path):
                logger.info(f"Cover guardada en: {dest_abs_path}")
                return web_path, True
            else:
                logger.error("Fallo optimizacion.")
                return current_url, False
                
    except Exception as e:
        logger.error(f"Error procesando imagen: {e}")
        return current_url, False

    finally:
        # Limpiar temporal si se creó/descargó (y NO es el local original)
        if not is_local and temp_input and os.path.exists(temp_input):
            try: os.remove(temp_input)
            except: pass
    
    return current_url, False
