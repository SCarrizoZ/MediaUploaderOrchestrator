import json
import os

class UploadHistory:
    """Historial centralizado para evitar subidas duplicadas"""
    def __init__(self, base_path):
        self.history_file = os.path.join(base_path, "upload_history.json")
        self.load()
    
    def load(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except:
                self.data = {}
        else:
            self.data = {}
    
    def save(self):
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
    
    def is_uploaded(self, filename, destination):
        """
        destination: 'okru', 'telegram', 'youtube'
        Retorna True si ya fue subido
        """
        key = f"{filename}_{destination}"
        return self.data.get(key, False)
    
    def mark_uploaded(self, filename, destination, success=True):
        """Marca como subido (o fallido si success=False)"""
        key = f"{filename}_{destination}"
        self.data[key] = success
        self.save()