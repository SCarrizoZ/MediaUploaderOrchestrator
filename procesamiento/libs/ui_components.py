import tkinter as tk
from tkinter import ttk
from tkcalendar import DateEntry
from libs.utils import format_spanish_date

class StreamerDateSessionFrame(ttk.Frame):
    """
    Componente reutilizable que agrupa el ComboBox de Streamer 
    y el DateEntry de Fecha, junto con sus respectivos eventos de auto-formateo.
    """
    def __init__(self, parent, core_instance, var_streamer=None, var_date=None, **kwargs):
        # Extraer opciones visuales personalizadas ANTES de llamar al init del padre
        self.streamer_width = kwargs.pop('streamer_width', 23)
        self.date_width = kwargs.pop('date_width', 23)
        self.layout = kwargs.pop('layout', 'horizontal')
        self.label_font = kwargs.pop('label_font', None)
        
        super().__init__(parent, **kwargs)
        
        self.core = core_instance
        
        # Variables persistentes (Si el padre no pasa unas, creamos nuevas)
        self.var_streamer = var_streamer if var_streamer is not None else tk.StringVar()
        self.var_date = var_date if var_date is not None else tk.StringVar()
        
        self._build_ui()

    def _build_ui(self):
        # Labels configurables
        if self.label_font:
            lbl_streamer = tk.Label(self, text="Streamer", font=self.label_font)
            lbl_date = tk.Label(self, text="Fecha", font=self.label_font)
        else:
            lbl_streamer = ttk.Label(self, text="Streamer:")
            lbl_date = ttk.Label(self, text="Fecha:")
        
        # Intentamos obtener historial (soporta tanto get_streamer_history directo como en pm)
        history = []
        if hasattr(self.core, 'get_streamer_history'):
            history = self.core.get_streamer_history()
        
        self.combo_streamer = ttk.Combobox(self, textvariable=self.var_streamer, values=history, width=self.streamer_width)
        self.combo_streamer.bind("<FocusOut>", self._on_streamer_focus_out)
        self.combo_streamer.bind("<<ComboboxSelected>>", self._on_streamer_focus_out)

        self.cal_date = DateEntry(self, width=self.date_width, background='darkblue',
                                  foreground='white', borderwidth=2, locale='es_ES',
                                  date_pattern='dd/MM/yyyy')
        self.cal_date.bind("<<DateEntrySelected>>", self._on_date_selected)
        self.cal_date.bind("<FocusOut>", self._on_date_focus_out)

        # Ubicación en grilla interna según layout solicitado
        if self.layout == 'vertical':
            lbl_streamer.grid(row=0, column=0, padx=2, sticky="w")
            self.combo_streamer.grid(row=1, column=0, padx=2)
            lbl_date.grid(row=0, column=1, padx=2, sticky="w")
            self.cal_date.grid(row=1, column=1, padx=2)
        else:
            lbl_streamer.grid(row=0, column=0, padx=5, sticky="w")
            self.combo_streamer.grid(row=0, column=1, padx=5)
            lbl_date.grid(row=0, column=2, padx=5, sticky="w")
            self.cal_date.grid(row=0, column=3, padx=5)

    # --- Lógica de Formateo de Texto ---

    def _on_streamer_focus_out(self, event=None):
        val = self.var_streamer.get()
        if val:
            self.var_streamer.set(val.strip().upper())

    def _on_date_selected(self, event=None):
        date_obj = self.cal_date.get_date()
        formatted = format_spanish_date(date_obj)
        self.var_date.set(formatted)
        
        # Limpiamos y re-insertamos en el calendario visual
        self.cal_date.delete(0, "end")
        self.cal_date.insert(0, formatted)

    def _on_date_focus_out(self, event=None):
        val = self.cal_date.get()
        if val:
            try:
                date_obj = self.cal_date.get_date()
                formatted = format_spanish_date(date_obj)
                self.var_date.set(formatted)
            except Exception:
                # Si el usuario ingresó un modelo como "15 MARZO 2026", get_date podría fallar, guardamos las mayúsculas:
                self.var_date.set(val.strip().upper())
            
            # Sincronizamos la parte visual si es un texto escrito a mano legal
            self.cal_date.delete(0, "end")
            self.cal_date.insert(0, self.var_date.get())
            
    # API Externa para actualización manual 
    def set_streamer(self, name):
        self.var_streamer.set(name.upper() if name else "")
        
    def set_date(self, date_string):
        self.var_date.set(date_string if date_string else "")
        self.cal_date.delete(0, "end")
        self.cal_date.insert(0, self.var_date.get())
