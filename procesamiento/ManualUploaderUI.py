from libs.utils import CONTENT_TYPE
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
from manual_uploader_core.ManualUploadCore import ManualUploadCore
from manual_uploader_core.DatabaseManagerUI import DatabaseManagerUI  # Importamos el componente CRUD
from manual_uploader_core.MetadataManagerCore import MetadataManagerCore
from manual_uploader_core.MetadataManagerUI import MetadataManagerUI
from libs.cover_manager import process_cover
from libs.ui_components import StreamerDateSessionFrame

class ManualUploaderApp:
    def __init__(self, root, config):
        self.root = root
        self.root.title("Suite Ultimate V3 - Gestor & Uploader")
        self.root.geometry("1100x850")
        self.config = config
        
        # Inicializar Core de Subida
        self.core = ManualUploadCore()
        
        # Estilos Globales
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=[10, 5])
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), foreground="#333")
        style.configure("Status.TLabel", font=("Segoe UI", 9, "bold"))

        # ==========================================================
        # SISTEMA DE PESTAÑAS (NOTEBOOK)
        # ==========================================================
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # TAB 1: Uploader Manual
        self.tab_uploader = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_uploader, text="  📤 Subida Manual  ")
        self._init_uploader_tab(self.tab_uploader)

        # TAB 2: Gestor Base de Datos (Componente Externo)
        self.tab_db = DatabaseManagerUI(self.notebook)
        self.notebook.add(self.tab_db, text="  🗄️ Gestor Base de Datos  ")

        # TAB 3: Gestor Metadatos (Componente Externo)
        self.tab_metadata = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_metadata, text="🎨 Portadas y Info")

        self.meta_core = MetadataManagerCore()
        self.meta_ui = MetadataManagerUI(self.tab_metadata, self.meta_core)
        
        # Evento: Recargar DB al cambiar a la pestaña 2
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _on_tab_change(self, event):
        # Si cambio a la pestaña BD, refrescar el árbol
        current_tab = self.notebook.select()
        if current_tab == str(self.tab_db):
            self.tab_db.refresh_tree()

    # =========================================================================
    # LÓGICA DE LA PESTAÑA 1: UPLOADER
    # =========================================================================
    def _init_uploader_tab(self, parent):
        """Construye toda la interfaz de la pestaña de subida."""
        
        # --- Variables de Control ---
        self.var_streamer = tk.StringVar()
        self.var_date = tk.StringVar()
        
        self.var_vod_enabled = tk.BooleanVar(value=True)
        self.var_vod_path = tk.StringVar()
        self.var_vod_status = tk.StringVar(value="Sin seleccionar")
        
        self.reactions_data = [] # Lista de diccionarios para la tabla
        
        # Variables Edición Rápida (Reacciones)
        self.var_edit_show = tk.StringVar()
        self.var_edit_season = tk.StringVar()
        self.var_edit_ep = tk.StringVar()
        self.var_edit_type = tk.StringVar()
        self.var_edit_ok = tk.BooleanVar()
        self.var_edit_tg = tk.BooleanVar()
        self.selected_index = None

        # Variables Nueva Serie
        self.var_new_desc = tk.StringVar()
        self.var_new_cover_url = tk.StringVar()
        self.is_new_series = False
        
        # Trace para detectar nueva serie
        self.var_edit_show.trace("w", self._on_show_change)

        # --- Layout Principal ---
        main_frame = ttk.Frame(parent, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ----------------------------------------------------------
        # SECCIÓN 1: DATOS DE LA SESIÓN
        # ----------------------------------------------------------
        info_frame = ttk.LabelFrame(main_frame, text=" 1. Datos de la Sesión ", padding=10)
        info_frame.pack(fill=tk.X, pady=5)

        self.session_frame = StreamerDateSessionFrame(
            info_frame, 
            core_instance=self.core,
            var_streamer=self.var_streamer,
            var_date=self.var_date,
            streamer_width=23,
            date_width=23
        )
        self.session_frame.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(info_frame, text="(Autocompletado al cargar archivos)", 
                  font=("Segoe UI", 8, "italic"), foreground="#888").pack(side=tk.LEFT, padx=10)

        # ----------------------------------------------------------
        # SECCIÓN 2: VOD DE YOUTUBE
        # ----------------------------------------------------------
        vod_frame = ttk.LabelFrame(main_frame, text=" 2. VOD YouTube (Compilado) ", padding=10)
        vod_frame.pack(fill=tk.X, pady=10)

        # Fila 1: Check y Archivo
        cb = ttk.Checkbutton(vod_frame, text="Subir VOD", variable=self.var_vod_enabled, command=self._toggle_vod_ui)
        cb.grid(row=0, column=0, sticky="w")

        self.btn_vod = ttk.Button(vod_frame, text="Seleccionar Video...", command=self._browse_vod)
        self.btn_vod.grid(row=0, column=1, padx=10, sticky="w")

        ttk.Label(vod_frame, textvariable=self.var_vod_path, foreground="#555", width=40).grid(row=0, column=2, sticky="w", padx=5)
        
        # Estado BD
        self.lbl_vod_status = ttk.Label(vod_frame, textvariable=self.var_vod_status, style="Status.TLabel")
        self.lbl_vod_status.grid(row=0, column=3, sticky="e", padx=20)

        # Fila 2: Descripción
        ttk.Label(vod_frame, text="Descripción / Timestamps:").grid(row=1, column=0, sticky="nw", pady=5)
        
        self.txt_desc = tk.Text(vod_frame, height=5, width=80, font=("Consolas", 9))
        self.txt_desc.grid(row=1, column=1, columnspan=3, sticky="ew", pady=5)
        
        # Botón Importar
        ttk.Button(vod_frame, text="📂 Importar .txt", command=self._import_txt).grid(row=2, column=1, sticky="w")
        
        # Inicializar estado visual del VOD
        self._toggle_vod_ui()

        # ----------------------------------------------------------
        # SECCIÓN 3: GESTOR DE REACCIONES
        # ----------------------------------------------------------
        reac_frame = ttk.LabelFrame(main_frame, text=" 3. Reacciones (OK.ru / Telegram) ", padding=10)
        reac_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Toolbar (Botones de acción para la tabla)
        toolbar = ttk.Frame(reac_frame)
        toolbar.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(toolbar, text="➕ Agregar Archivos", command=self._add_reactions).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="➖ Quitar Seleccionado", command=self._remove_reaction).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="🧹 Limpiar Todo", command=self._clear_tree).pack(side=tk.LEFT, padx=2)

        # --- Tabla (Treeview) ---
        columns = ("file", "show", "ep", "type", "ok", "tg", "stat")
        self.tree = ttk.Treeview(reac_frame, columns=columns, show="headings", height=8)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        # Scrollbar
        sb = ttk.Scrollbar(reac_frame, orient="vertical", command=self.tree.yview)
        sb.pack(fill=tk.Y, side=tk.RIGHT)
        self.tree.configure(yscrollcommand=sb.set)

        # Configurar Columnas
        self.tree.heading("file", text="Archivo")
        self.tree.heading("show", text="Serie / Show")
        self.tree.heading("ep", text="Episodio")
        self.tree.heading("type", text="Tipo")
        self.tree.heading("ok", text="OK.ru")
        self.tree.heading("tg", text="Telegram")
        self.tree.heading("stat", text="Estado BD")

        self.tree.column("file", width=250)
        self.tree.column("show", width=150)
        self.tree.column("ep", width=80)
        self.tree.column("type", width=80)
        self.tree.column("ok", width=50, anchor="center")
        self.tree.column("tg", width=60, anchor="center")
        self.tree.column("stat", width=100)

        # Evento de Selección (Para cargar datos en el editor de abajo)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # --- ÁREA DE EDICIÓN RÁPIDA (Debajo de la tabla) ---
        edit_frame = ttk.LabelFrame(reac_frame, text="Editar Selección", padding=5)
        edit_frame.pack(fill=tk.X, pady=(10, 0))

        # Fila de Inputs
        ef = ttk.Frame(edit_frame)
        ef.pack(fill=tk.X)

        ttk.Label(ef, text="Serie:").pack(side=tk.LEFT, padx=2)
        
        # Combobox inteligente con historial
        self.cb_show = ttk.Combobox(ef, textvariable=self.var_edit_show, width=20)
        self.cb_show.pack(side=tk.LEFT, padx=2)
        self.cb_show['values'] = self.core.get_series_history()
        self.cb_show.bind("<<ComboboxSelected>>", self._on_cb_show_selected)

        ttk.Label(ef, text="Temp:").pack(side=tk.LEFT, padx=(5,0))
        ttk.Entry(ef, textvariable=self.var_edit_season, width=5).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(ef, text="Ep:").pack(side=tk.LEFT, padx=(5,0))
        ttk.Entry(ef, textvariable=self.var_edit_ep, width=5).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(ef, text="Tipo:").pack(side=tk.LEFT, padx=2)
        ttk.Combobox(ef, textvariable=self.var_edit_type, values=CONTENT_TYPE, width=10).pack(side=tk.LEFT, padx=2)

        # Checkboxes de destino
        ttk.Checkbutton(ef, text="Subir OK", variable=self.var_edit_ok).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(ef, text="Subir TG", variable=self.var_edit_tg).pack(side=tk.LEFT, padx=5)

        # Botón Aplicar
        ttk.Button(ef, text="💾 Aplicar Cambios", command=self._save_edit).pack(side=tk.RIGHT, padx=5)

        # Panel para Serie Nueva (Oculto por defecto)
        self.f_new_series = ttk.LabelFrame(edit_frame, text="✨ Nueva Serie Detectada", padding=5)
        # No lo hacemos pack al inicio
        
        ttk.Label(self.f_new_series, text="Descripción:").pack(side=tk.LEFT)
        ttk.Entry(self.f_new_series, textvariable=self.var_new_desc, width=40).pack(side=tk.LEFT, padx=5)
        
        btn_cover = ttk.Button(self.f_new_series, text="🖼️ Subir Portada", command=self._upload_cover)
        btn_cover.pack(side=tk.LEFT, padx=5)
        
        self.lbl_cover_status = ttk.Label(self.f_new_series, text="(Sin portada)", foreground="gray", font=("Segoe UI", 8))
        self.lbl_cover_status.pack(side=tk.LEFT)

        # ----------------------------------------------------------
        # SECCIÓN 4: BOTÓN DE INICIO
        # ----------------------------------------------------------
        action_frame = ttk.Frame(main_frame, padding=20)
        action_frame.pack(fill=tk.X)
        
        self.btn_start = ttk.Button(action_frame, text="🚀 INICIAR PROCESO DE SUBIDA", command=self._start_upload_process)
        self.btn_start.pack(fill=tk.X, ipady=10)

        # Barra de progreso simple
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.status_lbl = ttk.Label(main_frame, text="Listo para comenzar.", foreground="blue")
        self.status_lbl.pack(anchor="w", padx=10)

    def _toggle_vod_ui(self):
        """Habilita o deshabilita los campos del VOD según el checkbox."""
        state = "normal" if self.var_vod_enabled.get() else "disabled"
        self.btn_vod.configure(state=state)
        self.txt_desc.configure(state=state, background="white" if state=="normal" else "#f0f0f0")

    def _browse_vod(self):
        """Selecciona el archivo VOD principal."""
        path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.mkv *.ts *.mov")])
        if path:
            self.var_vod_path.set(path)
            self._parse_file_info(path, is_vod=True)

    def _import_txt(self):
        """Importa descripción desde un archivo de texto."""
        path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.txt_desc.delete("1.0", tk.END)
                    self.txt_desc.insert("1.0", f.read())
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo leer el archivo: {e}")

    def _add_reactions(self):
        """Agrega múltiples archivos a la tabla de reacciones."""
        paths = filedialog.askopenfilenames(filetypes=[("Video Files", "*.mp4 *.mkv *.ts")])
        if not paths:
            return

        for path in paths:
            # 1. Parsear nombre para obtener Show/Ep
            info = self.core.parse_filename(path)
            
            # 2. Si es el primer archivo y no hay sesión, llenar datos
            if not self.var_streamer.get(): 
                self._parse_file_info(path, is_vod=False)

            # 3. Checkear estado en BD
            filename = os.path.basename(path)
            in_ok = self.core.check_upload_status(filename, 'okru')
            in_tg = self.core.check_upload_status(filename, 'telegram')
            
            # Determinar estado textual
            status_txt = "Nuevo"
            if in_ok and in_tg: status_txt = "Completo en BD"
            elif in_ok: status_txt = "Falta TG"
            elif in_tg: status_txt = "Falta OK"

            # 4. Agregar a la lista de datos
            # Check if we should backfill missing information from history
            last_info = self.core.get_last_info(info.get("show", ""))
            
            # Use original parsed values, fallback to history if they are missing
            show_val = info.get("show") or self.var_edit_show.get()
            season_val = info.get("season")
            if not season_val: season_val = last_info.get("season", "")
            
            ep_val = info.get("episode")
            if not ep_val: ep_val = last_info.get("episode", "")
            
            type_val = info.get("type", "Otro")
            if type_val == "Otro" and "material_type" in last_info:
                type_val = last_info["material_type"]

            self.reactions_data.append({
                "path": path,
                "filename": filename,
                "show": show_val,
                "season": season_val,
                "ep": ep_val,
                "type": type_val,
                "ok": not in_ok, # Si ya está en BD, desmarcar por defecto
                "tg": not in_tg,
                "status_txt": status_txt
            })
        
        self._refresh_tree()

    def _refresh_tree(self):
        """Redibuja la tabla con los datos actuales."""
        for i in self.tree.get_children(): self.tree.delete(i)
        
        for idx, item in enumerate(self.reactions_data):
            # Iconos visuales
            ok_icon = "✅" if item["ok"] else "⛔"
            tg_icon = "✅" if item["tg"] else "⛔"
            
            vals = (
                item["filename"], 
                item["show"], 
                item["ep"], 
                item["type"],
                ok_icon, 
                tg_icon, 
                item["status_txt"]
            )
            self.tree.insert("", "end", iid=idx, values=vals)

    def _on_tree_select(self, event):
        """Carga los datos de la fila seleccionada en el editor de abajo."""
        sel = self.tree.selection()
        if not sel: return
        
        idx = int(sel[0])
        self.selected_index = idx
        data = self.reactions_data[idx]
        
        self.var_edit_show.set(data["show"])
        self.var_edit_season.set(data.get("season", ""))
        self.var_edit_ep.set(data["ep"])
        self.var_edit_type.set(data["type"])
        self.var_edit_ok.set(data["ok"])
        self.var_edit_tg.set(data["tg"])
        
        # Autocompletar tipo si cambiamos de show y existe en historial
        last_info = self.core.get_last_info(data["show"])
        if last_info and not data["type"]:
             self.var_edit_type.set(last_info.get("type", "Gameplay"))

    def _on_cb_show_selected(self, event):
        """Autocompleta Tipo y Temporada al seleccionar del historial."""
        show = self.var_edit_show.get().strip()
        info = self.core.get_last_info(show)
        if info:
            self.var_edit_show.set(info.get('title', show) or show)
            self.var_edit_season.set(info.get('season') or '')
            self.var_edit_ep.set(info.get('episode') or '')
            self.var_edit_type.set(info.get('material_type', 'Gameplay'))

    def _on_show_change(self, *args):
        """Detecta si la serie escrita es nueva."""
        name = self.var_edit_show.get().strip()
        if not name: 
            self._hide_new_series_panel()
            return

        info = self.meta_core.get_series_info(name)
        if info:
            self.is_new_series = False
            self._hide_new_series_panel()
        else:
            self.is_new_series = True
            self._show_new_series_panel()

    def _show_new_series_panel(self):
        try:
            self.f_new_series.pack(fill=tk.X, pady=5)
        except Exception: pass

    def _hide_new_series_panel(self):
        self.f_new_series.pack_forget()

    def _upload_cover(self):
        fn = filedialog.askopenfilename(title="Seleccionar Portada", filetypes=[("Imágenes", "*.jpg *.png *.webp")])
        if not fn: return
        self.var_new_cover_url.set(fn)
        self.lbl_cover_status.config(text=f"📂 {os.path.basename(fn)}", foreground="blue")

    def _save_edit(self):
        """Guarda los cambios del editor en la lista y refresca la tabla."""
        if self.selected_index is None: return
        
        idx = self.selected_index
        
        # Lógica para procesar nueva serie antes de guardar cambios locales
        if self.is_new_series:
            show_name = self.var_edit_show.get().strip().upper()
            raw_cover = self.var_new_cover_url.get()
            final_cover_url = ""
            
            if raw_cover:
                web_path, _ = process_cover(raw_cover, show_name, config=self.config)
                final_cover_url = web_path
            
            new_data = {
                'description': self.var_new_desc.get(),
                'cover_url': final_cover_url,
                'provider': 'Manual',
                'material_type': self.var_edit_type.get(),
                'seasons': {}
            }
            if self.meta_core.update_show_data(show_name, new_data):
                self.is_new_series = False
                self._hide_new_series_panel()
            else:
                messagebox.showerror("Error", "No se pudo guardar la metadata de la nueva serie.")
        
        self.reactions_data[idx].update({
            "show": self.var_edit_show.get(),
            "season": self.var_edit_season.get(),
            "ep": self.var_edit_ep.get(),
            "type": self.var_edit_type.get(),
            "ok": self.var_edit_ok.get(),
            "tg": self.var_edit_tg.get()
        })
        self._refresh_tree()

    def _remove_reaction(self):
        """Elimina la fila seleccionada."""
        sel = self.tree.selection()
        if not sel: return
        idx = int(sel[0])
        del self.reactions_data[idx]
        self._refresh_tree()
        self.selected_index = None

    def _clear_tree(self):
        """Limpia toda la tabla."""
        self.reactions_data.clear()
        self._refresh_tree()

    def _parse_file_info(self, path, is_vod=False):
        """Ayuda a llenar Streamer/Fecha y verificar VODs."""
        info = self.core.parse_filename(path)
        
        # Llenar datos de sesión si están vacíos
        if not self.var_streamer.get() and info.get("streamer"):
            self.session_frame.set_streamer(info["streamer"])
        if not self.var_date.get() and info.get("date_str"):
            self.session_frame.set_date(info["date_str"])
            
        if is_vod:
            # Autocargar descripción
            desc = self.core.get_auto_description(path)
            self.txt_desc.delete("1.0", tk.END)
            self.txt_desc.insert("1.0", desc)
            
            # Verificar estado en BD
            filename = os.path.basename(path)
            if self.core.check_upload_status(filename, 'youtube'):
                self.var_vod_status.set("✅ Registrado en BD")
                self.lbl_vod_status.configure(foreground="green")
            else:
                self.var_vod_status.set("⚠️ Nuevo / Pendiente")
                self.lbl_vod_status.configure(foreground="#d9534f")

    # ==========================================================
    # EJECUCIÓN DEL PROCESO
    # ==========================================================
    def _start_upload_process(self):
        """Valida y lanza el proceso de subida en segundo plano."""
        # 1. Validaciones
        if not self.var_streamer.get() or not self.var_date.get():
            messagebox.showwarning("Faltan Datos", "Por favor ingresa el nombre del Streamer y la Fecha.")
            return
            
        # 2. Construir Configuración del Trabajo
        job_config = {
            "streamer": self.var_streamer.get().strip(),
            "date": self.var_date.get().strip(),
            "close_chrome": True, # Seguridad: Siempre cerrar al final
            "vod": {
                "enabled": self.var_vod_enabled.get(),
                "path": self.var_vod_path.get(),
                "desc": self.txt_desc.get("1.0", tk.END).strip()
            },
            "reactions": self.reactions_data
        }

        # 3. Bloquear UI
        self.btn_start.configure(state="disabled", text="⏳ PROCESANDO...")
        self.status_lbl.configure(text="Iniciando motor de subida...")
        self.progress_bar['value'] = 0
        
        # 4. Definir Callbacks
        def on_finish():
            """Se ejecuta cuando el hilo termina."""
            self.root.after(0, self._restore_ui)

        def update_progress(current, total_str):
            """Actualiza la barra de progreso desde el hilo."""
            if current is None:
                # Es un mensaje de texto
                self.root.after(0, lambda: self.status_lbl.configure(text=total_str))
            else:
                # Es un valor numérico
                self.root.after(0, lambda: self.progress_var.set(current))
        
        callbacks = {
            "on_finish": on_finish,
            "tg_progress": update_progress
        }
        
        # 5. Lanzar Core
        self.core.start_upload(self.config, job_config, callbacks)

    def _restore_ui(self):
        """Restaura la interfaz al finalizar."""
        self.btn_start.configure(state="normal", text="🚀 INICIAR PROCESO DE SUBIDA")
        self.status_lbl.configure(text="✅ Proceso finalizado. Verifica la consola para detalles.")
        self.progress_bar['value'] = 100
        
        messagebox.showinfo("Completado", "El proceso de subida ha terminado.\nRevisa la pestaña 'Gestor Base de Datos' para confirmar los cambios.")
        
        # Recargar la pestaña de BD automáticamente
        self.tab_db.refresh_tree()

# ==========================================================
# BOOTSTRAP (PUNTO DE ENTRADA)
# ==========================================================
if __name__ == "__main__":
    # Cargar Configuración Básica
    config_path = "config/config.json"
    default_config = {
        "okru": {"headless": False, "profile_path": "config/chrome_profile_okru"}, 
        "telegram": {}, 
        "youtube": {}
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except:
            config = default_config
    else:
        config = default_config

    # Iniciar Ventana
    root = tk.Tk()
    
    # Intentar poner icono si existe
    try: root.iconbitmap("icon.ico") 
    except: pass
    
    app = ManualUploaderApp(root, config)
    root.mainloop()