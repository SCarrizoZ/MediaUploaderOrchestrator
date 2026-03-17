import os
import asyncio
import threading
import shutil
import math
import subprocess
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from FastTelethonhelper import upload_file
from .utils import setup_logger

class TelegramUploader:
    def __init__(self, config, log_queue=None):
        self.logger = setup_logger("Telegram", log_queue)
        self.api_id = config['telegram']['api_id']
        self.api_hash = config['telegram']['api_hash']
        self.session_name = config['telegram']['session_name']
        self.channel_id = config['telegram']['channel_id']
        self.backup_folder = config['paths']['backup_folder']
        
        # Límite seguro (1.95 GB)
        self.MAX_SIZE = 1.95 * 1024 * 1024 * 1024 
        
        self.client = None
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start_loop, daemon=True)
        self.thread.start()
        
        future = asyncio.run_coroutine_threadsafe(self._connect(), self.loop)
        try: future.result(timeout=30)
        except: pass

    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _connect(self):
        self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
        await self.client.start()
        self.logger.info("✅ Cliente Telegram conectado.")

    # --- MÉTODO PÚBLICO PRINCIPAL ---
    def upload_video(self, file_path, caption_base, gui_callback=None):
        if not os.path.exists(file_path): return False, []

        # Verificar tamaño
        size = os.path.getsize(file_path)
        files_to_send = []
        is_split = False

        if size > self.MAX_SIZE:
            self.logger.info(f"✂️ Archivo grande ({size/1024**3:.2f}GB). Dividiendo...")
            files_to_send = self._split_video(file_path, size)
            is_split = True
        else:
            files_to_send = [file_path]

        if not files_to_send: return False, []

        # Subir cada parte
        all_ok = True
        sent_messages = []
        total_parts = len(files_to_send)
        
        for i, f_path in enumerate(files_to_send):
            # Personalizar caption si es por partes
            final_caption = caption_base
            if is_split:
                final_caption += f" (Parte {i+1}/{total_parts})"
            
            # Llamada asíncrona
            future = asyncio.run_coroutine_threadsafe(
                self._upload_coroutine(f_path, final_caption, gui_callback, i+1, total_parts),
                self.loop
            )
            try:
                result_msg = future.result()
                if result_msg:
                    sent_messages.append(result_msg)
                else:
                    all_ok = False
            except Exception as e:
                self.logger.error(f"Error subiendo parte {i+1}: {e}")
                all_ok = False

        # Limpieza de temporales (solo si hubo split) Mover Partes a Backup para verificar el corte realizado
        if is_split:
            for temp_f in files_to_send:
                try: 
                    shutil.move(temp_f, self.backup_folder)
                    self.logger.info(f"✅ Parte movida a backup: {temp_f}")
                except: 
                    self.logger.error(f"❌ Error moviendo parte a backup: {temp_f}")
                    pass
            if all_ok:
                self.logger.info(f"ℹ️ Archivo original preservado: {os.path.basename(file_path)}")
                self.logger.info(f"ℹ️ Todas las partes movidas a backup: {self.backup_folder}")
            # Intentar borrar carpeta temp si está vacía
            try: os.rmdir(os.path.dirname(files_to_send[0]))
            except: pass
        else:
            # Si fue archivo único, mover a backup
            if all_ok: 
                self._backup_file(file_path)
                self.logger.info(f"ℹ️ Archivo original preservado: {os.path.basename(file_path)}")


        return all_ok, sent_messages

    # --- LÓGICA DE SPLIT (Rescatada de tu script V5) ---
    def _split_video(self, source_file, file_size):
        try:
            # Obtener duración
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', source_file]
            duration = float(subprocess.check_output(cmd, creationflags=0x08000000).strip())
            
            if duration == 0: return []
            
            avg_bitrate = file_size / duration
            chunk_duration = (self.MAX_SIZE / avg_bitrate) * 0.95 # 5% margen
            total_parts = math.ceil(duration / chunk_duration)
            
            base_name = os.path.splitext(os.path.basename(source_file))[0]
            temp_dir = os.path.join(os.path.dirname(source_file), "temp_tg_split")
            if not os.path.exists(temp_dir): os.makedirs(temp_dir)
            
            generated = []
            current_start = 0.0
            
            for i in range(total_parts):
                current_end = min(current_start + chunk_duration, duration)
                part_path = os.path.join(temp_dir, f"{base_name}_Pt{i+1}.mp4")
                
                cmd_ffmpeg = [
                    'ffmpeg', '-y', 
                    '-ss', str(current_start), 
                    '-i', source_file, 
                    '-t', str(current_end - current_start), 
                    '-map', '0',
                    '-c:v', 'copy',               # Copiar Video (Rápido)
                    '-c:a', 'aac', '-b:a', '192k',# Re-codificar Audio (Arregla Sync)
                    '-avoid_negative_ts', 'make_zero',
                    '-fflags', '+genpts',
                    part_path
                ]
                subprocess.run(cmd_ffmpeg, check=True, creationflags=0x08000000)
                generated.append(part_path)
                current_start = current_end
                
            return generated
        except Exception as e:
            self.logger.error(f"Error dividiendo video: {e}")
            return []

    async def _upload_coroutine(self, file_path, caption, gui_callback, part_num, total_parts):
        filename = os.path.basename(file_path)
        self.logger.info(f"📤 Subiendo: {filename}...")

        def internal_progress(current, total):
            percent = (current / total) * 100
            status_txt = f"Subiendo Telegram ({part_num}/{total_parts}): {percent:.1f}%"
            # Mostrar progreso por terminal
            print(f"\r{status_txt}", end="", flush=True)
            
            if gui_callback:
                gui_callback(percent, status_txt)

        while True:
            try:

                if not self.client.is_connected():
                    self.logger.warning("❌ Cliente Telegram no conectado. Intentando reconectar...")
                    await self.client.connect()
                    continue

                with open(file_path, "rb") as f:
                    uploaded_file = await upload_file(
                        client=self.client, 
                        file=f, 
                        name=filename, 
                        progress_callback=internal_progress
                    )
                print() # Salto de línea al terminar la subida
                
                message = await self.client.send_file(
                    self.channel_id,
                    uploaded_file,
                    caption=caption,
                    supports_streaming=True
                )
                self.logger.info(f"✅ Telegram: {filename} OK.")
                return message
            except FloodWaitError as e:
                self.logger.warning(f"⏳ FloodWait: Esperando {e.seconds} segundos antes de reintentar...")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                self.logger.error(f"❌ Fallo Telegram: {e}")
                return None

    def _backup_file(self, file_path):
        if not os.path.exists(self.backup_folder): os.makedirs(self.backup_folder)
        try:
            shutil.move(file_path, os.path.join(self.backup_folder, os.path.basename(file_path)))
            self.logger.info(f"📦 Respaldo OK.")
        except: pass
    
    def disconnect(self):
        try: asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)
        except: pass