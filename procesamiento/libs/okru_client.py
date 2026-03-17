import os
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from .utils import setup_logger

class OkruUploader:
    def __init__(self, config, log_queue=None):
        self.logger = setup_logger("OKRu", log_queue)
        
        root_dir = os.getcwd() 
        profile_name = config['okru'].get('profile_path', 'config/chrome_profile_okru')
        self.profile_path = os.path.join(root_dir, profile_name)
        
        self.headless = config['okru'].get('headless', False)
        self.driver = None

    def _init_driver(self):
        """Configura e inicia Chrome"""
        self.logger.info(f"🌐 Iniciando Chrome: {self.profile_path}")
        if not os.path.exists(self.profile_path):
            os.makedirs(self.profile_path)

        chrome_options = Options()
        chrome_options.add_argument(f"user-data-dir={self.profile_path}")
        if self.headless: chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--log-level=3")
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_window_size(1280, 720)
        except Exception as e:
            self.logger.error(f"❌ Error iniciando Chrome: {e}")

    def upload_video(self, file_path, gui_callback=None):
        if not self.driver: self._init_driver()
        if not self.driver: return False, None
        if not os.path.exists(file_path): return False, None

        captured_video_id = None

        try:
            self.driver.get("https://ok.ru/video/manager")
            time.sleep(5)

            # 1. Enviar Archivo
            try:
                file_input = self.driver.find_element(By.CSS_SELECTOR, "input[name='files'][type='file']")
                self.logger.info(f"📂 Enviando: {os.path.basename(file_path)}")
                file_input.send_keys(os.path.abspath(file_path))
            except:
                file_input = self.driver.find_element(By.XPATH, "//input[@type='file']")
                file_input.send_keys(os.path.abspath(file_path))

            self.logger.info("⏳ Iniciando subida inteligente (Modo: Sin Publicar)...")

            # VARIABLES DE MONITOREO
            last_progress = -1.0
            stuck_start_time = time.time()
            max_stuck_time = 300  # 5 minutos sin cambios = Estancado
            last_log_percentage = -1 

            while True:

                # A) INTENTAR CAPTURAR ID (Botón Edit)
                if not captured_video_id:
                    try:
                        # Buscamos el botón de editar
                        edit_btns = self.driver.find_elements(By.CLASS_NAME, "js-uploader-editor-link")
                        for btn in edit_btns:
                            href = btn.get_attribute("href")
                            if href and "/video/editor/" in href:
                                # Extraer ID del string "/video/editor/123456789"
                                parts = href.split("/editor/")
                                if len(parts) > 1:
                                    captured_video_id = parts[1].strip()
                                    self.logger.info(f"   🔗 ID Detectado: {captured_video_id}")
                                    break
                    except: pass

                # B) CRITERIO DE ÉXITO: Botón "Publicar" visible
                try:
                    publish_btns = self.driver.find_elements(By.CLASS_NAME, "js-uploader-publish-link")
                    if any(btn.is_displayed() for btn in publish_btns):
                        self.logger.info("✅ Botón Publicar detectado. Subida completada.")
                        if captured_video_id:
                            self.logger.info(f"   🔗 ID Capturado: {captured_video_id}")
                        else:
                            self.logger.warning("   ⚠️ Subida OK, pero no se pudo capturar el ID.")
                        time.sleep(2) 
                        return True, captured_video_id
                except: pass

                # C) MONITOREO DE PROGRESO
                try:
                    prog_elem = self.driver.find_element(By.CLASS_NAME, "v-upl-card_pb_count")
                    current_txt = prog_elem.text.strip()
                    
                    if current_txt:
                        current_progress = float(current_txt)
                        
                        # Loguear cada 20%
                        current_bracket = int(current_progress / 20) * 20
                        if current_bracket > last_log_percentage and current_bracket > 0:
                            self.logger.info(f"   📊 Subiendo OK.ru: ~{current_bracket}%")
                            if gui_callback: gui_callback(None, f"Subiendo OK.ru: {current_bracket}%")
                            last_log_percentage = current_bracket

                        # WATCHDOG
                        if current_progress > last_progress:
                            last_progress = current_progress
                            stuck_start_time = time.time()
                        else:
                            stuck_duration = time.time() - stuck_start_time
                            if stuck_duration > max_stuck_time:
                                self.logger.warning(f"⚠️ Estancado en {current_progress}% por {int(stuck_duration)}s.")
                                
                                if current_progress >= 99.0:
                                    self.logger.info("   🔄 Estancado en >99%. Refrescando página (Bug Visual)...")
                                    try:
                                        self.driver.refresh()
                                        time.sleep(10)
                                    except: pass
                                    return True, captured_video_id
                                else:
                                    self.logger.error("❌ Fallo de subida (Estancado). Abortando.")
                                    return False, None
                except: pass

                # C) Chequear ERRORES
                try:
                    error_msg = self.driver.find_element(By.CLASS_NAME, "js-uploader-error")
                    if error_msg.is_displayed() and error_msg.text:
                        self.logger.error(f"❌ Error OK.ru detectado: {error_msg.text}")
                        return False, None
                except: pass

                time.sleep(2)

            return False, None

        except Exception as e:
            self.logger.error(f"❌ Excepción Selenium: {e}")
            return False, None

    def close(self):
        """Cierra el navegador de forma segura y verbosa."""
        if self.driver:
            self.logger.info("🛑 Cerrando driver de Chrome...")
            try: 
                self.driver.quit()
                self.logger.info("   ✅ Chrome cerrado correctamente.")
            except Exception as e: 
                self.logger.warning(f"⚠️ Alerta al cerrar Chrome: {e}")
            finally:
                self.driver = None
        else:
            pass