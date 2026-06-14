import os
import datetime
from .pdf_processor import process_pdf
from .json_manager import ProjectJSONManager
from .markdown_generator import (
    generate_page_markdown,
    generate_index_markdown,
    clean_filename
)

class ProjectManager:
    def __init__(self, base_projects_dir):
        self.base_projects_dir = base_projects_dir
        os.makedirs(base_projects_dir, exist_ok=True)
        
    def list_projects(self):
        """
        Lists all project names that have a proyecto.json file.
        """
        projects = []
        if not os.path.exists(self.base_projects_dir):
            return projects
            
        for folder in os.listdir(self.base_projects_dir):
            folder_path = os.path.join(self.base_projects_dir, folder)
            if os.path.isdir(folder_path):
                meta_file = os.path.join(folder_path, "Datos_JSON", "proyecto.json")
                if os.path.exists(meta_file):
                    # Run auto-migration to the new Biblioteca structure
                    self.migrate_project(folder_path)
                    
                    # Run auto-migration to the new ID-based layer (entities.json)
                    from .entity_manager import EntityManager
                    EntityManager(folder_path).run_auto_migration()
                    
                    from .json_manager import load_json
                    meta = load_json(meta_file)
                    if meta:
                        projects.append({
                            "id": folder,
                            "name": meta.get("name", folder),
                            "path": folder_path,
                            "total_pages": meta.get("total_pages", 0),
                            "created_at": meta.get("created_at", "")
                        })
        return projects

    def migrate_project(self, project_path):
        import shutil
        bib_dir = os.path.join(project_path, "Biblioteca")
        os.makedirs(bib_dir, exist_ok=True)
        
        # Ensure new directories exist under Biblioteca/
        new_folders = ["Personajes", "Eventos", "Lugares", "Objetos", "Organizaciones", "Relaciones", "Timeline"]
        for f in new_folders:
            os.makedirs(os.path.join(bib_dir, f), exist_ok=True)
            
        # Move old root folders to Biblioteca
        old_folders = ["Personajes", "Eventos", "Lugares", "Objetos"]
        for folder in old_folders:
            old_path = os.path.join(project_path, folder)
            if os.path.exists(old_path) and os.path.isdir(old_path):
                for file in os.listdir(old_path):
                    src = os.path.join(old_path, file)
                    dst = os.path.join(bib_dir, folder, file)
                    if os.path.exists(dst):
                        if os.path.isdir(src):
                            shutil.rmtree(dst)
                        else:
                            os.remove(dst)
                    shutil.move(src, dst)
                try:
                    os.rmdir(old_path)
                except Exception:
                    pass
                    
        # Migrate any .md files from Assets subfolders to Biblioteca subfolders
        assets_dir = os.path.join(project_path, "Assets")
        if os.path.exists(assets_dir) and os.path.isdir(assets_dir):
            for sub in os.listdir(assets_dir):
                sub_path = os.path.join(assets_dir, sub)
                if os.path.isdir(sub_path):
                    for file in os.listdir(sub_path):
                        if file.endswith(".md"):
                            src = os.path.join(sub_path, file)
                            # Match target Biblioteca directory
                            dst_dir = os.path.join(bib_dir, sub)
                            if not os.path.exists(dst_dir):
                                dst_dir = os.path.join(bib_dir, "Personajes") # default fallback
                            os.makedirs(dst_dir, exist_ok=True)
                            dst = os.path.join(dst_dir, file)
                            if os.path.exists(dst):
                                os.remove(dst)
                            shutil.move(src, dst)

    def create_project(self, project_name, pdf_path):
        """
        Creates a new project structure, processes the PDF, and initializes metadata.
        """
        # Format a clean folder name for the project
        folder_name = clean_filename(project_name)
        project_path = os.path.join(self.base_projects_dir, folder_name)
        
        # If folder already exists, raise FileExistsError to prevent silent duplicates
        if os.path.exists(project_path):
            raise FileExistsError(f"Ya existe un proyecto con el nombre '{project_name}'.")

        # 1. Create directory structure
        dirs = [
            "00_Index",
            "Capitulos",
            "Paginas",
            "Imagenes",
            "Datos_JSON",
            "PDF_Original",
            "Assets",
            "Biblioteca",
            "Biblioteca/Personajes",
            "Biblioteca/Eventos",
            "Biblioteca/Lugares",
            "Biblioteca/Objetos",
            "Biblioteca/Organizaciones",
            "Biblioteca/Relaciones",
            "Biblioteca/Timeline"
        ]
        for d in dirs:
            os.makedirs(os.path.join(project_path, d), exist_ok=True)
            
        # Create Assets subdirectories
        from .asset_extractor import TYPE_MAP
        for folder in TYPE_MAP.values():
            os.makedirs(os.path.join(project_path, "Assets", folder), exist_ok=True)
            
        # 2. Process PDF
        images_dir = os.path.join(project_path, "Imagenes")
        pdf_dir = os.path.join(project_path, "PDF_Original")
        total_pages = process_pdf(pdf_path, images_dir, pdf_dir)
        
        # 3. Create JSON Manager
        json_mgr = ProjectJSONManager(project_path)
        
        # 4. Save metadata
        meta = {
            "id": folder_name,
            "name": project_name,
            "pdf_name": os.path.basename(pdf_path),
            "total_pages": total_pages,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        json_mgr.save_project_meta(meta)
        
        # 5. Initialize pages.json and create baseline page markdown files
        pages_data = {}
        for i in range(1, total_pages + 1):
            page_str = f"{i:03d}"
            page_info = {
                "num_pagina": page_str,
                "texto": "",
                "narracion": "",
                "personajes": [],
                "descripcion_visual": "",
                "eventos": [],
                "lugares": [],
                "objetos": [],
                "curiosidades": [],
                "relaciones": [],
                "notas": "",
                "etiquetas": ["#pagina", "#manga", "#pendiente"]
            }
            pages_data[page_str] = page_info
            
            # Generate markdown note for page
            generate_page_markdown(project_path, page_info)
            
        json_mgr.save_pages(pages_data)
        
        # 6. Initialize entity JSON files
        json_mgr.save_characters([])
        json_mgr.save_events([])
        json_mgr.save_places([])
        json_mgr.save_objects([])
        
        # Save default example detections file
        example_detections = [
            {
                "pagina": 1,
                "elementos": [
                    {
                        "id": "p001_obj_001",
                        "tipo": "personaje",
                        "nombre": "Gold Roger",
                        "descripcion": "El legendario Rey de los Piratas, Gold Roger, sonriendo en el patíbulo antes de su ejecución.",
                        "bbox": {
                            "x": 100,
                            "y": 100,
                            "ancho": 400,
                            "alto": 500
                        },
                        "tags": ["personaje", "gold_roger", "rey_de_los_piratas"]
                    },
                    {
                        "id": "p001_obj_002",
                        "tipo": "objeto",
                        "nombre": "Espadas de Ejecucion",
                        "descripcion": "Las dos espadas cruzadas que custodian el cuello de Gold Roger en la plataforma de ejecución.",
                        "bbox_normalizado": {
                            "x": 0.1,
                            "y": 0.35,
                            "ancho": 0.35,
                            "alto": 0.15
                        },
                        "tags": ["objeto", "ejecucion", "espadas"]
                    },
                    {
                        "id": "p001_obj_003",
                        "tipo": "escena",
                        "nombre": "La Ejecucion de Gold Roger",
                        "descripcion": "Gran plano general de la plaza de Loguetown atestada de personas presenciando la ejecución del Rey de los Piratas.",
                        "bbox": {
                            "x": 50,
                            "y": 50,
                            "ancho": 700,
                            "alto": 1000
                        },
                        "tags": ["escena", "loguetown", "ejecucion"]
                    }
                ]
            }
        ]
        from .json_manager import save_json
        save_json(os.path.join(project_path, "Datos_JSON", "detecciones_ejemplo.json"), example_detections)
        
        # 7. Generate main Index.md
        generate_index_markdown(
            project_path,
            project_name,
            total_pages,
            characters=[],
            events=[],
            places=[],
            objects=[]
        )
        
        return folder_name
