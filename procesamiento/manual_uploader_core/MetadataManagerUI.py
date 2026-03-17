import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk # Requiere pip install pillow
import requests
from io import BytesIO
import threading
from ..libs.utils import REPO_ROOT

class MetadataManagerUI:
    def __init__(self, parent, core):
        self.parent = parent
        self.core = core
        
        self._setup_ui()
        self.refresh_list()

    def _setup_ui(self):
        # --- DIVISIÓN PRINCIPAL (PANED WINDOW) ---
        paned = ttk.PanedWindow(self.parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # === PANEL IZQUIERDO: LISTA DE SERIES ===
        left_frame = ttk.Frame(paned, width=300)
        paned.add(left_frame, weight=1)
        
        # Toolbar superior izquierda
        l_toolbar = ttk.Frame(left_frame)
        l_toolbar.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(l_toolbar, text="Mis Series", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        
        # Botón Sincronizar Nube (NUEVO)
        btn_sync = ttk.Button(l_toolbar, text="☁️ Procesar y Sincronizar", command=self._sync_cloud)
        btn_sync.pack(side=tk.RIGHT)
        
        # Treeview para listar
        self.tree = ttk.Treeview(left_frame, columns=("Status"), show="headings", selectmode="browse")
        self.tree.heading("Status", text="Serie / Estado")
        self.tree.column("Status", width=200)
        
        # Scrollbar para la lista
        sb_tree = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb_tree.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_tree.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind("<<TreeviewSelect>>", self._on_select_show)
        
        # Botón Recargar DB
        btn_refresh = ttk.Button(left_frame, text="🔄 Recargar desde DB", command=self.refresh_list)
        btn_refresh.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        # === PANEL DERECHO: EDICIÓN (SCROLLABLE) ===
        right_outer_frame = ttk.Frame(paned)
        paned.add(right_outer_frame, weight=4)
        
        # Canvas + Scrollbar para permitir scroll si hay muchas temporadas
        self.canvas = tk.Canvas(right_outer_frame)
        sb_canvas = ttk.Scrollbar(right_outer_frame, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = ttk.Frame(self.canvas)
        
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=sb_canvas.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        sb_canvas.pack(side="right", fill="y")
        
        # Mensaje inicial
        self.lbl_placeholder = ttk.Label(self.scroll_frame, text="Selecciona una serie de la izquierda para editar sus metadatos.", foreground="gray")
        self.lbl_placeholder.pack(pady=50, padx=20)

    def refresh_list(self):
        """Recarga la lista de series desde el Core"""
        self.core.load_data()
        
        # Limpiar
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Llenar
        for show in self.core.shows_list:
            # Check visual si ya tiene datos
            has_data = show in self.core.metadata
            icon = "✅" if has_data else "⚠️"
            display_text = f"{icon}  {show}"
            
            self.tree.insert("", "end", values=(display_text,), tags=(show,))

    def _on_select_show(self, event):
        sel = self.tree.selection()
        if not sel: return
        
        # Obtener el nombre real del show (lo guardamos en tags o parseando el texto)
        # El texto visible es "✅ SHOW", pero necesitamos el ID real. 
        # Opción fácil: extraer del tag que guardamos al insertar
        try:
            show_name = self.tree.item(sel[0], "tags")[0]
            self._load_editor(show_name)
        except: pass

    def _load_editor(self, show_name):
        # Limpiar formulario anterior
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
            
        current_data = self.core.metadata.get(show_name, {})
        
        # --- HEADER ---
        ttk.Label(self.scroll_frame, text=f"Editando: {show_name}", font=("Segoe UI", 16, "bold"), foreground="#9b59b6").pack(pady=10, anchor="w", padx=10)
        
        # --- SECCIÓN 1: DATOS GLOBALES (Portada Principal) ---
        gf = ttk.LabelFrame(self.scroll_frame, text="Portada Principal (Global)", padding=10)
        gf.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(gf, text="URL Imagen:").grid(row=0, column=0, sticky="w")
        
        v_cover = tk.StringVar(value=current_data.get("cover_url", ""))
        ent_cover = ttk.Entry(gf, textvariable=v_cover, width=50)
        ent_cover.grid(row=0, column=1, padx=5, sticky="ew")
        
        # Preview Label
        lbl_preview = ttk.Label(gf, text="Sin vista previa", background="#f0f0f0", width=20, anchor="center")
        lbl_preview.grid(row=0, column=4, rowspan=3, padx=10)
        
        # Botones
        btn_browse = ttk.Button(gf, text="📂", width=3, command=lambda: self._browse_file(v_cover, lbl_preview))
        btn_browse.grid(row=0, column=2, padx=2)
        
        btn_view = ttk.Button(gf, text="👁️", width=3, command=lambda: self._load_image_preview(v_cover.get(), lbl_preview))
        btn_view.grid(row=0, column=3, padx=2)
        
        # Descripción (Opcional)
        ttk.Label(gf, text="Sinopsis (Opcional):").grid(row=1, column=0, sticky="nw", pady=5)
        txt_desc = tk.Text(gf, height=4, width=45)
        txt_desc.grid(row=1, column=1, columnspan=3, sticky="ew", pady=5)
        if current_data.get("description"):
            txt_desc.insert("1.0", current_data.get("description"))

        # Cargar preview inicial si hay URL
        if v_cover.get(): self._load_image_preview(v_cover.get(), lbl_preview)

        # --- SECCIÓN 2: POR TEMPORADAS ---
        sf = ttk.LabelFrame(self.scroll_frame, text="Portadas por Temporada (Opcional)", padding=10)
        sf.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(sf, text="Si no defines una, se usará la global.", font=("Segoe UI", 8, "italic"), foreground="gray").pack(anchor="w", pady=5)
        
        # Recuperar temporadas detectadas en la DB
        detected_seasons = self.core.shows_seasons_map.get(show_name, [])
        saved_seasons = current_data.get("seasons", {})
        
        self.season_entries = {} # { "1": StringVar, "2": StringVar... }
        
        for season in detected_seasons:
            row_frame = ttk.Frame(sf)
            row_frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(row_frame, text=f"Temporada {season}:", width=15, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
            
            # Valor guardado o vacío
            s_val = saved_seasons.get(season, {}).get("cover_url", "")
            s_var = tk.StringVar(value=s_val)
            self.season_entries[season] = s_var
            
            ttk.Entry(row_frame, textvariable=s_var, width=45).pack(side=tk.LEFT, padx=5)
            
            # Botones Select y Preview
            ttk.Button(row_frame, text="📂", width=3, 
                       command=lambda v=s_var: self._browse_file(v)).pack(side=tk.LEFT, padx=1)
            
            ttk.Button(row_frame, text="👁️", width=3, 
                               command=lambda v=s_var: self._popup_preview(v.get())).pack(side=tk.LEFT, padx=1)

        # --- BOTÓN GUARDAR ---
        btn_save = ttk.Button(self.scroll_frame, text="💾 GUARDAR CAMBIOS METADATA LOCAL", command=lambda: self._save(show_name, v_cover, txt_desc))
        btn_save.pack(fill=tk.X, padx=20, pady=20)

    def _browse_file(self, string_var, preview_lbl=None):
        """Abre dialogo para seleccionar imagen local."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("Imagenes", "*.jpg *.png *.jpeg *.webp")])
        if path:
            string_var.set(path)
            if preview_lbl:
                self._load_image_preview(path, preview_lbl)

    def _sync_cloud(self):
        """Lanza el proceso de subida masiva."""
        confirm = messagebox.askyesno("Confirmar Sincronización", 
                                      "Esto recorrerá todas las series:\n"
                                      "1. Descargará y optimizará portadas pendientes.\n"
                                      "2. Actualizará rutas locales en metadata.\n"
                                      "3. Hará Push al repo de la Web.\n\n"
                                      "¿Continuar?")
        if not confirm: return

        # Ventana de progreso
        top = tk.Toplevel(self.parent)
        top.title("Sincronizando...")
        top.geometry("400x150")
        
        lbl_status = ttk.Label(top, text="Iniciando...", anchor="center")
        lbl_status.pack(pady=20, fill=tk.X)
        
        pb = ttk.Progressbar(top, mode="indeterminate")
        pb.pack(pady=10, padx=20, fill=tk.X)
        pb.start(10)

        def run_task():
            def update_ui(curr, total, msg):
                top.after(0, lambda: lbl_status.config(text=msg))
            
            try:
                success, changed = self.core.bulk_cloud_sync(progress_callback=update_ui)
                top.after(0, lambda: self._on_sync_finish(top, success, changed))
            except Exception as e:
                top.after(0, lambda: messagebox.showerror("Error Critico", f"Fallo en sync: {e}"))
                top.after(0, top.destroy)

        threading.Thread(target=run_task, daemon=True).start()

    def _on_sync_finish(self, top_window, success, changed):
        top_window.destroy()
        if success:
            msg = "Sincronización Web Exitosa."
            if changed: msg += "\nSe procesaron nuevas imágenes y se actualizaron metadatos."
            else: msg += "\nNo hubo cambios en imágenes."
            messagebox.showinfo("Éxito", msg)
            self.refresh_list() # Recargar por si cambiaron URLs a Cloudinary IDs
        else:
            messagebox.showwarning("Atención", "Proceso finalizado con advertencias (quizás falló el Git Push o alguna imagen). Revisar logs.")

    def _load_image_preview(self, url, label):
        """Descarga y muestra la imagen en el label dado."""
        import os
        if not url:
            label.config(image="", text="Sin Imagen")
            return

        def task():
            try:
                image = None
                
                # Caso 1: Archivo Local
                if os.path.exists(url):
                   image = Image.open(url)
                
                # Caso 2: URL Remota
                elif url.startswith("http"):
                    headers = {'User-Agent': 'Mozilla/5.0'} 
                    response = requests.get(url, headers=headers, timeout=5)
                    response.raise_for_status()
                    image = Image.open(BytesIO(response.content))

                # Caso 3: Ruta Web Local (Ej: /images/covers/foo.webp)
                elif url.startswith("/images/covers/"):
                     # Hardcoded base path (mismo que en cover_manager)
                     local_path = os.path.join(REPO_ROOT, "public", url.lstrip("/"))
                     local_path = os.path.normpath(local_path)
                     
                     if os.path.exists(local_path):
                         image = Image.open(local_path)
                     else:
                         print(f"⚠️ Imagen no encontrada en disco: {local_path}")

                # Caso 4: Public ID de Cloudinary (ej: covers/naruto)
                # No podemos previsualizarlo fácil sin construir la URL.
                else: 
                     # Intentar construir url cloudinary simple
                     cloud_name = self.core.config.get('cloudinary', {}).get('cloud_name')
                     if cloud_name:
                         full_url = f"https://res.cloudinary.com/{cloud_name}/image/upload/{url}"
                         resp = requests.get(full_url, timeout=5)
                         if resp.status_code == 200:
                             image = Image.open(BytesIO(resp.content))
                
                if image:
                    # Redimensionar manteniendo ratio (Thumbnail)
                    image.thumbnail((120, 180)) 
                    photo = ImageTk.PhotoImage(image)
                    
                    # Actualizar UI en hilo principal
                    def update():
                        label.config(image=photo, text="")
                        label.image = photo 
                    self.parent.after(0, update)
                else:
                    self.parent.after(0, lambda: label.config(image="", text="No Preview"))
                
            except Exception as e:
                def fail():
                    label.config(image="", text="Error Carga")
                    # print(f"Error imagen: {e}")
                self.parent.after(0, fail)
        
        # Ejecutar en hilo secundario para no congelar la app
        threading.Thread(target=task, daemon=True).start()

    def _popup_preview(self, url):
        """Muestra una ventana emergente rápida con la imagen"""
        if not url: return
        top = tk.Toplevel(self.parent)
        top.title("Vista Previa")
        top.geometry("300x450")
        
        lbl = ttk.Label(top, text="Cargando...")
        lbl.pack(expand=True)
        
        self._load_image_preview(url, lbl)

    def _save(self, show_name, var_cover, txt_desc):
        # 1. Recopilar datos
        new_data = {
            "cover_url": var_cover.get().strip(),
            "description": txt_desc.get("1.0", tk.END).strip(),
            "provider": "Manual",
            "seasons": {}
        }
        
        # 2. Recopilar temporadas
        for s_num, s_var in self.season_entries.items():
            val = s_var.get().strip()
            if val:
                new_data["seasons"][s_num] = {
                    "cover_url": val
                }
        
        # 3. Guardar
        if self.core.update_show_data(show_name, new_data):
            messagebox.showinfo("Éxito", f"Datos de '{show_name}' guardados localmente.\nUsa el botón 'Sincronizar Todo' para subir cambios a la nube.")
            self.refresh_list() # Para actualizar el icono ✅
        else:
            messagebox.showerror("Error", "No se pudo guardar el archivo JSON.")