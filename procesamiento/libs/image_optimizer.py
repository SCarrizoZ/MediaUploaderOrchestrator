import os
from PIL import Image

def optimize_cover(input_path, output_path):
    """
    Optimiza una imagen para portada:
    1. Convierte a .webp
    2. Redimensiona si ancho > 600px (manteniendo ratio)
    3. Asegura modo RGB
    4. Comprime (quality=85, method=6)
    """
    try:
        with Image.open(input_path) as img:
            # Asegurar RGB (para manejar PNGs transparentes o CMYK)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Redimensionar si es necesario
            max_width = 600
            if img.width > max_width:
                # Calcular nuevo alto manteniendo aspect ratio
                ratio = max_width / float(img.width)
                new_height = int((float(img.height) * float(ratio)))
                img = img.resize((max_width, new_height), Image.LANCZOS)

            # Crear directorio destino si no existe
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            # Guardar como WebP
            img.save(output_path, 'WEBP', quality=85, method=6)
            return True
            
    except Exception as e:
        print(f"Error optimizando imagen {input_path}: {e}")
        return False

def optimize_thumbnail(input_path, output_path):
    """
    Optimiza thumbnails para Cloudinary:
    1. Convierte a .webp
    2. Redimensiona a ancho 1280px (720p)
    3. Asegura RGB
    4. Compresión moderada (q=85)
    """
    try:
        with Image.open(input_path) as img:
            if img.mode != 'RGB': img = img.convert('RGB')
            
            # Redimensionar a 1280px de ancho (HD estándar)
            TARGET_WIDTH = 1280
            if img.width > TARGET_WIDTH:
                ratio = TARGET_WIDTH / float(img.width)
                new_height = int((float(img.height) * float(ratio)))
                img = img.resize((TARGET_WIDTH, new_height), Image.LANCZOS)
                
            # Crear directorio destino si no existe
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            img.save(output_path, 'WEBP', quality=85, method=6)
            return True
    except Exception as e:
        print(f"Error optimizando thumbnail {input_path}: {e}")
        return False
