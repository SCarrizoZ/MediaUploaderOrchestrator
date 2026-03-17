import os
import shutil
import logging
from libs.video_utils import generate_smart_thumbnail
from libs.image_optimizer import optimize_thumbnail

def process_thumbnail(video_path, cloudinary_manager, logger=None):
    """
    Genera, optimiza y sube un thumbnail a Cloudinary.
    
    Args:
        video_path: Ruta al archivo de video.
        cloudinary_manager: Instancia de CloudinaryManager.
        logger: Logger opcional.

    Returns:
        cloud_url: URL de la imagen en Cloudinary o "" si falló.
    """
    if not logger:
        logger = logging.getLogger("ThumbnailManager")
        
    cloud_url = ""
    thumb_dir = os.path.join("data", "thumbnails_temp")
    
    try:
        # 1. Generar Smart Thumbnail
        logger.info(f"   🖼️ Generando Thumbnail: {os.path.basename(video_path)}")
        thumb_path = generate_smart_thumbnail(video_path, thumb_dir, position_percent=0.45)
        
        if not thumb_path:
            logger.warning("   ⚠️ No se pudo generar el thumbnail base.")
            return ""

        # 2. Upload (si Cloudinary está activo)
        if cloudinary_manager and cloudinary_manager.enabled:
            try:
                logger.info("   ⚙️ Optimizando Thumbnail...")
                optimized_thumb_path = thumb_path.replace(".jpg", "_opt.webp")
                
                if optimize_thumbnail(thumb_path, optimized_thumb_path):
                    # Si optimiza bien, subimos el optimizado
                    cloud_url = cloudinary_manager.upload_image(optimized_thumb_path, folder="thumbnails")
                    
                    # Limpiar optimizado
                    try: os.remove(optimized_thumb_path)
                    except: pass
                else:
                    # Si falla optimización, subimos el original
                    logger.warning("   ⚠️ Falló optimización, subiendo original.")
                    cloud_url = cloudinary_manager.upload_image(thumb_path, folder="thumbnails")
            
            except Exception as e:
                logger.error(f"   ❌ Error en flujo optimización/upload: {e}")
                # Intento de subir original como fallback
                cloud_url = cloudinary_manager.upload_image(thumb_path, folder="thumbnails")
        
        # Limpiar thumbnail original generado
        try: os.remove(thumb_path)
        except: pass

    except Exception as e:
        logger.error(f"Error procesando thumbnail para {video_path}: {e}")
        return ""
        
    return cloud_url

def process_static_thumbnail(image_path_or_url, cloudinary_manager, logger=None):
    """
    Procesa un thumbnail estático (local o URL) para Cloudinary.
    Descarga (si url), optimiza y sube.
    """
    import requests
    import uuid
    if not logger:
        logger = logging.getLogger("ThumbnailManager")
        
    cloud_url = ""
    thumb_dir = os.path.join("data", "thumbnails_temp")
    os.makedirs(thumb_dir, exist_ok=True)
    
    temp_input = None
    is_local = os.path.exists(image_path_or_url)
    
    try:
        if is_local:
            temp_input = image_path_or_url
        else:
            if image_path_or_url.startswith("http"):
                logger.info(f"⬇️ Descargando Thumbnail: {image_path_or_url}")
                resp = requests.get(image_path_or_url, timeout=15)
                if resp.status_code == 200:
                    temp_file = os.path.join(thumb_dir, f"temp_thumb_{uuid.uuid4()}.jpg")
                    with open(temp_file, 'wb') as f:
                        f.write(resp.content)
                    temp_input = temp_file
                else:
                    logger.error(f"Error descargando thumbnail: {resp.status_code}")
                    return ""
            else:
                return image_path_or_url # Probably already a Cloudinary URL or path

        if temp_input and cloudinary_manager and cloudinary_manager.enabled:
            logger.info("   ⚙️ Optimizando Thumbnail estático...")
            optimized_thumb_path = os.path.join(thumb_dir, f"opt_{uuid.uuid4()}.webp")
            
            if optimize_thumbnail(temp_input, optimized_thumb_path):
                cloud_url = cloudinary_manager.upload_image(optimized_thumb_path, folder="thumbnails")
                try: os.remove(optimized_thumb_path)
                except: pass
            else:
                cloud_url = cloudinary_manager.upload_image(temp_input, folder="thumbnails")
                
    except Exception as e:
        logger.error(f"Error procesando thumbnail estático: {e}")
        return ""
        
    finally:
        # Limpiar si descargamos
        if not is_local and temp_input and os.path.exists(temp_input):
            try: os.remove(temp_input)
            except: pass
            
    return cloud_url
