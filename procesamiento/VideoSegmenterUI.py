import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import threading
import queue
import os
import json
import logging
from datetime import datetime
from tkcalendar import DateEntry

# Importamos el Core actualizado
from video_segmenter_core.VideoSegmenterCore import VideoSegmenterCore, TIPOS_MATERIAL
from manual_uploader_core.MetadataManagerCore import MetadataManagerCore
from libs.cloudinary_manager import CloudinaryManager
from libs.cover_manager import process_cover
from libs.utils import format_spanish_date
from libs.ui_components import StreamerDateSessionFrame

class VideoSegmenterUI:
    def __init__(self, root):
        self.root = root
        self.root.title("VideoSegmenter Ultimate V9.0 (Recovery & Stop)")
        self.root.geometry("1150x950")
        self.root.option_add('*Foreground', 'black')

        # --- Comunicación Thread-Safe ---
        self.log_queue = queue.Queue()
        self.core = VideoSegmenterCore(self.log_queue)
        
        # Gestor de Metadata y Cloudinary
        self.metadata_mgr = MetadataManagerCore()
        self.metadata_mgr.load_data()
        
        self.cloudinary = None
        self._load_config()

        # Estado UI
        self.editing_id = None
        self.series_list = []
        self.processing = False # Flag de estado

        self._init_vars()
        self._build_ui()
        
        # Loop de logs y chequeo de estado
        self.root.after(100, self.process_log_queue)

    def _load_config(self):
        try:
            if os.path.exists('config/config.json'):
                with open('config/config.json', 'r') as f:
                    self.config = json.load(f)
                    self.cloudinary = CloudinaryManager(self.config)
            else:
                self.config = {}
        except Exception as e:
            logging.error(f"Error cargando config: {e}")
            self.config = {}

    def _init_vars(self):
        # Variables Tiempos
        self.var_start = tk.StringVar(value="00:00:00")
        self.var_end = tk.StringVar(value="00:00:00")
        
        # Variables Nombres
        self.var_n_streamer = tk.StringVar()
        self.var_n_date = tk.StringVar()
        self.var_n_content = tk.StringVar()
        self.var_n_season = tk.StringVar()
        self.var_n_episode = tk.StringVar()
        self.var_n_episode = tk.StringVar()
        self.var_final_name = tk.StringVar()
        self.var_material_type = tk.StringVar(value=TIPOS_MATERIAL[0])
        
        # New Series Vars
        self.var_new_desc = tk.StringVar()
        self.var_new_cover_url = tk.StringVar()
        self.is_new_series = False

        # Triggers
        for var in [self.var_n_streamer, self.var_n_date, 
                   self.var_n_season, self.var_n_episode]:
            var.trace("w", self.update_name_preview)
        
        # Trace especial para detectar serie
        self.var_n_content.trace("w", self.on_content_change)

        # Checkboxes Segmento
        self.chk_ind_ok = tk.BooleanVar(value=True)
        self.chk_ind_tg = tk.BooleanVar(value=True)
        self.chk_ind_yt = tk.BooleanVar(value=True)
        self.chk_save_db = tk.BooleanVar(value=True)

        # Config Global
        self.var_precise_mode = tk.BooleanVar(value=False)
        self.var_hw_accel = tk.BooleanVar(value=True)
        self.var_gen_youtube = tk.BooleanVar(value=True)
        self.var_auto_upload = tk.BooleanVar(value=False)
        self.var_close_chrome = tk.BooleanVar(value=True)

    def _build_ui(self):
        # 1. Carga
        f_top = tk.LabelFrame(self.root, text="1. Archivo de Origen", padx=10, pady=5)
        f_top.pack(fill="x", padx=10, pady=5)
        tk.Button(f_top, text="📂 Cargar Video", command=self.load_video, bg="#e3f2fd").pack(side="left", padx=5)
        self.lbl_info = tk.Label(f_top, text="Sin archivo...", fg="gray")
        self.lbl_info.pack(side="left", padx=10)
        self.lbl_tech = tk.Label(f_top, text="", fg="#1565C0", font=("Consolas", 9))
        self.lbl_tech.pack(side="right", padx=10)

        # 2. Editor
        self.f_edit = tk.LabelFrame(self.root, text="2. Editor de Cortes", padx=10, pady=10)
        self.f_edit.pack(fill="x", padx=10, pady=5)
        
        # Tiempos
        f_t = tk.Frame(self.f_edit)
        f_t.pack(fill="x", pady=5)
        
        tk.Label(f_t, text="INICIO:", fg="#2e7d32", font=("Arial", 9, "bold")).pack(side="left")
        self.e_start = tk.Entry(f_t, textvariable=self.var_start, width=10)
        self.e_start.pack(side="left", padx=5)
        self.e_start.bind('<Return>', self.on_entry_change); self.e_start.bind('<FocusOut>', self.on_entry_change)
        
        self.s_start = ttk.Scale(f_t, from_=0, to=100, command=self.on_slider_start)
        self.s_start.pack(side="left", fill="x", expand=True, padx=5)

        tk.Label(f_t, text="FIN:", fg="#c62828", font=("Arial", 9, "bold")).pack(side="left")
        self.e_end = tk.Entry(f_t, textvariable=self.var_end, width=10)
        self.e_end.pack(side="left", padx=5)
        self.e_end.bind('<Return>', self.on_entry_change); self.e_end.bind('<FocusOut>', self.on_entry_change)
        
        self.s_end = ttk.Scale(f_t, from_=0, to=100, command=self.on_slider_end)
        self.s_end.pack(side="left", fill="x", expand=True, padx=5)
        
        tk.Button(f_t, text="🧲 Imantar", command=self.snap_to_keyframes, bg="#607D8B", fg="white").pack(side="right", padx=5)

        # Nombres
        f_name = tk.LabelFrame(self.f_edit, text="Metadatos", padx=5, pady=5)
        f_name.pack(fill="x", pady=10)
        
        headers = ["Serie o Episodio", "Temp", "Ep", "Tipo"]
        widths = [25, 5, 5, 12]
        for i, h in enumerate(headers): tk.Label(f_name, text=h, font=("Arial", 8)).grid(row=0, column=i+2, sticky="w")
        
        # Agregamos el componente Custom Streamer/Fecha a la izquierda (Columnas 0,1 unidas)
        self.session_frame = StreamerDateSessionFrame(
            f_name, 
            core_instance=self.core,
            var_streamer=self.var_n_streamer,
            var_date=self.var_n_date,
            streamer_width=12,
            date_width=16,
            layout="vertical",
            label_font=("Arial", 8)
        )
        self.session_frame.grid(row=0, column=0, rowspan=2, columnspan=2, padx=0, sticky="nw")
        
        # Resto de los campos (Serie, Temp, Ep, Tipo) a la derecha
        self.series_list = self.core.get_series_history()
        self.combo_content = ttk.Combobox(f_name, textvariable=self.var_n_content, values=self.series_list, width=widths[0])
        self.combo_content.grid(row=1, column=2, padx=2)
        self.combo_content.bind("<<ComboboxSelected>>", self.on_series_selected)
        
        tk.Entry(f_name, textvariable=self.var_n_season, width=widths[1]).grid(row=1, column=3, padx=2)
        tk.Entry(f_name, textvariable=self.var_n_episode, width=widths[2]).grid(row=1, column=4, padx=2)
        
        self.combo_mat = ttk.Combobox(f_name, textvariable=self.var_material_type, values=TIPOS_MATERIAL, state="readonly", width=widths[3])
        self.combo_mat.grid(row=1, column=5, padx=2)

        # Panel para Serie Nueva (Oculto por defecto)
        self.f_new_series = tk.LabelFrame(self.f_edit, text="✨ Nueva Serie Detectada", padx=5, pady=5, fg="blue")
        # No lo hacemos pack/grid al inicio
        
        tk.Label(self.f_new_series, text="Descripción:").pack(side="left")
        tk.Entry(self.f_new_series, textvariable=self.var_new_desc, width=40).pack(side="left", padx=5)
        
        self.btn_cover = tk.Button(self.f_new_series, text="🖼️ Subir Portada", command=self.upload_cover, bg="#E91E63", fg="white")
        self.btn_cover.pack(side="left", padx=5)
        
        self.lbl_cover_status = tk.Label(self.f_new_series, text="(Sin portada)", fg="gray", font=("Arial", 8))
        self.lbl_cover_status.pack(side="left")

        tk.Entry(self.f_edit, textvariable=self.var_final_name, state="readonly", bg="#eee").pack(fill="x", pady=5)

        # Flags y Botones
        f_act = tk.Frame(self.f_edit)
        f_act.pack(fill="x")
        tk.Checkbutton(f_act, text="OK.ru", variable=self.chk_ind_ok).pack(side="left")
        tk.Checkbutton(f_act, text="Telegram", variable=self.chk_ind_tg).pack(side="left")
        tk.Checkbutton(f_act, text="No YT", variable=self.chk_ind_yt, fg="red").pack(side="left")

        tk.Label(f_act, text="|", fg="#ccc").pack(side="left", padx=5)
        tk.Checkbutton(f_act, text="Guardar en DB", variable=self.chk_save_db, fg="#00695C").pack(side="left")
        
        self.btn_cancel_edit = tk.Button(f_act, text="Cancelar", command=self.cancel_edit, state="disabled")
        self.btn_cancel_edit.pack(side="right")
        self.btn_update = tk.Button(f_act, text="💾 Actualizar", command=self.update_segment, bg="#FF9800", fg="white", state="disabled")
        self.btn_update.pack(side="right", padx=5)
        self.btn_add = tk.Button(f_act, text="➕ Agregar", command=self.add_segment, bg="#4CAF50", fg="white", state="disabled")
        self.btn_add.pack(side="right", padx=5)

        # 3. Lista
        f_list = tk.LabelFrame(self.root, text="3. Cola", padx=10, pady=5)
        f_list.pack(fill="both", expand=True, padx=10, pady=5)
        
        cols = ("id", "name", "dur", "type", "ok", "tg", "yt")
        self.tree = ttk.Treeview(f_list, columns=cols, show="headings", height=5)
        self.tree.heading("name", text="Nombre"); self.tree.column("name", width=300)
        self.tree.heading("dur", text="Dur"); self.tree.column("dur", width=60)
        self.tree.heading("type", text="Tipo"); self.tree.column("type", width=80)
        self.tree.heading("ok", text="OK"); self.tree.column("ok", width=30)
        self.tree.heading("tg", text="TG"); self.tree.column("tg", width=30)
        self.tree.heading("yt", text="NoYT"); self.tree.column("yt", width=40)
        self.tree.column("id", width=0, stretch=False)
        
        sb = ttk.Scrollbar(f_list, command=self.tree.yview); self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select_segment)
        tk.Button(f_list, text="Borrar Seleccionado", command=self.delete_segment).pack(side="bottom")

        # 4. Ejecución
        f_run = tk.LabelFrame(self.root, text="4. Ejecución", padx=10, pady=5, bg="#f1f8e9")
        f_run.pack(fill="x", padx=10, pady=5)
        
        f_r_opts = tk.Frame(f_run, bg="#f1f8e9")
        f_r_opts.pack(fill="x")
        tk.Checkbutton(f_r_opts, text="Preciso", variable=self.var_precise_mode, bg="#f1f8e9").pack(side="left")
        tk.Checkbutton(f_r_opts, text="GPU", variable=self.var_hw_accel, bg="#f1f8e9").pack(side="left")
        self.cb_qual = ttk.Combobox(f_r_opts, values=["Rápida (720p)", "Media (1080p)", "Alta"], state="readonly", width=10)
        self.cb_qual.current(0); self.cb_qual.pack(side="left", padx=5)
        
        tk.Label(f_r_opts, text="|", bg="#f1f8e9").pack(side="left", padx=10)
        tk.Checkbutton(f_r_opts, text="Gen YT", variable=self.var_gen_youtube, bg="#f1f8e9").pack(side="left")
        tk.Checkbutton(f_r_opts, text="AUTO-SUBIR", variable=self.var_auto_upload, bg="#f1f8e9", fg="blue").pack(side="left")
        tk.Checkbutton(f_r_opts, text="Cerrar Chrome", variable=self.var_close_chrome, bg="#f1f8e9").pack(side="left")

        # BOTONES DE CONTROL
        self.btn_run = tk.Button(f_r_opts, text="EJECUTAR TODO", command=self.start_process, bg="#2196F3", fg="white", font=("Arial", 10, "bold"), state="disabled")
        self.btn_run.pack(side="right", padx=5)
        
        self.btn_stop = tk.Button(f_r_opts, text="⛔ DETENER", command=self.stop_process, bg="#B71C1C", fg="white", font=("Arial", 10, "bold"), state="disabled")
        self.btn_stop.pack(side="right", padx=5)

        # 5. Logs
        f_log = tk.LabelFrame(self.root, text="Consola", padx=5)
        f_log.pack(fill="both", expand=True, padx=10, pady=5)
        self.prog_tg = ttk.Progressbar(f_log, orient="horizontal", mode="determinate")
        self.prog_tg.pack(fill="x")
        self.log_area = scrolledtext.ScrolledText(f_log, height=8, state='disabled', bg="#222", fg="#eee", font=("Consolas", 9))
        self.log_area.pack(fill="both", expand=True)

    # --- Lógica Log ---
    def process_log_queue(self):
        while not self.log_queue.empty():
            try:
                r = self.log_queue.get_nowait()
                msg = f"{r.asctime} - {r.message}" if isinstance(r, logging.LogRecord) else str(r)
                self.log_area.configure(state='normal')
                self.log_area.insert(tk.END, msg + '\n')
                self.log_area.see(tk.END)
                self.log_area.configure(state='disabled')
            except queue.Empty: pass
        self.root.after(100, self.process_log_queue)

    # --- Eventos Carga/UI ---
    def load_video(self):
        fn = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mkv *.ts *.flv")])
        if not fn: return
        info = self.core.load_video(fn)
        self.lbl_info.config(text=info['filename'])
        self.lbl_tech.config(text=f"Dur: {self.core.sec_to_hms(info['duration'])}")
        
        self.s_start.config(to=info['duration']); self.s_end.config(to=info['duration'])
        
        p = self.core.parse_filename_smart(fn)
        self.var_n_streamer.set(p['streamer'])
        self.var_n_date.set(p['date_str'])
        
        # Usamos la API externa del SessionFrame
        self.session_frame.set_streamer(p['streamer'])
        self.session_frame.set_date(p['date_str'])
        
        self.refresh_list()
        self.btn_run.config(state="normal")
        self.btn_add.config(state="normal")

    def on_series_selected(self, e):
        info = self.core.get_last_series_info(self.var_n_content.get())
        self.var_n_season.set(info.get('season', ''))
        self.var_n_episode.set(info.get('episode', ''))
        self.var_material_type.set(info.get('material_type', TIPOS_MATERIAL[0]))


    def update_name_preview(self, *args):
        s = self.var_n_season.get().strip(); e = self.var_n_episode.get().strip()
        fs = f"S{s}" if s and not s.lower().startswith('s') else s
        fe = f"Cap {e}" if e and not e.lower().startswith('cap') else e
        parts = [self.var_n_streamer.get(), self.var_n_date.get(), self.var_n_content.get(), fs, fe]
        self.var_final_name.set(" ".join([p.strip() for p in parts if p]).upper())

    def on_content_change(self, *args):
        self.update_name_preview()
        name = self.var_n_content.get().strip()
        if not name: 
            self._hide_new_series_panel()
            return
            
        info = self.metadata_mgr.get_series_info(name)
        if info:
            # Existe
            self.is_new_series = False
            self._hide_new_series_panel()
        else:
            # No existe -> Es nueva
            self.is_new_series = True
            self._show_new_series_panel()

    def _show_new_series_panel(self):
        try:
            # [0]=f_t, [1]=f_name, [2]=self.f_new_series. We want to pack after [1]
            target = self.f_edit.winfo_children()[1] 
            self.f_new_series.pack(fill="x", pady=5, after=target)
        except Exception as e:
            print(f"Error showing panel: {e}")
    
    def _hide_new_series_panel(self):
        self.f_new_series.pack_forget()


    def upload_cover(self):
        # Ahora solo seleccionamos el archivo local. El procesamiento real ocurre al guardar la serie.
        fn = filedialog.askopenfilename(title="Seleccionar Portada", filetypes=[("Imágenes", "*.jpg *.png *.webp")])
        if not fn: return
        
        self.var_new_cover_url.set(fn)
        self.lbl_cover_status.config(text=f"📂 {os.path.basename(fn)}", fg="blue")

    # --- CRUD ---
    def add_segment(self):
        try:
            s = self.core.hms_to_sec(self.var_start.get())
            e = self.core.hms_to_sec(self.var_end.get())
            opts = {'ok':self.chk_ind_ok.get(), 'tg':self.chk_ind_tg.get(), 'yt_cut':self.chk_ind_yt.get(), 'save_db':self.chk_save_db.get()}
            meta = {'show':self.var_n_content.get(), 'season':self.var_n_season.get(), 'ep':self.var_n_episode.get(), 'type':self.var_material_type.get()}
            
            # Metadata de Serie Nueva
            if self.is_new_series:
                show_name = self.var_n_content.get().strip().upper()
                
                # Procesar portada si se seleccionó una
                raw_cover = self.var_new_cover_url.get()
                final_cover_url = ""
                
                if raw_cover:
                    print(f"Procesando portada para {show_name}...")
                    web_path, _ = process_cover(raw_cover, show_name, config=self.config)
                    final_cover_url = web_path
                
                new_data = {
                    'description': self.var_new_desc.get(),
                    'cover_url': final_cover_url,
                    'provider': 'Manual',
                    'material_type': self.var_material_type.get(),
                    'seasons': {}
                }
                
                # Guardar en JSON de Metadatos
                if self.metadata_mgr.update_show_data(show_name, new_data):
                    print(f"✅ Nueva serie guardada: {show_name}")
                    self.is_new_series = False
                    self._hide_new_series_panel()
                else:
                    messagebox.showerror("Error", "No se pudo guardar la metadata de la nueva serie.")
            
            # Update history if OKru is checked
            if meta['show'] and opts['ok']:
                self.core.update_series_info_db(meta['show'], meta['season'], meta['ep'], meta['type'])
                if meta['show'] not in self.series_list:
                    self.series_list = self.core.get_series_history()
                    self.combo_content['values'] = self.series_list
            
            self.core.add_segment(s, e, self.var_final_name.get(), opts, meta)
            self.refresh_list()
            
            # Avanzar
            self.s_start.set(e); self.on_slider_start(e)
            self.s_end.set(min(e+600, self.core.duration_sec)); self.on_slider_end(self.s_end.get())
            self.cancel_edit()
        except Exception as e: messagebox.showwarning("Error", str(e))

    def update_segment(self):
        if not self.editing_id: return
        s = self.core.hms_to_sec(self.var_start.get())
        e = self.core.hms_to_sec(self.var_end.get())
        opts = {'ok':self.chk_ind_ok.get(), 'tg':self.chk_ind_tg.get(), 'yt_cut':self.chk_ind_yt.get()}
        meta = {'type':self.var_material_type.get()}
        self.core.update_segment(self.editing_id, s, e, self.var_final_name.get(), opts, meta)
        self.refresh_list()
        self.cancel_edit()

    def delete_segment(self):
        ids = [self.tree.item(i)['values'][0] for i in self.tree.selection()]
        self.core.delete_segments_by_id(ids)
        self.refresh_list()
        self.cancel_edit()

    def on_select_segment(self, e):
        sel = self.tree.selection()
        if not sel: return
        sid = self.tree.item(sel[0])['values'][0]
        seg = self.core.get_segment_by_id(sid)
        if seg:
            self.editing_id = sid
            self.s_start.set(seg['start']); self.on_slider_start(seg['start'])
            self.s_end.set(seg['end']); self.on_slider_end(seg['end'])
            self.var_n_content.set(seg.get('meta_show',''))
            self.var_n_season.set(seg.get('meta_season',''))
            self.var_n_episode.set(seg.get('meta_ep',''))
            self.var_material_type.set(seg.get('meta_type',''))
            if not seg.get('meta_show'): self.var_n_content.set(seg['name'])
            self.chk_ind_ok.set(seg['dest_ok'])
            self.chk_ind_tg.set(seg['dest_tg'])
            self.chk_ind_yt.set(seg['yt_cut'])
            self.chk_save_db.set(seg.get('save_db', True))
            self.btn_add.config(state="disabled")
            self.btn_update.config(state="normal")
            self.btn_cancel_edit.config(state="normal")

    def cancel_edit(self):
        self.editing_id = None
        self.btn_add.config(state="normal"); self.btn_update.config(state="disabled"); self.btn_cancel_edit.config(state="disabled")
        self.var_n_content.set("")

    def refresh_list(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        for s in self.core.segments:
            self.tree.insert("", "end", values=(s['id'], s['name'], self.core.sec_to_hms(s['end']-s['start']), s.get('meta_type',''), 
                                              "✅" if s['dest_ok'] else "⛔", "✅" if s['dest_tg'] else "⛔", "✂️" if s['yt_cut'] else "👁️"))

    # --- Utils ---
    def on_slider_start(self, v): self.var_start.set(self.core.sec_to_hms(float(v)))
    def on_slider_end(self, v): self.var_end.set(self.core.sec_to_hms(float(v)))
    def on_entry_change(self, e=None):
        try: self.s_start.set(self.core.hms_to_sec(self.var_start.get())); self.s_end.set(self.core.hms_to_sec(self.var_end.get()))
        except: pass
    def snap_to_keyframes(self):
        t = self.core.snap_to_keyframes(self.s_start.get())
        if t is not None: self.s_start.set(t); self.on_slider_start(t)
        else: messagebox.showinfo("Info", "Sin keyframes.")

    # --- PROCESAMIENTO ---
    def start_process(self):
        if not os.path.exists('config/config.json'): return messagebox.showerror("Error", "Falta config.json")
        out_dir = filedialog.askdirectory(title="Salida")
        if not out_dir: return
        
        try:
            with open('config/config.json') as f: config = json.load(f)
        except: return messagebox.showerror("Error", "Config corrupto")

        opts = {
            'precise_mode':self.var_precise_mode.get(), 'hw_accel':self.var_hw_accel.get(),
            'quality_yt':self.cb_qual.get(), 'gen_youtube':self.var_gen_youtube.get(),
            'auto_upload':self.var_auto_upload.get(), 'close_chrome':self.var_close_chrome.get(),
            'streamer_name':self.var_n_streamer.get(), 'date_str':self.var_n_date.get(),
            'allow_empty': not self.core.segments
        }

        if not self.core.segments and not messagebox.askyesno("?", "Sin cortes. ¿Procesar entero?"): return

        self.processing = True
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal") # Activar botón de Pánico

        def cb_ui(p, t): self.root.after(0, lambda: self.prog_tg.configure(value=p))

        t = threading.Thread(target=self._run_thread, args=(out_dir, config, opts, {'tg_progress': cb_ui}))
        t.start()

    def stop_process(self):
        if messagebox.askyesno("Confirmar", "¿Seguro que deseas detener el proceso? Se completarán las tareas actuales."):
            self.core.stop_processing()
            self.btn_stop.config(state="disabled", text="Deteniendo...")

    def _run_thread(self, *args):
        try:
            self.core.process_all(*args)
            self.root.after(0, lambda: messagebox.showinfo("Fin", "Proceso completado."))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.processing = False
            self.root.after(0, self._reset_buttons)

    def _reset_buttons(self):
        self.btn_run.config(state="normal")
        self.btn_stop.config(state="disabled", text="⛔ DETENER")
        self.prog_tg.configure(value=0)

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoSegmenterUI(root)
    root.mainloop()