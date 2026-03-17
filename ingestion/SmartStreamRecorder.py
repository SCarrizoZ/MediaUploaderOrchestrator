import sys
import shutil
import os
import subprocess
import time
import json
import re
import tkinter as tk
import threading
from tkinter import filedialog, messagebox, ttk
from datetime import datetime, timedelta
from pathlib import Path

# --- CONFIGURACIÓN DEL SISTEMA ---
CONFIG_FILE = "config_recorder.json"
CHECK_INTERVAL = 30    # Segundos a esperar si está offline
RETRY_INTERVAL = 5     # Segundos a esperar si se cae la conexión (micro-corte)
SESSION_TIMEOUT = 900  # (15 min) Tiempo máximo de espera para resetear sesión

class StreamConfig:
    def __init__(self):
        self.data = self.load_config()

    def load_config(self):
        default_structure = {
            "base_path": "",
            "quality": "best",
            "twitch_auth_token": "",
            "streamers_history": []
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    if "streamers_history" not in loaded:
                        loaded["streamers_history"] = []
                        if "streamer_name" in loaded: loaded["streamers_history"].append(loaded["streamer_name"])
                    if "twitch_auth_token" not in loaded:
                        loaded["twitch_auth_token"] = ""
                    return loaded
            except: pass 
        return default_structure

    def save(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4)

    def add_streamer_to_history(self, name):
        if name not in self.data["streamers_history"]:
            self.data["streamers_history"].append(name)
            self.save()

    @property
    def base_path(self): return self.data['base_path']
    @base_path.setter
    def base_path(self, value): self.data['base_path'] = value; self.save()
    
    @property
    def history(self): return self.data['streamers_history']
    @property
    def quality(self): return self.data.get('quality', 'best')
    @property
    def auth_token(self): return self.data.get('twitch_auth_token', "")

# --- GUI ---
def ask_streamer_gui(config):
    root = tk.Tk()
    root.title("Recorder V5 - Batch Mode")
    w, h = 400, 180
    root.geometry(f"{w}x{h}+{int(root.winfo_screenwidth()/2 - w/2)}+{int(root.winfo_screenheight()/2 - h/2)}")

    selected = tk.StringVar()
    tk.Label(root, text="Streamer a grabar:", font=("Arial", 10)).pack(pady=10)
    combo = ttk.Combobox(root, textvariable=selected, values=config.history, font=("Arial", 12))
    combo.pack(pady=5, padx=20, fill='x'); combo.focus()

    def confirm():
        if selected.get().strip(): root.destroy()
        else: messagebox.showwarning("Error", "Escribe un nombre.")
    
    tk.Button(root, text="GRABAR", command=confirm, bg="#4CAF50", fg="white").pack(pady=20)
    root.bind('<Return>', lambda e: confirm())
    root.mainloop()
    return selected.get().strip()

def setup_base_path(config):
    if not config.base_path or not os.path.exists(config.base_path):
        root = tk.Tk(); root.withdraw()
        folder = filedialog.askdirectory(title="Selecciona carpeta raíz")
        if folder: config.base_path = folder
        else: exit()

# --- LÓGICA DE HERRAMIENTAS ---

def check_is_live(streamer_name, auth_token):
    cmd = ["streamlink", f"twitch.tv/{streamer_name}", "--stream-url"]
    if auth_token:
        cmd.extend(["--twitch-api-header", f"Authorization=OAuth {auth_token}"])
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0
    except: return False

def is_file_stable(file_path, wait_seconds=2):
    """Verifica que el archivo no esté siendo escrito comparando su tamaño."""
    try:
        if not os.path.exists(file_path): return False
        size1 = os.path.getsize(file_path)
        time.sleep(wait_seconds)
        size2 = os.path.getsize(file_path)
        return size1 == size2 and size1 > 0
    except: return False

def batch_sanitize(file_list):
    """
    Procesa archivos con el método NUCLEAR y guarda LOGS de FFMPEG en disco.
    """
    if not file_list:
        print("\nℹ️  No hay archivos para procesar.")
        return

    print("\n" + "="*60)
    print(f"🧹 POST-PRODUCCIÓN: Iniciando limpieza de {len(file_list)} archivos...")
    print("="*60)

    for i, file_path in enumerate(file_list):
        filename = os.path.basename(file_path)
        print(f"\n[{i+1}/{len(file_list)}] Verificando: {filename}")
        
        attempts = 0
        while not is_file_stable(file_path) and attempts < 5:
            print(f"   ⏳ Esperando estabilidad del archivo ({attempts+1}/5)...")
            time.sleep(2)
            attempts += 1
        
        if not os.path.exists(file_path):
            print("   ❌ El archivo ya no existe. Saltando.")
            continue

        print(f"   ☢️  Aplicando parche NUCLEAR (GenPTS + Bitstream)...")
        temp_fixed = Path(file_path).with_suffix('.fixed.ts')
        log_ffmpeg = Path(file_path).with_suffix('.ffmpeg_fix.log')
        
        cmd = [
            'ffmpeg', '-y', '-fflags', '+genpts',
            '-i', str(file_path), 
            '-c:v', 'copy', '-c:a', 'copy',
            '-bsf:v', 'h264_mp4toannexb', 
            str(temp_fixed)
        ]
        
        try:
            with open(log_ffmpeg, "w", encoding="utf-8") as f_log:
                f_log.write(f"--- FFMPEG LOG: {datetime.now()} ---\n")
                f_log.write(f"CMD: {cmd}\n\n")
                f_log.flush()
                
                # stdout y stderr van directo al archivo
                process = subprocess.run(cmd, stdout=f_log, stderr=subprocess.STDOUT, text=True)
            
            if process.returncode == 0 and temp_fixed.exists() and temp_fixed.stat().st_size > 0:
                os.remove(file_path)
                shutil.move(str(temp_fixed), str(file_path))
                print(f"   ✅ Reparado. Log guardado en: {log_ffmpeg.name}")
            else:
                print(f"   ❌ FFMPEG falló. Revisa: {log_ffmpeg.name}")
                if temp_fixed.exists(): os.remove(temp_fixed)
                
        except Exception as e:
            print(f"   ❌ Error ejecución: {e}")
            if temp_fixed.exists(): 
                try: os.remove(temp_fixed)
                except: pass
    
    print("\n✨ Todo listo. Archivos saneados.")


# --- FUNCIÓN AUXILIAR PARA LEER LOGS EN SEGUNDO PLANO ---
def stream_log_worker(process, ad_log_path, start_time):
    """
    Lee la salida de Streamlink línea por línea sin bloquear el programa principal.
    Filtra los anuncios y los guarda en el archivo de log.
    """
    try:
        # Preparamos el archivo de log
        with open(ad_log_path, "w", encoding="utf-8") as ad_file:
            ad_file.write(f"LOG DE ANUNCIOS\n")
            ad_file.write(f"Inicio: {datetime.now()}\n")
            ad_file.write("="*40 + "\n")

        # Iteramos sobre la salida del proceso (se detiene cuando el proceso muere)
        for line in process.stdout:
            line = line.strip()
            if not line: continue

            # Detección de Anuncios
            if "Detected advertisement break" in line:
                try:
                    # Extraer duración
                    seconds_match = re.search(r'break of (\d+) seconds', line)
                    duration_ads = seconds_match.group(1) if seconds_match else "??"
                    
                    # Calcular tiempo relativo
                    elapsed = time.time() - start_record_time
                    timestamp_str = str(timedelta(seconds=int(elapsed)))
                    
                    log_entry = f"[{timestamp_str}] 🚨 ANUNCIO: {duration_ads}s ({line})\n"
                    
                    # Guardar en txt
                    with open(ad_log_path, "a", encoding="utf-8") as ad_file:
                        ad_file.write(log_entry)
                        
                    # (Opcional) Imprimir en consola borrando momentáneamente la barra
                    sys.stdout.write(f"\n📢 ANUNCIO DETECTADO: {duration_ads} segundos\n")
                    
                except Exception: pass
            
            # (Opcional) Si quieres ver errores graves de Streamlink en pantalla:
            if "error" in line.lower() or "failed" in line.lower():
                 sys.stdout.write(f"\n⚠️ {line}\n")

    except Exception as e:
        print(f"\n❌ Error en lector de logs: {e}")


def analyze_streamlink_log(raw_log_path, clean_log_path):
    """
    Analiza el log crudo de Streamlink para generar un reporte limpio de anuncios
    con tiempos relativos (Minuto del video).
    """
    if not os.path.exists(raw_log_path): return

    print(f"   🔍 Analizando log de anuncios...")
    
    ads_found = []
    start_time = None
    
    try:
        with open(raw_log_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                # 1. Extraer marca de tiempo del log [HH:MM:SS]
                # Ejemplo: [13:31:06] [plugins.twitch][info] ...
                time_match = re.search(r'^\[(\d{2}:\d{2}:\d{2})\]', line)
                if not time_match: continue
                
                line_time_str = time_match.group(1)
                line_dt = datetime.strptime(line_time_str, "%H:%M:%S")
                
                # Definir T0 (Inicio del stream) con la primera línea con hora
                if start_time is None:
                    start_time = line_dt
                
                # Gestionar cambio de día (Medianoche)
                if line_dt < start_time:
                    line_dt += timedelta(days=1)

                # 2. Buscar Anuncios
                if "Detected advertisement break" in line:
                    sec_match = re.search(r'break of (\d+) seconds', line)
                    duration = sec_match.group(1) if sec_match else "??"
                    
                    # Calcular tiempo relativo (Offset)
                    offset = line_dt - start_time
                    
                    ads_found.append(f"[{str(offset)}] 🚨 ANUNCIO: {duration} segundos")

        # Guardar reporte limpio
        with open(clean_log_path, 'w', encoding='utf-8') as f_out:
            f_out.write(f"REPORTE DE ANUNCIOS\n")
            f_out.write(f"Archivo base: {os.path.basename(raw_log_path)}\n")
            f_out.write(f"Total encontrados: {len(ads_found)}\n")
            f_out.write("="*30 + "\n")
            if ads_found:
                f_out.write("\n".join(ads_found))
            else:
                f_out.write("✅ No se detectaron interrupciones por anuncios.\n")
                
    except Exception as e:
        print(f"   ⚠️ Error analizando logs: {e}")

def tail_log_worker(raw_log_path, ad_report_path, start_time, stop_event):
    """
    Lee el archivo de log y ajusta el tiempo restando la duración de los anuncios previos.
    """
    # Esperar a que el archivo exista
    while not os.path.exists(raw_log_path) and not stop_event.is_set():
        time.sleep(1)

    if not os.path.exists(raw_log_path): return

    # VARIABLE NUEVA: Acumulador de tiempo perdido en anuncios
    total_ad_lost_time = 0

    try:
        with open(ad_report_path, "w", encoding="utf-8") as f_out:
            f_out.write(f"REPORTE DE ANUNCIOS - {os.path.basename(raw_log_path)}\n")
            f_out.write(f"Inicio Grabación: {datetime.now()}\n")
            f_out.write("="*40 + "\n")

        with open(raw_log_path, "r", encoding="utf-8", errors='replace') as f_in:
            while not stop_event.is_set():
                line = f_in.readline()
                
                if not line:
                    time.sleep(0.5) 
                    continue
                
                if "Detected advertisement break" in line:
                    try:
                        # 1. Extraer duración
                        sec_match = re.search(r'break of (\d+) seconds', line)
                        duration = int(sec_match.group(1)) if sec_match else 0
                        
                        # 2. Calcular tiempo REAL transcurrido
                        real_elapsed = time.time() - start_time
                        
                        # 3. Calcular tiempo de VIDEO (Real - Anuncios Anteriores)
                        video_elapsed = real_elapsed - total_ad_lost_time
                        
                        # Formatear a HH:MM:SS
                        timestamp_str = str(timedelta(seconds=int(video_elapsed)))
                        
                        msg = f"[{timestamp_str}] 🚨 ANUNCIO: {duration}s (Real: {str(timedelta(seconds=int(real_elapsed)))})\n"
                        
                        # Guardar
                        with open(ad_report_path, "a", encoding="utf-8") as f_out:
                            f_out.write(msg)
                            f_out.flush()
                        
                        # 4. IMPORTANTE: Sumar este anuncio al descuento para el FUTURO
                        # Se suma AHORA para que afecte al SIGUIENTE corte, no a este.
                        total_ad_lost_time += duration
                            
                    except Exception as e: 
                        print(f"Error calculando tiempo anuncio: {e}")
                    
    except Exception as e:
        print(f"Error en tail_worker: {e}")

def record_stream_logic(config, streamer_name):
    print("\n" + "="*60)
    print(f"📡  RECORDER V11 (Live Tail Logs): {streamer_name}")
    print(f"📂  Ruta: {config.base_path}")
    print("="*60 + "\n")

    current_part = 1
    last_active_time = 0
    session_date_str = None
    session_folder_path = None
    base_path_obj = Path(config.base_path)
    session_files_to_process = []
    
    stop_requested = False

    try:
        while not stop_requested:
            now = time.time()
            
            # Reset de sesión
            if last_active_time > 0 and (now - last_active_time > SESSION_TIMEOUT):
                print(f"\n⏹️  Sesión caducada.")
                if session_files_to_process:
                    batch_sanitize(session_files_to_process)
                    session_files_to_process = []
                print("🔄  Esperando nueva sesión...")
                session_date_str = None; session_folder_path = None
                current_part = 1; last_active_time = 0 

            is_live = check_is_live(streamer_name, config.auth_token)

            if not is_live:
                if session_date_str:
                    remaining = int(SESSION_TIMEOUT - (now - last_active_time))
                    sys.stdout.write(f"\r⏳ Stream offline. Esperando... ({remaining}s)   ")
                    sys.stdout.flush()
                    time.sleep(RETRY_INTERVAL)
                else:
                    sys.stdout.write(f"\r💤 [{datetime.now().strftime('%H:%M:%S')}] {streamer_name} offline...   ")
                    sys.stdout.flush()
                    time.sleep(CHECK_INTERVAL)
                continue
            
            # --- ONLINE ---
            if session_date_str is None:
                session_date_str = datetime.now().strftime("%Y-%m-%d")
                session_folder_path = base_path_obj / streamer_name / session_date_str
                print(f"\n\n🟢  NUEVA SESIÓN: {session_date_str}")
                session_files_to_process = []
            
            os.makedirs(session_folder_path, exist_ok=True)
            filename = f"{streamer_name}_{session_date_str}_Parte{current_part:02d}.ts"
            file_path = session_folder_path / filename
            
            # Archivos de LOG
            raw_log_path = session_folder_path / f"{filename}.raw_streamlink.log"
            ad_report_path = session_folder_path / f"{filename}.ad_report.txt"

            # Construimos comando
            cmd = [
                "streamlink",
                f"twitch.tv/{streamer_name}",
                config.quality,
                "-o", str(file_path),
                "--twitch-disable-ads",
                "--twitch-disable-hosting",
                "--twitch-disable-reruns",
                "--stream-segment-threads", "3",
                "--hls-live-restart",
                "--force",
                "--logfile", str(raw_log_path) # Streamlink escribe aquí
            ]

            if config.auth_token:
                cmd.extend(["--twitch-api-header", f"Authorization=OAuth {config.auth_token}"])

            print(f"🎥  GRABANDO PARTE {current_part} -> {filename}")
            
            start_record_time = time.time()
            # Evento para detener el hilo lector
            stop_tail_event = threading.Event()
            
            try:
                # Lanzamos Streamlink silenciando su salida a consola 
                # (ya que escribe en el archivo y queremos pintar nuestro dashboard)
                process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL
                )

                # --- LANZAMOS EL ESPÍA (Live Tail) ---
                tail_thread = threading.Thread(
                    target=tail_log_worker, 
                    args=(raw_log_path, ad_report_path, start_record_time, stop_tail_event)
                )
                tail_thread.daemon = True 
                tail_thread.start()

                # --- DASHBOARD (Barra Roja) ---
                while process.poll() is None:
                    elapsed = time.time() - start_record_time
                    time_str = str(timedelta(seconds=int(elapsed)))
                    
                    size_mb = 0
                    if file_path.exists():
                        size_mb = file_path.stat().st_size / (1024 * 1024)
                    
                    sys.stdout.write(f"\r🔴 [REC] Tiempo: {time_str} | Tamaño: {size_mb:.2f} MB   ")
                    sys.stdout.flush()
                    time.sleep(0.5)

            except KeyboardInterrupt:
                print("\n\n🛑 Interrupción de usuario (Ctrl+C).")
                print("⏳ Cerrando Streamlink...")
                stop_requested = True
                process.terminate() 
                try: process.wait(timeout=10)
                except: process.kill()
            
            except Exception as e:
                print(f"\n❌ Error lanzando Streamlink: {e}")
                time.sleep(CHECK_INTERVAL)
                continue
            
            # --- FIN DE PARTE ---
            stop_tail_event.set() # Detener el espía
            print("") 
            
            end_record_time = time.time()
            duration = end_record_time - start_record_time
            last_active_time = time.time()

            if file_path.exists() and file_path.stat().st_size > 1024 * 500:
                print(f"⏹️  Grabación detenida ({int(duration)} seg).")
                print(f"📌  Agregado a cola de procesamiento.")
                session_files_to_process.append(file_path)
                current_part += 1
            else:
                print("⚠️  Archivo pequeño/inexistente.")
                if file_path.exists(): 
                    try: os.remove(file_path)
                    except: pass
                # Limpiar logs si falló
                if raw_log_path.exists(): 
                    try: os.remove(raw_log_path)
                    except: pass
                if ad_report_path.exists(): 
                    try: os.remove(ad_report_path)
                    except: pass

            if stop_requested:
                print("⛔ Saliendo del monitor.")
                break
                
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Interrupción forzada.")
    
    finally:
        if session_files_to_process:
            print("\n🚨 Procesando archivos pendientes...")
            batch_sanitize(session_files_to_process)
        else:
            print("\n👋 Salida limpia.")

if __name__ == "__main__":
    app_config = StreamConfig()
    setup_base_path(app_config)
    target = ask_streamer_gui(app_config)
    if target:
        app_config.add_streamer_to_history(target)
        record_stream_logic(app_config, target)