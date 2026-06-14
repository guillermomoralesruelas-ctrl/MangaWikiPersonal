import os
import sys
import shutil
import json

def run_test():
    print("=== INICIANDO PRUEBA DE MANGAWIKI PERSONAL ===")
    
    # 1. Check dependencies
    try:
        import fitz
        import flask
        import PIL
        print("[OK] Dependencias principales (pymupdf, flask, pillow) están instaladas.")
    except ImportError as e:
        print(f"[ERROR] Falta alguna dependencia: {str(e)}")
        print("Por favor ejecuta: pip install -r requirements.txt")
        sys.exit(1)

    # 2. Check source PDF
    source_pdf = "OP-Tomo a color 01.pdf"
    if not os.path.exists(source_pdf):
        print(f"[ERROR] No se encontró el PDF de prueba '{source_pdf}' en la raíz del proyecto.")
        sys.exit(1)
    print(f"[OK] Archivo PDF origen encontrado: {source_pdf}")

    # 3. Import local services
    try:
        from services.project_manager import ProjectManager
        from services.json_manager import ProjectJSONManager
    except Exception as e:
        print(f"[ERROR] Error al importar los módulos de servicio: {str(e)}")
        sys.exit(1)

    # 4. Perform lightweight project creation (just test processing the first 2 pages)
    print("\n--- Probando creación de estructura y procesamiento ligero (2 primeras páginas) ---")
    test_projects_dir = os.path.abspath("./MangaWikiPersonal/Proyectos")
    manager = ProjectManager(test_projects_dir)
    test_project_id = "test_one_piece"
    test_project_path = os.path.join(test_projects_dir, test_project_id)
    
    # Clean previous test if exists
    if os.path.exists(test_project_path):
        shutil.rmtree(test_project_path)
        
    try:
        # Create directories manually for the mock run
        dirs = ["00_Index", "Capitulos", "Paginas", "Personajes", "Eventos", "Lugares", "Objetos", "Curiosidades", "Imagenes", "Datos_JSON", "PDF_Original"]
        for d in dirs:
            os.makedirs(os.path.join(test_project_path, d), exist_ok=True)
            
        # Extract only first 2 pages for testing
        print("Extractores: Leyendo PDF de prueba...")
        doc = fitz.open(source_pdf)
        num_pages = min(2, len(doc))
        print(f"Procesando {num_pages} páginas de prueba...")
        
        # Save images
        for i in range(num_pages):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            image_path = os.path.join(test_project_path, "Imagenes", f"pagina_{i+1:03d}.png")
            pix.save(image_path)
            print(f" -> Página {i+1} guardada en Imagenes/")
        
        # Save original PDF copy
        shutil.copy2(source_pdf, os.path.join(test_project_path, "PDF_Original", source_pdf))
        doc.close()
        
        # Initialize JSON and Markdown notes
        json_mgr = ProjectJSONManager(test_project_path)
        
        # Save dummy pages.json
        pages_data = {}
        from services.markdown_generator import generate_page_markdown, generate_index_markdown
        for i in range(1, num_pages + 1):
            page_str = f"{i:03d}"
            page_info = {
                "num_pagina": page_str,
                "texto": "Texto de prueba.",
                "narracion": "Una escena de prueba.",
                "personajes": ["Monkey D. Luffy"] if i == 1 else ["Roronoa Zoro"],
                "descripcion_visual": "Detalles visuales.",
                "eventos": ["Inicio de la prueba"],
                "lugares": ["Mar del Este"],
                "objetos": ["Sombrero de Paja"],
                "curiosidades": [],
                "relaciones": [],
                "notas": "",
                "etiquetas": ["#test", "#manga"]
            }
            pages_data[page_str] = page_info
            generate_page_markdown(test_project_path, page_info)
            
        json_mgr.save_pages(pages_data)
        json_mgr.save_characters(["Monkey D. Luffy", "Roronoa Zoro"])
        json_mgr.save_events(["Inicio de la prueba"])
        json_mgr.save_places(["Mar del Este"])
        json_mgr.save_objects(["Sombrero de Paja"])
        
        # Generate indexes
        generate_index_markdown(test_project_path, "One Piece Prueba", num_pages, 
                                ["Monkey D. Luffy", "Roronoa Zoro"], ["Inicio de la prueba"], ["Mar del Este"], ["Sombrero de Paja"])
        
        # Create character files
        from services.markdown_generator import generate_character_markdown
        generate_character_markdown(test_project_path, "Monkey D. Luffy", ["001"])
        generate_character_markdown(test_project_path, "Roronoa Zoro", ["002"])

        # Dummy detections for testing
        example_detections = [
            {
                "pagina": 1,
                "elementos": [
                    {
                        "id": "p001_obj_001",
                        "tipo": "personaje",
                        "nombre": "Gold Roger",
                        "descripcion": "El legendario Rey de los Piratas.",
                        "bbox": {
                            "x": 100,
                            "y": 100,
                            "ancho": 200,
                            "alto": 200
                        },
                        "tags": ["personaje", "gold_roger"]
                    }
                ]
            }
        ]
        with open(os.path.join(test_project_path, "Datos_JSON", "detecciones_ejemplo.json"), 'w', encoding='utf-8') as f:
            json.dump(example_detections, f, ensure_ascii=False, indent=4)

        # Test Asset Extractor
        print("\n--- Probando extracción de assets visuales ---")
        from services.asset_extractor import process_detections
        # Load example detections json we wrote earlier
        example_json_path = os.path.join(test_project_path, "Datos_JSON", "detecciones_ejemplo.json")
        with open(example_json_path, 'r', encoding='utf-8') as f:
            detections_data = json.load(f)
        
        # Run extraction
        result = process_detections(test_project_path, detections_data)
        print(f" -> Recortes procesados: {result['processed']}, omitidos: {result['skipped']}")
        if result['warnings']:
            print(f" -> Advertencias de test: {result['warnings']}")

        # Test Entity Manager - Master Entity System (IDs Layer) & Resolution Center
        print("\n--- Probando Resolution Center (Alias, Merge, Redirect, Rollback, Historial) ---")
        from services.entity_manager import EntityManager
        em = EntityManager(test_project_path)
        em.run_auto_migration()
        
        # Test Alias Add
        luffy_id = em.resolve_to_id("Monkey D. Luffy")
        if not luffy_id:
            raise ValueError("No se pudo encontrar a Monkey D. Luffy por nombre.")
            
        success, msg = em.add_alias(luffy_id, "Mugiwara")
        print(f" -> Agregar alias 'Mugiwara' a Luffy ({luffy_id}): {success} ({msg})")
        if not success:
            raise ValueError(f"Error al agregar alias: {msg}")
            
        # Test Alias Duplicated Validation
        success, msg = em.add_alias(luffy_id, "Mugiwara")
        print(f" -> Intentar duplicar alias 'Mugiwara': {success} ({msg})")
        if success:
            raise ValueError("Se permitió registrar un alias duplicado erróneamente.")
            
        # Test Merge & Soft Delete
        new_ent, _ = em.get_or_create_entity("Luffy", "personaje")
        luffy_dup_id = new_ent["id"]
        print(f" -> Creada entidad duplicada 'Luffy' con ID: {luffy_dup_id}")
        
        # Merge Luffy (luffy_dup_id) into Monkey D. Luffy (luffy_id)
        success, msg = em.merge_entities(luffy_id, luffy_dup_id, "Test Fusión")
        print(f" -> Fusionando {luffy_dup_id} en {luffy_id}: {success} ({msg})")
        if not success:
            raise ValueError(f"Error al fusionar entidades: {msg}")
            
        # Verify Soft Delete & Redirect
        entities = em.load_entities()
        sec_ent = next(x for x in entities if x["id"] == luffy_dup_id)
        print(f" -> Estado de entidad fusionada: {sec_ent.get('estado')} (merged_into: {sec_ent.get('merged_into')})")
        if sec_ent.get("estado") != "merged" or sec_ent.get("merged_into") != luffy_id:
            raise ValueError("Fusión no aplicó soft delete correctamente.")
            
        # Resolve redirect
        resolved = em.resolve_to_id("Luffy")
        print(f" -> Resolución de nombre duplicado 'Luffy' apunta a ID: {resolved}")
        if resolved != luffy_id:
            raise ValueError(f"Resolución de redirección falló: se esperaba {luffy_id}, se obtuvo {resolved}")
            
        # Verify History log was recorded
        history = em.load_history()
        actions = [h["accion"] for h in history if h["entity_id"] == luffy_id]
        print(f" -> Historial de Luffy: {actions}")
        if "alias_added" not in actions or "merged_absorb" not in actions:
            raise ValueError("Historial de cambios incompleto.")
            
        # Test Restoration / Rollback
        success, msg = em.restore_entity(luffy_dup_id)
        print(f" -> Restaurando {luffy_dup_id} (Rollback): {success} ({msg})")
        if not success:
            raise ValueError(f"Error al restaurar entidad: {msg}")
            
        entities = em.load_entities()
        sec_ent = next(x for x in entities if x["id"] == luffy_dup_id)
        print(f" -> Estado restaurado de entidad duplicada: {sec_ent.get('estado')}")
        if sec_ent.get("estado") != "activo" or "merged_into" in sec_ent:
            raise ValueError("Restauración falló en actualizar estado.")
            
        resolved_after_restore = em.resolve_to_id("Luffy")
        print(f" -> Resolución de 'Luffy' tras restauración apunta a: {resolved_after_restore}")
        if resolved_after_restore != luffy_dup_id:
            raise ValueError("Resolución de redirecciones no se limpió correctamente tras restauración.")

        # Test Knowledge Analysis Engine
        print("\n--- Probando Knowledge Analysis Engine ---")
        from services.analysis_engine import AnalysisEngine
        ae = AnalysisEngine(test_project_path)
        report_data = ae.run_full_analysis()
        
        print(f" -> Knowledge Score calculado: {report_data['knowledge_score']}%")
        print(f" -> Cobertura de páginas %: {report_data['coverage_pct']}%")
        print(f" -> Total entidades críticas: {report_data['critical_entities_count']}")
        print(f" -> Relaciones sugeridas: {report_data['suggested_relations_count']}")
        print(f" -> Acciones recomendadas: {len(report_data['top_recommendations'])}")
        
        # Basic assertions
        assert "knowledge_score" in report_data, "Falta 'knowledge_score' en el reporte."
        assert "coverage_pct" in report_data, "Falta 'coverage_pct' en el reporte."
        assert "top_recommendations" in report_data, "Falta 'top_recommendations' en el reporte."
        assert len(report_data["top_recommendations"]) <= 10, "Se generaron más de 10 recomendaciones."
        
        # Test exports (primary & versioned)
        export_paths = ae.export_reports()
        print(" -> Reportes exportados exitosamente:")
        print(f"    - JSON Primario: {export_paths['json_path']}")
        print(f"    - MD Primario: {export_paths['md_path']}")
        print(f"    - JSON Versionado: {export_paths['versioned_json_path']}")
        print(f"    - MD Versionado: {export_paths['versioned_md_path']}")
        
        assert os.path.exists(export_paths["json_path"]), "No se exportó el reporte JSON principal."
        assert os.path.exists(export_paths["md_path"]), "No se exportó el reporte MD principal."
        assert os.path.exists(export_paths["versioned_json_path"]), "No se exportó el reporte JSON versionado."
        assert os.path.exists(export_paths["versioned_md_path"]), "No se exportó el reporte MD versionado."
        print("[OK] Toda la validación del Knowledge Analysis Engine fue exitosa.")

        # Check results
        index_file = os.path.join(test_project_path, "00_Index", "Index.md")
        char_file = os.path.join(test_project_path, "Biblioteca", "Personajes", "Monkey_D._Luffy.md")
        asset_crop = os.path.join(test_project_path, "Assets", "Personajes", "p001_obj_001_Gold_Roger.png")
        asset_index = os.path.join(test_project_path, "Assets", "index_assets.json")
        
        if os.path.exists(index_file) and os.path.exists(char_file) and os.path.exists(asset_crop) and os.path.exists(asset_index):
            print("\n[OK] ¡La prueba se ejecutó con éxito!")
            print(f" - Estructura creada en: {test_project_path}")
            print(f" - Archivos de personaje creados correctamente.")
            print(f" - Índice Markdown generado correctamente.")
            print(f" - Recorte visual e índice de assets generados correctamente.")
        else:
            print("\n[ERROR] El test terminó pero faltan archivos clave o recortes.")
            if not os.path.exists(asset_crop):
                print(f"    Falta recorte: {asset_crop}")
            if not os.path.exists(asset_index):
                print(f"    Falta index JSON de assets: {asset_index}")
            
    except Exception as e:
        print(f"\n[ERROR] Falló la ejecución de la prueba: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    run_test()
