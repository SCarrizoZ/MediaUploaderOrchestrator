import os
import re
from utils import CONTENT_TYPE as TIPOS_MATERIAL
from utils import MESES_ES

def parse_show_info(text, history_data=None):
    """
    Extrae Show, Temporada y Episodio de una cadena de texto.
    
    Args:
        text (str): El texto a analizar.
        history_data (dict, optional): Un diccionario con el historial de series para buscar `material_type`.
                                       
    Returns:
        dict: Diccionario extraído con:
        {
            "show": str,
            "season": str,
            "episode": str,
            "type": str
        }
    """
    res = {"show": text, "season": "", "episode": "", "type": "Otro"}
    
    # Busca "S2 CAP 4" o "EP 4-5"
    match_ep = re.search(r"(.*?)(?:\s+S\s*(\d*))?(?:\s*(?:CAP|EP|PART|PT|PARTE|CAPITULO)\s*(\d+(?:\s*-\s*\d+)?.*))?$", text, re.IGNORECASE)
    clean_show = text
    
    if match_ep:
        clean_show = match_ep.group(1).strip()
        if clean_show: 
            res["show"] = clean_show
        
        # El grupo 2 es la temporada. Ej. "S2" -> "2", "S" -> "". Si "S" coincidió pero no hay número, se asume "1"
        if match_ep.group(2) is not None: 
            res["season"] = match_ep.group(2) if match_ep.group(2) != "" else "1"
        
        ep_str = ""
        if match_ep.group(3): 
            ep_str += match_ep.group(3)
        # Normalizar posibles rangos como "1 - 5" a "1-5"
        res["episode"] = re.sub(r'\s*-\s*', '-', ep_str.strip())
        
    # Compatibilidad con los nombres viejos: a veces lo devolvían como "ep" y otras como "episode"
    res["ep"] = res["episode"] 

    # Intentar sacar el type de un historial si existe
    if history_data:
        from libs.utils import slugify
        slug = slugify(res["show"])
        if slug in history_data:
            res["type"] = history_data[slug].get("material_type", "Otro")
            return res

    return res

def parse_filename(filename, history_data=None):
    """
    Intenta extraer Streamer, Fecha y Show del nombre del archivo.
    Formatos soportados:
    1. TUTISVALENTINE 08 FEBRERO 2026 Minecraft... (Formato Estandar)
    2. Tutis_2026-02-08_... (Formato Raw Twitch)
    
    Returns:
        dict: Diccionario extraído con:
        {
            "streamer": str,
            "date_str": str,
            "raw_name": str,       # Nombre base sin extensión
            "show": str,
            "season": str,
            "episode": str,
            "ep": str,             # Alias para episode
            "type": str,
            "is_vod": bool
        }
    """
    filename = os.path.basename(filename)
    name_no_ext = os.path.splitext(filename)[0]
    
    info = {
        "streamer": "",
        "date_str": "",
        "raw_name": name_no_ext,
        "show": "",
        "season": "",
        "episode": "",
        "ep": "",
        "type": "Otro",
        "is_vod": False
    }

    # A) Detección VOD (Si dice VOD o es muy largo)
    if "VOD" in name_no_ext.upper():
        info["is_vod"] = True

    # B) Intentar formato estandar (STREAMER DIA MES AÑO CONTENIDO)
    # Regex busca: (PALABRA) (DD) (MES) (AAAA) (RESTO)
    meses_str = r"(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)"
    match_std = re.search(fr"^([A-Z0-9_]+)\s+(\d{{1,2}})\s+{meses_str}\s+(\d{{4}})\s+(.*)", name_no_ext, re.IGNORECASE)
    
    if match_std:
        info["streamer"] = match_std.group(1).upper()
        day = match_std.group(2).zfill(2)
        month = match_std.group(3).upper() # En mayúsculas, como en el origen
        year = match_std.group(4)
        info["date_str"] = f"{day} {month} {year}"
        
        remainder = match_std.group(5)
        info["raw_name"] = remainder 
        
        # Intentar extraer show del resto
        show_info = parse_show_info(remainder, history_data)
        info.update(show_info)
        return info

    # C) Intentar formato Raw (Streamer_YYYY-MM-DD_...)
    match_raw = re.search(r"^([a-zA-Z0-9]+)_(\d{4})-(\d{2})-(\d{2})_", name_no_ext)
    if match_raw:
        info["streamer"] = match_raw.group(1).upper()
        y, m, d = match_raw.group(2), int(match_raw.group(3)), match_raw.group(4)
        
        # Convertir mes número a texto
        if 1 <= m <= 12:
            # En manual upload se devolvía el mes en mayúsculas, en video segmenter como title
            # Optamos por la mayúscula por consistencia con el formateador de fechas español
            month_str = MESES_ES.get(m, "ENERO").upper()
            info["date_str"] = f"{d} {month_str} {y}"
        
        # Extraer resto del nombre del archivo en RAW
        partes_raw = name_no_ext.split('-', 3)
        if len(partes_raw) > 3:
            remainder = partes_raw[-1].replace('_',' ').strip()
            info["raw_name"] = remainder
            show_info = parse_show_info(remainder, history_data)
            info.update(show_info)
            
        return info
        
    # D) Fallback formato Segmenter C (Adivinar por primera palabra)
    partes = name_no_ext.split(' ', 3)
    if len(partes) >= 4:
        info["streamer"] = partes[0].upper()
        info["raw_name"] = partes[-1]
    else:
        info["streamer"] = name_no_ext

    return info
