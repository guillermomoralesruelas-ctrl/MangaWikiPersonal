import os
import json

def load_json(filepath, default_value=None):
    if default_value is None:
        default_value = {}
    if not os.path.exists(filepath):
        return default_value
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default_value

def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

class ProjectJSONManager:
    def __init__(self, project_path):
        self.project_path = project_path
        self.json_dir = os.path.join(project_path, "Datos_JSON")
        
    def get_path(self, filename):
        return os.path.join(self.json_dir, filename)
        
    def load_project_meta(self):
        return load_json(self.get_path("proyecto.json"))
        
    def save_project_meta(self, data):
        save_json(self.get_path("proyecto.json"), data)
        
    def load_pages(self):
        return load_json(self.get_path("paginas.json"))
        
    def save_pages(self, data):
        save_json(self.get_path("paginas.json"), data)
        
    def load_characters(self):
        return load_json(self.get_path("personajes.json"), default_value=[])
        
    def save_characters(self, data):
        save_json(self.get_path("personajes.json"), data)
        
    def load_events(self):
        return load_json(self.get_path("eventos.json"), default_value=[])
        
    def save_events(self, data):
        save_json(self.get_path("eventos.json"), data)
        
    def load_places(self):
        return load_json(self.get_path("lugares.json"), default_value=[])
        
    def save_places(self, data):
        save_json(self.get_path("lugares.json"), data)
        
    def load_objects(self):
        return load_json(self.get_path("objetos.json"), default_value=[])
        
    def save_objects(self, data):
        save_json(self.get_path("objetos.json"), data)

    def load_organizations(self):
        return load_json(self.get_path("organizaciones.json"), default_value=[])
        
    def save_organizations(self, data):
        save_json(self.get_path("organizaciones.json"), data)

    def load_relations(self):
        return load_json(self.get_path("relaciones.json"), default_value=[])
        
    def save_relations(self, data):
        save_json(self.get_path("relaciones.json"), data)

    def load_timeline(self):
        return load_json(self.get_path("timeline.json"), default_value=[])
        
    def save_timeline(self, data):
        save_json(self.get_path("timeline.json"), data)
