import tkinter as tk
from tkinter import ttk, messagebox
from manual_uploader_core.DatabaseManagerCore import DatabaseManagerCore
import json
from libs.utils import CONTENT_TYPE
from libs.ui_components import StreamerDateSessionFrame

class DatabaseManagerUI(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.core = DatabaseManagerCore()
        self.current_selection = None # Tupla (session_idx, reaction_idx)
        
        # Estilos específicos para este componente
        self._setup_styles()
        self._setup_layout()
        
        # Cargar datos iniciales
        self.refresh_tree()

    def _setup_styles(self):
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)
        style.map("Treeview", background=[('selected', '#0078d7')])

    def _setup_layout(self):
        """Configura el panel dividido (Izquierda: Árbol, Derecha: Editor)."""
        # PanedWindow: Permite redimensionar las dos mitades
        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ==========================================================
        # PANEL IZQUIERDO: ÁRBOL DE CONTENIDO
        # ==========================================================
        frame_left = ttk.Frame(self.paned)
        self.paned.add(frame_left, weight=1)

        # Toolbar superior (Botones de acción rápida)
        toolbar = ttk.Frame(frame_left)
        toolbar.pack(fill=tk.X, pady=2)
        
        ttk.Button(toolbar, text="🔄 Recargar", command=self.refresh_tree).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="➕ Nueva Sesión", command=self._new_session).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="🗑️ Eliminar Item", command=self._delete_item).pack(side=tk.LEFT)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)
        ttk.Button(toolbar, text="☁️ Subida a la Nube", command=self._cloud_sync).pack(side=tk.LEFT)

        # Treeview (Jerarquía)
        self.tree = ttk.Treeview(frame_left, selectmode="browse")
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        # Scrollbar vertical
        sb = ttk.Scrollbar(frame_left, orient="vertical", command=self.tree.yview)
        sb.pack(fill=tk.Y, side=tk.RIGHT)
        self.tree.configure(yscrollcommand=sb.set)
        
        self.tree.heading("#0", text="Historial de Streams", anchor="w")
        
        # Evento: Al hacer clic en un item
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # ==========================================================
        # PANEL DERECHO: EDITOR (Contenedor vacío por ahora)
        # ==========================================================
        self.frame_right = ttk.LabelFrame(self.paned, text="Editor de Metadatos", padding=15)
        self.paned.add(self.frame_right, weight=3) # Más ancho que el árbol
        
        # Aquí se inyectarán los formularios dinámicamente
        self.form_container = ttk.Frame(self.frame_right)
        self.form_container.pack(fill=tk.BOTH, expand=True)
        
        # Mensaje por defecto
        self.lbl_placeholder = ttk.Label(
            self.form_container, 
            text="👈 Selecciona una Sesión o Reacción del menú izquierdo para editarla.", 
            foreground="#888", font=("Segoe UI", 10, "italic")
        )
        self.lbl_placeholder.pack(pady=50)

    def refresh_tree(self):
        """Lee la BD y repuebla el árbol visualmente."""
        # Intentar preservar la selección actual tras recargar
        selected_items = self.tree.selection()
        last_selected_id = selected_items[0] if selected_items else None
        
        # Limpiar árbol
        self.tree.delete(*self.tree.get_children())
        
        # Cargar datos frescos
        sessions = self.core.get_all_sessions()
        
        for idx, s in enumerate(sessions):
            # 1. Nodo Padre: La Sesión
            vod_status = s.get("youtube_vod", {}).get("status", "pending")
            
            # Icono visual según estado VOD
            icon = "🟢" if vod_status == "uploaded" else "🔴" if vod_status == "failed" else "⚪"
            text = f"{s.get('streamer', 'N/A')} - {s.get('date_str', 'N/A')} [{icon} VOD]"
            
            session_id = f"S_{idx}" # ID único para el árbol
            self.tree.insert("", "end", session_id, text=text, open=False)
            
            # 2. Nodos Hijos: Las Reacciones
            for r_idx, r in enumerate(s.get("reactions", [])):
                ok = "✅" if r.get("ok_status") == "uploaded" else "⛔"
                tg = "✅" if r.get("tg_status") == "uploaded" else "⛔"
                
                # Texto descriptivo: Serie + Ep + Estados
                r_text = f"{r.get('show_id', 'Varios')} {r.get('episode','')} [OK:{ok} TG:{tg}]"
                reac_id = f"R_{idx}_{r_idx}" # ID único hijo
                
                self.tree.insert(session_id, "end", reac_id, text=r_text)

        # Restaurar selección si el ID aún existe
        if last_selected_id and self.tree.exists(last_selected_id):
            self.tree.selection_set(last_selected_id)
            self.tree.see(last_selected_id)

    def _on_select(self, event):
        """Manejador de evento: Determina qué formulario mostrar."""
        sel = self.tree.selection()
        if not sel:
            return
        
        item_id = sel[0]
        self._clear_form() # Limpiar panel derecho
        
        if item_id.startswith("S_"):
            # Usuario seleccionó una SESIÓN
            s_idx = int(item_id.split("_")[1])
            self.current_selection = (s_idx, None)
            
            data = self.core.get_item_data(s_idx)
            self._render_session_form(data) # Definido en Parte II
            
        elif item_id.startswith("R_"):
            # Usuario seleccionó una REACCIÓN
            parts = item_id.split("_")
            s_idx = int(parts[1])
            r_idx = int(parts[2])
            self.current_selection = (s_idx, r_idx)
            
            data = self.core.get_item_data(s_idx, r_idx)
            self._render_reaction_form(data) # Definido en Parte II

    def _clear_form(self):
        """Elimina todos los widgets del panel derecho."""
        for widget in self.form_container.winfo_children():
            widget.destroy()

    # ==========================================================
    # RENDERIZADO DE FORMULARIOS (PANEL DERECHO)
    # ==========================================================
    def _render_session_form(self, data):
        """Dibuja el formulario para editar una SESIÓN (VOD)."""
        if not data: return
        
        # Variables vinculadas a los campos
        self.v_streamer = tk.StringVar(value=data["streamer"])
        self.v_date = tk.StringVar(value=data["date_str"])
        self.v_vod_file = tk.StringVar(value=data["vod_filename"])
        self.v_vod_status = tk.StringVar(value=data["vod_status"])
        self.v_vod_id = tk.StringVar(value=data["vod_id"])
        
        # --- Encabezado ---
        ttk.Label(self.form_container, text="EDITAR SESIÓN", font=("Segoe UI", 12, "bold"), foreground="#0078d7").pack(anchor="w", pady=(0, 10))
        
        # --- Datos Generales ---
        gf = ttk.LabelFrame(self.form_container, text="Datos Generales", padding=10)
        gf.pack(fill=tk.X, pady=5)
        
        self.session_frame = StreamerDateSessionFrame(
            gf,
            core_instance=self.core,
            var_streamer=self.v_streamer,
            var_date=self.v_date,
            streamer_width=28,
            date_width=18
        )
        self.session_frame.pack(side=tk.LEFT, padx=5)

        # --- Datos del VOD ---
        vf = ttk.LabelFrame(self.form_container, text="VOD de YouTube (Compilado)", padding=10)
        vf.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Fila 1: Archivo
        ttk.Label(vf, text="Nombre Archivo:").grid(row=0, column=0, sticky="w")
        ttk.Entry(vf, textvariable=self.v_vod_file, width=50).grid(row=0, column=1, columnspan=3, sticky="ew", padx=5, pady=2)
        
        # Fila 2: Estado y ID
        ttk.Label(vf, text="Estado:").grid(row=1, column=0, sticky="w")
        ttk.Combobox(vf, textvariable=self.v_vod_status, values=["uploaded", "pending", "failed", "skipped", "quota_exceeded"], width=15).grid(row=1, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(vf, text="YouTube ID:").grid(row=1, column=2, sticky="e")
        ttk.Entry(vf, textvariable=self.v_vod_id, width=20).grid(row=1, column=3, sticky="w", padx=5, pady=2)
        
        # --- Capítulos VOD Dinámicos ---
        cf = ttk.LabelFrame(self.form_container, text="Capítulos del Video (Timestamps)", padding=10)
        cf.pack(fill=tk.BOTH, expand=True, pady=10)

        # Toolbar Capítulos
        ctb = ttk.Frame(cf)
        ctb.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(ctb, text="➕ Agregar Capítulo", command=self._add_chapter_row).pack(side=tk.LEFT)
        
        # Header de las columnas
        ch_head = ttk.Frame(cf)
        ch_head.pack(fill=tk.X, pady=2)
        ttk.Label(ch_head, text="Timestamp", width=12).pack(side=tk.LEFT, padx=2)
        ttk.Label(ch_head, text="Título (Serie/Reacción)", width=35).pack(side=tk.LEFT, padx=2)
        ttk.Label(ch_head, text="Saltado (Motivo)", width=15).pack(side=tk.LEFT, padx=2)

        # Contenedor Scrolleable para las filas
        self.canvas_ch = tk.Canvas(cf, height=150, highlightthickness=0)
        self.scrollbar_ch = ttk.Scrollbar(cf, orient="vertical", command=self.canvas_ch.yview)
        self.scrollable_frame_ch = ttk.Frame(self.canvas_ch)

        self.scrollable_frame_ch.bind(
            "<Configure>",
            lambda e: self.canvas_ch.configure(scrollregion=self.canvas_ch.bbox("all"))
        )
        self.canvas_window_ch = self.canvas_ch.create_window((0, 0), window=self.scrollable_frame_ch, anchor="nw")
        
        # Ajustar ancho del frame al canvas
        self.canvas_ch.bind('<Configure>', lambda e: self.canvas_ch.itemconfig(self.canvas_window_ch, width=e.width))

        self.canvas_ch.configure(yscrollcommand=self.scrollbar_ch.set)
        
        self.canvas_ch.pack(side="left", fill="both", expand=True)
        self.scrollbar_ch.pack(side="right", fill="y")
        
        # Mousewheel binding
        def _on_mousewheel(event):
            self.canvas_ch.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas_ch.bind_all("<MouseWheel>", _on_mousewheel)

        self.chapter_rows = []
        
        # Poblar Capítulos
        chapters = data.get("vod_chapters", [])
        if chapters:
            for c in chapters:
                self._add_chapter_row(c.get("timestamp", ""), c.get("title", ""), c.get("skipped", ""))
        else:
            # Añadir fila vacía por defecto
            self._add_chapter_row()
            
        # --- Botones de Acción ---
        bf = ttk.Frame(self.form_container, padding=10)
        bf.pack(fill=tk.X, side=tk.BOTTOM)
        
        ttk.Button(bf, text="💾 Guardar Cambios", command=self._save_session).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bf, text="➕ Añadir Reacción a esta sesión", command=self._add_reaction_to_session).pack(side=tk.LEFT)

    def _add_chapter_row(self, ts="", title="", skipped=""):
        row_f = ttk.Frame(self.scrollable_frame_ch)
        row_f.pack(fill=tk.X, pady=2)
        
        v_ts = tk.StringVar(value=ts)
        v_title = tk.StringVar(value=title)
        v_skip = tk.StringVar(value=skipped)
        
        ttk.Entry(row_f, textvariable=v_ts, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Entry(row_f, textvariable=v_title, width=35).pack(side=tk.LEFT, padx=2)
        ttk.Entry(row_f, textvariable=v_skip, width=15).pack(side=tk.LEFT, padx=2)
        
        def _delete_row():
            row_f.destroy()
            self.chapter_rows = [r for r in self.chapter_rows if r['frame'] != row_f]
            
        ttk.Button(row_f, text="🗑️", width=3, command=_delete_row).pack(side=tk.LEFT, padx=5)
        
        self.chapter_rows.append({
            "frame": row_f,
            "ts": v_ts,
            "title": v_title,
            "skipped": v_skip
        })

    def _render_reaction_form(self, data):
        """Dibuja el formulario para editar una REACCIÓN individual."""
        if not data: return
        
        # Variables
        self.v_fname = tk.StringVar(value=data["filename"])
        self.v_show = tk.StringVar(value=data["show_id"])
        self.v_season = tk.StringVar(value=data.get("season", ""))
        self.v_ep = tk.StringVar(value=data["episode"])
        self.v_type = tk.StringVar(value=data["material_type"])
        self.v_ok = tk.StringVar(value=data["ok_status"])
        self.v_tg = tk.StringVar(value=data["tg_status"])
        self.v_ok_url = tk.StringVar(value=data.get("ok_url", ""))
        
        # Nuevas variables de Telegram
        self.v_tg_msg_id = tk.StringVar(value=str(data.get("tg_message_id", "")))
        self.v_tg_file_unq = tk.StringVar(value=str(data.get("tg_file_unique_id", "")))
        self.v_tg_file_size = tk.StringVar(value=str(data.get("tg_file_size", "")))
        self.v_tg_split = tk.StringVar(value=str(data.get("tg_split_parts", "")))

        self.current_raw_json = data.get("raw_json", {}) # Guardamos ref para el botón

        # --- Encabezado con Botón JSON ---
        h_frame = ttk.Frame(self.form_container)
        h_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(h_frame, text="EDITAR REACCIÓN", font=("Segoe UI", 12, "bold"), foreground="#e04f5f").pack(side=tk.LEFT)
        # Botón pequeña para ver JSON
        ttk.Button(h_frame, text="📄 JSON", width=6, command=self._view_json_popup).pack(side=tk.RIGHT)

        # --- Datos del Archivo ---
        rf = ttk.LabelFrame(self.form_container, text="Metadatos del Contenido", padding=10)
        rf.pack(fill=tk.X, pady=5)
        
        ttk.Label(rf, text="Archivo Original:").pack(anchor="w")
        ttk.Entry(rf, textvariable=self.v_fname, width=60).pack(fill=tk.X, pady=(0, 10))
        
        # Grid para Show/Ep
        f_grid = ttk.Frame(rf)
        f_grid.pack(fill=tk.X)
        
        ttk.Label(f_grid, text="Serie / Show:").grid(row=0, column=0, sticky="w")
        
        self.cb_show = ttk.Combobox(f_grid, textvariable=self.v_show, values=self.core.get_series_history(), width=23)
        self.cb_show.grid(row=0, column=1, sticky="ew", padx=5)
        self.cb_show.bind("<<ComboboxSelected>>", self._on_show_selected)
        
        # --- AGREGADO: Temporada ---
        ttk.Label(f_grid, text="Temp:").grid(row=0, column=2, sticky="w")
        ttk.Entry(f_grid, textvariable=self.v_season, width=8).grid(row=0, column=3, sticky="ew", padx=5)
        
        ttk.Label(f_grid, text="Ep:").grid(row=0, column=4, sticky="w")
        ttk.Entry(f_grid, textvariable=self.v_ep, width=10).grid(row=0, column=5, sticky="ew", padx=5)
        
        ttk.Label(f_grid, text="Tipo:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Combobox(f_grid, textvariable=self.v_type, values=CONTENT_TYPE).grid(row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=5)

        url_frame = ttk.LabelFrame(self.form_container, text="Enlaces y Referencias", padding=10)
        url_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(url_frame, text="URL OK.ru:").grid(row=0, column=0, sticky="w")
        ttk.Entry(url_frame, textvariable=self.v_ok_url, width=50).grid(row=0, column=1, sticky="ew", padx=5)
        
        # Thumbnail URL/Path
        self.v_thumbnail = tk.StringVar(value=data.get("thumbnail_url", ""))
        ttk.Label(url_frame, text="Thumbnail:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(url_frame, textvariable=self.v_thumbnail, width=50).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        
        def _browse_thumb():
            from tkinter import filedialog
            fn = filedialog.askopenfilename(title="Seleccionar Thumbnail", filetypes=[("Imágenes", "*.jpg *.png *.webp")])
            if fn:
                self.v_thumbnail.set(fn)
                
        ttk.Button(url_frame, text="📂", width=3, command=_browse_thumb).grid(row=1, column=2, padx=5, pady=5)

        # --- Estados de Subida ---
        sf = ttk.LabelFrame(self.form_container, text="Estado en Plataformas", padding=10)
        sf.pack(fill=tk.X, pady=10)
        
        f_status = ttk.Frame(sf)
        f_status.pack(fill=tk.X)
        
        # OK.ru
        ttk.Label(f_status, text="OK.ru:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Combobox(f_status, textvariable=self.v_ok, values=["uploaded", "pending", "failed", "skipped"], width=12).pack(side=tk.LEFT, padx=5)
        
        # Telegram
        ttk.Label(f_status, text="Telegram:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(20, 0))
        ttk.Combobox(f_status, textvariable=self.v_tg, values=["uploaded", "pending", "failed", "skipped"], width=12).pack(side=tk.LEFT, padx=5)

        # --- Metadatos Técnicos Telegram ---
        tg_tech = ttk.LabelFrame(self.form_container, text="Metadatos Técnicos Telegram", padding=10)
        tg_tech.pack(fill=tk.X, pady=5)
        
        ttk.Label(tg_tech, text="Message ID:").grid(row=0, column=0, sticky="w")
        ttk.Entry(tg_tech, textvariable=self.v_tg_msg_id, width=15).grid(row=0, column=1, sticky="w", padx=5)
        
        ttk.Label(tg_tech, text="Unique ID:").grid(row=0, column=2, sticky="w", padx=10)
        ttk.Entry(tg_tech, textvariable=self.v_tg_file_unq, width=25).grid(row=0, column=3, sticky="w", padx=5)
        
        ttk.Label(tg_tech, text="File Size:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(tg_tech, textvariable=self.v_tg_file_size, width=15).grid(row=1, column=1, sticky="w", padx=5, pady=5)
        
        ttk.Label(tg_tech, text="Split Parts:").grid(row=1, column=2, sticky="w", padx=10, pady=5)
        ttk.Entry(tg_tech, textvariable=self.v_tg_split, width=10).grid(row=1, column=3, sticky="w", padx=5, pady=5)

        # --- Botón Guardar ---
        ttk.Button(self.form_container, text="💾 Guardar Reacción", command=self._save_reaction).pack(side=tk.BOTTOM, anchor="e", pady=20)

    # ==========================================================
    # LÓGICA CRUD (BOTONES)
    # ==========================================================
    def _save_session(self):
        s_idx, _ = self.current_selection
        
        # Desvincular mousewheel al guardar/cambiar
        self.canvas_ch.unbind_all("<MouseWheel>")
        
        # Recolectar de la lista dinámica
        chapters = []
        for row in self.chapter_rows:
            ts = row['ts'].get().strip()
            title = row['title'].get().strip()
            skipped = row['skipped'].get().strip()
            
            if ts or title:
                chapters.append({
                    "timestamp": ts,
                    "title": title,
                    "skipped": skipped
                })
        
        # Recolectar datos del formulario
        new_data = {
            "streamer": self.v_streamer.get(),
            "date_str": self.v_date.get(),
            "vod_filename": self.v_vod_file.get(),
            "vod_status": self.v_vod_status.get(),
            "vod_id": self.v_vod_id.get(),
            "vod_chapters": chapters
        }
        
        # Guardar en Core
        if self.core.update_session(s_idx, new_data):
            self.refresh_tree()
            messagebox.showinfo("Éxito", "Sesión actualizada correctamente.")

    def _save_reaction(self):
        s_idx, r_idx = self.current_selection
        new_data = {
            "filename": self.v_fname.get(),
            "show_id": self.v_show.get(),
            "season": self.v_season.get(),
            "episode": self.v_ep.get(),
            "material_type": self.v_type.get(),
            "ok_status": self.v_ok.get(),
            "tg_status": self.v_tg.get(),
            "ok_url": self.v_ok_url.get(),
            "tg_message_id": self.v_tg_msg_id.get(),
            "tg_file_unique_id": self.v_tg_file_unq.get(),
            "tg_file_size": self.v_tg_file_size.get(),
            "tg_split_parts": self.v_tg_split.get(),
            "thumbnail_url": self.v_thumbnail.get()
        }
        
        if self.core.update_reaction(s_idx, r_idx, new_data):
            self.refresh_tree()
            messagebox.showinfo("Éxito", "Reacción actualizada.")

    def _on_show_selected(self, event=None):
        show = self.v_show.get().strip()
        info = self.core.get_last_info(show)
        if info:
            self.v_show.set(info.get('title', show) or show)
            self.v_season.set(info.get('season') or '')
            self.v_ep.set(info.get('episode') or '')
            self.v_type.set(info.get('material_type', 'Gameplay'))

    def _new_session(self):
        self.core.create_session()
        self.refresh_tree()
        # Seleccionar la nueva sesión (índice 0)
        item_id = "S_0"
        if self.tree.exists(item_id):
            self.tree.selection_set(item_id)
            self.tree.see(item_id)

    def _add_reaction_to_session(self):
        # Asegurarse de que estamos en una sesión
        if not self.current_selection or self.current_selection[0] is None:
            messagebox.showwarning("Error", "Selecciona una sesión primero.")
            return

        s_idx = self.current_selection[0]
        self.core.create_reaction(s_idx)
        self.refresh_tree()
        
        # Expandir la sesión para ver la nueva reacción
        session_id = f"S_{s_idx}"
        self.tree.item(session_id, open=True)
        # Seleccionar la última reacción
        children = self.tree.get_children(session_id)
        if children:
            self.tree.selection_set(children[-1])
            self.tree.see(children[-1])

    def _delete_item(self):
        sel = self.tree.selection()
        if not sel: 
            messagebox.showinfo("Info", "Selecciona un item para eliminar.")
            return
        
        item_id = sel[0]
        
        # --- LÓGICA DE MENSAJE PERSONALIZADO ---
        confirm_msg = ""
        
        if item_id.startswith("S_"):
            # Es una SESIÓN
            s_idx = int(item_id.split("_")[1])
            data = self.core.get_item_data(s_idx) # Recuperamos datos para mostrar el nombre
            
            if data:
                nombre = f"{data.get('streamer', 'Desconocido')} - {data.get('date_str', 'Sin Fecha')}"
                confirm_msg = (f"¿Estás seguro de eliminar la SESIÓN COMPLETA:\n\n"
                               f"👉 {nombre}?\n\n"
                               f"⚠️ ESTO BORRARÁ EL VOD Y TODAS SUS REACCIONES ASOCIADAS.\n"
                               f"Esta acción es irreversible.")
            else:
                confirm_msg = "¿Estás seguro de eliminar esta sesión?"

        elif item_id.startswith("R_"):
            # Es una REACCIÓN
            parts = item_id.split("_")
            s_idx = int(parts[1])
            r_idx = int(parts[2])
            data = self.core.get_item_data(s_idx, r_idx) # Recuperamos datos de la reacción
            
            if data:
                nombre = f"{data.get('show_id', 'Show')} {data.get('episode', 'Ep')}"
                confirm_msg = (f"¿Estás seguro de eliminar la REACCIÓN INDIVIDUAL:\n\n"
                               f"👉 {nombre}?\n\n"
                               f"Esta acción es irreversible.")
            else:
                confirm_msg = "¿Estás seguro de eliminar esta reacción?"

        # --- MOSTRAR CONFIRMACIÓN ---
        confirm = messagebox.askyesno("Confirmar Eliminación", confirm_msg)
        if not confirm: return

        # --- EJECUTAR BORRADO ---
        if item_id.startswith("S_"):
            s_idx = int(item_id.split("_")[1])
            self.core.delete_item(s_idx)
        elif item_id.startswith("R_"):
            parts = item_id.split("_")
            self.core.delete_item(int(parts[1]), int(parts[2]))
            
        self.refresh_tree()
        self._clear_form()

    def _cloud_sync(self):
        confirm = messagebox.askyesno("Confirmar Sincronización", "¿Deseas procesar thumbnails pendientes y subir los metadatos a la nube (GitHub)?")
        if not confirm: 
            return
            
        import threading
        def run_sync():
            try:
                # 1. Procesar thumbnails pendientes primero
                self.core.process_pending_thumbnails()
                
                # 2. Sincronizar base de datos
                success = self.core.sync_to_cloud()
                if success:
                    self.after(0, lambda: messagebox.showinfo("Éxito", "¡Procesamiento y sincronización finalizados correctamente!"))
                    self.after(0, self.refresh_tree)
                else:
                    self.after(0, lambda: messagebox.showerror("Fallido", "Ocurrió un error en el despliegue a GitHub. Revisa la consola."))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: messagebox.showerror("Error", f"Fallo catastrófico: {err_msg}"))
                
        # Inhabilito interacciones bloqueando por un breve modal
        threading.Thread(target=run_sync, daemon=True).start()
        messagebox.showinfo("Procesando", "El procesamiento batch y subida ha comenzado en segundo plano. Te avisaremos cuando finalice.\nVisualiza la consola para más detalles.", parent=self)

    def _view_json_popup(self):
        """Muestra una ventana emergente con el JSON crudo."""
        if not hasattr(self, 'current_raw_json'): return
        
        top = tk.Toplevel(self)
        top.title("Vista JSON Raw")
        top.geometry("500x400")
        
        txt = tk.Text(top, font=("Consolas", 10))
        txt.pack(fill=tk.BOTH, expand=True)
        
        # Formatear JSON bonito
        json_str = json.dumps(self.current_raw_json, indent=4, ensure_ascii=False)
        txt.insert("1.0", json_str)
        txt.configure(state="disabled") # Solo lectura para evitar bugs de edición manual del JSON estructura