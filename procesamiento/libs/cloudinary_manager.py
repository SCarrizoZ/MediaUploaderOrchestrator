import cloudinary
import cloudinary.uploader
import logging
import os

class CloudinaryManager:
    def __init__(self, config):
        """
        Inicializa la conexión con Cloudinary usando el dict de configuración.
        config debe tener: {'cloud_name': '...', 'api_key': '...', 'api_secret': '...'}
        """
        self.logger = logging.getLogger("Cloudinary")
        
        c_conf = config.get('cloudinary', {})
        try:
            cloudinary.config(
                cloud_name = c_conf.get('cloud_name'),
                api_key = c_conf.get('api_key'),
                api_secret = c_conf.get('api_secret'),
                secure = True
            )
            self.enabled = True
        except Exception as e:
            self.logger.error(f"❌ Error configurando Cloudinary: {e}")
            self.enabled = False

    def upload_image(self, file_path, folder="thumbnails"):
        """
        Sube una imagen a Cloudinary.
        Retorna la URL segura (https) o None si falla.
        """
        if not self.enabled:
            self.logger.warning("⚠️ Cloudinary deshabilitado o mal configurado.")
            return None

        if not os.path.exists(file_path):
            self.logger.error(f"❌ Archivo no encontrado: {file_path}")
            return None

        try:
            filename = os.path.basename(file_path)
            public_id_base = os.path.splitext(filename)[0]
            
            self.logger.info(f"📤 Subiendo a Cloudinary ({folder}): {filename}...")
            
            # Subida
            response = cloudinary.uploader.upload(
                file_path,
                folder=folder,
                public_id=public_id_base,
                resource_type="image"
            )
            
            # Retornamos el public_id (ej: folder/imagen123)
            pid = response.get('public_id')
            self.logger.info(f"✅ Subida Exitosa. Public ID: {pid}")
            return pid

        except Exception as e:
            self.logger.error(f"❌ Error subiendo a Cloudinary {folder}/{filename}: {e}")
            return None
