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
            
        # Add alias Zoro to Roronoa Zoro
        zoro_id = em.resolve_to_id("Roronoa Zoro")
        success, msg = em.add_alias(zoro_id, "Zoro")
        print(f" -> Agregar alias 'Zoro' a Zoro ({zoro_id}): {success} ({msg})")
            
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

        # Test Entity Assisted Editor
        print("\n--- Probando Entity Assisted Editor ---")
        from app import app
        app.config['TESTING'] = True
        client = app.test_client()
        
        # 1. API autocomplete endpoint
        res = client.get(f'/project/{test_project_id}/api/entities')
        assert res.status_code == 200, "Error en API de entidades"
        ents = json.loads(res.data)
        print(f" -> Entidades obtenidas por API: {len(ents)}")
        
        # 2. Quick Create entity with similarity checks
        res = client.post(f'/project/{test_project_id}/api/entity/quick-create', json={
            "nombre": "Koby",
            "tipo": "personaje",
            "alias": ["Coby"]
        })
        assert res.status_code == 200, "Error en quick create"
        qc_res = json.loads(res.data)
        assert qc_res["status"] == "success"
        print(f" -> Quick create exitoso para: {qc_res['entity']['nombre']} ({qc_res['entity']['id']})")
        
        # Quick create similarity test (Koby vs Koby)
        res = client.post(f'/project/{test_project_id}/api/entity/quick-create', json={
            "nombre": "Koby",
            "tipo": "personaje"
        })
        assert res.status_code == 400, "Debió rechazar duplicado exacto"
        print(" -> Duplicado exacto bloqueado correctamente.")
        
        # Quick create warning test (nombres similares)
        res = client.post(f'/project/{test_project_id}/api/entity/quick-create', json={
            "nombre": "Kobi",
            "tipo": "personaje"
        })
        qc_warn = json.loads(res.data)
        assert qc_warn["status"] == "warning", "Debió advertir similitud"
        print(f" -> Advertencia de similitud capturada: {qc_warn['warnings'][0]}")
        
        # 3. Preview impact check
        res = client.post(f'/project/{test_project_id}/api/page/preview-impact', json={
            "page_num": "001",
            "personajes": ["Monkey D. Luffy", "Nami"],
            "eventos": [],
            "lugares": [],
            "objetos": []
        })
        assert res.status_code == 200, "Error en impact preview"
        imp_res = json.loads(res.data)
        assert imp_res["new_entities"] == 1, "Debería sugerir crear 1 nueva entidad (Nami)"
        print(f" -> Preview impact reportado: {imp_res['new_entities']} nuevas entidades.")
        
        # 4. Save page resolving: Structured format save
        res = client.post(f'/project/{test_project_id}/page/save/001', data={
            "texto": "Texto modificado",
            "personajes_json": json.dumps([
                {"entity_id": "char_000001", "nombre": "Monkey D. Luffy"},
                {"entity_id": "", "nombre": "Mugiwara"},
                {"entity_id": "", "nombre": "Nami"}
            ]),
            "eventos_json": "[]",
            "lugares_json": "[]",
            "objetos_json": "[]",
            "relaciones": "",
            "notas": "",
            "etiquetas": "#test"
        })
        assert res.status_code == 302, "Error al guardar página en modo asistido"
        
        # Load pages to verify format
        pages_after = json_mgr.load_pages()
        saved_chars = pages_after["001"]["personajes"]
        print(f" -> Personajes guardados en página 001: {saved_chars}")
        
        # Verify Luffy and Mugiwara mapped to Monkey D. Luffy, Nami discarded (Ajuste 3)
        assert len(saved_chars) == 2, "Deberían guardarse solo 2 personajes (Nami descartada al no tener ID)"
        assert saved_chars[0]["entity_id"] == "char_000001", "Luffy no resolvió a ID correcto"
        assert saved_chars[1]["entity_id"] == "char_000001", "Alias Mugiwara no resolvió a ID correcto"
        
        # 5. Verify Obsidian page Markdown continues to render plain links
        page_md_path = os.path.join(test_project_path, "Paginas", "Pagina_001.md")
        with open(page_md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        assert "[[Monkey_D._Luffy]]" in md_content, "El markdown no renderizó el link limpio de Luffy"
        assert "entity_id" not in md_content, "El markdown renderizó el formato diccionario JSON por error"
        print(" -> Obsidian Markdown renderiza links planos correctamente.")
        
        # 6. Verify Classic Editor compatibility: CSV save auto-resolves
        res = client.post(f'/project/{test_project_id}/page/save/002', data={
            "editor_mode": "classic",
            "personajes": "Monkey D. Luffy, Zoro",
            "eventos": "",
            "lugares": "",
            "objetos": "",
            "relaciones": "",
            "notas": "",
            "etiquetas": "#test"
        })
        assert res.status_code == 302, "Error al guardar en modo clásico"
        
        pages_classic = json_mgr.load_pages()
        saved_chars_classic = pages_classic["002"]["personajes"]
        print(f" -> Personajes en clásica: {saved_chars_classic}")
        assert isinstance(saved_chars_classic[0], dict), "Editor clásico no migró personajes a dict"
        assert saved_chars_classic[0]["entity_id"] == "char_000001", "Luffy clásica falló resolución"
        assert saved_chars_classic[1]["entity_id"] == "char_000002", "Zoro clásica falló resolución"
        
        print("[OK] Toda la validación del Entity Assisted Editor fue exitosa.")

        # Test ChatGPT Analysis Importer
        print("\n--- Probando ChatGPT Analysis Importer ---")
        
        # 1. Complete structured Markdown parsing test
        markdown_complete = """
## Página 001
### Tipo de página
Historia principal

### Narración
En este día comenzó la gran era de la piratería.

### Descripción visual
El Rey de los Piratas sonríe antes de su ejecución.

### Personajes presentes
- Monkey D. Luffy
- Gold Roger
- Personaje Nuevo Test

### Eventos importantes
- Gran Ejecución de Roger

### Lugares
- Loguetown

### Objetos importantes
- Espada de Ejecución

### Relaciones detectadas
- Gold Roger -> Monkey D. Luffy: Admiración e inspiración de la era pirata.

### Curiosidades
- Roger nació en Loguetown.

### Etiquetas
#historia #inicio #roger

```json
{
  "elementos": [
    {
      "id": "p001_roger_valid",
      "tipo": "personaje",
      "nombre": "Gold Roger",
      "descripcion": "El legendario Rey de los Piratas",
      "bbox_normalizado": {
        "x": 0.1,
        "y": 0.2,
        "ancho": 0.3,
        "alto": 0.4
      }
    }
  ]
}
```
"""
        res = client.post(f'/project/{test_project_id}/page/001/import-analysis/parse', json={
            "text_content": markdown_complete
        })
        assert res.status_code == 200, "Error al parsear Markdown completo"
        parsed_res = json.loads(res.data)
        print(" -> Markdown completo parseado con éxito.")
        assert parsed_res["pagina"] == 1
        assert parsed_res["tipo_pagina"] == "Historia principal"
        assert parsed_res["narracion"] == "En este día comenzó la gran era de la piratería."
        assert len(parsed_res["personajes"]) == 3
        assert len(parsed_res["detecciones_validas"]) == 1
        assert len(parsed_res["detecciones_invalidas"]) == 0
        
        # 2. JSON complete test
        json_complete = {
            "pagina": 1,
            "tipo_pagina": "Historia principal",
            "narracion": "El inicio de una nueva leyenda.",
            "descripcion_visual": "Luffy de pie en el barco.",
            "personajes": [{"nombre": "Monkey D. Luffy"}, {"nombre": "Roronoa Zoro"}],
            "eventos": ["El juramento"],
            "lugares": ["Mar de la supervivencia"],
            "objetos": ["Katanas de Zoro"],
            "relaciones": [{"source": "Roronoa Zoro", "target": "Monkey D. Luffy", "tipo": "interaccion", "evidencia": "Promesa de lealtad"}],
            "curiosidades": ["Zoro duerme mucho"],
            "etiquetas": ["#juramento", "#luffy"],
            "detecciones_visuales": {
                "elementos": [
                    {
                        "id": "p001_zoro_valid_abs",
                        "tipo": "personaje",
                        "nombre": "Roronoa Zoro",
                        "descripcion": "Cazador de piratas",
                        "bbox": {
                            "x": 50,
                            "y": 50,
                            "ancho": 100,
                            "alto": 150
                        }
                    }
                ]
            }
        }
        res = client.post(f'/project/{test_project_id}/page/001/import-analysis/parse', json={
            "text_content": json.dumps(json_complete)
        })
        assert res.status_code == 200, "Error al parsear JSON completo"
        parsed_json_res = json.loads(res.data)
        print(" -> JSON completo parseado con éxito.")
        assert parsed_json_res["pagina"] == 1
        assert len(parsed_json_res["detecciones_validas"]) == 1
        assert len(parsed_json_res["detecciones_invalidas"]) == 0
        
        # 3. Markdown / JSON without visual detections (page-only mode - Ajuste #4 & #5)
        markdown_no_assets = """
## Página 001
### Narración
Escena tranquila en el mar.
### Descripción visual
Solo olas y viento.
### Personajes presentes
- Luffy
"""
        res = client.post(f'/project/{test_project_id}/page/001/import-analysis/parse', json={
            "text_content": markdown_no_assets
        })
        assert res.status_code == 200
        parsed_no_assets = json.loads(res.data)
        print(" -> Modo 'solo página' (sin assets) parseado con éxito.")
        assert len(parsed_no_assets["detecciones_validas"]) == 0
        assert len(parsed_no_assets["detecciones_invalidas"]) == 0
        
        # 4. Incorrect page warning test (Ajuste #9)
        markdown_wrong_page = """
## Página 005
### Narración
Test
"""
        res = client.post(f'/project/{test_project_id}/page/001/import-analysis/parse', json={
            "text_content": markdown_wrong_page
        })
        assert res.status_code == 200
        parsed_wrong = json.loads(res.data)
        print(" -> Validación de página incorrecta exitosa.")
        has_warning = any("no coincide con la página actual" in w for w in parsed_wrong["warnings"])
        assert has_warning, "Debió generar advertencia de página incorrecta"
        
        # 5. Coordinate tests (valid/invalid bbox & bbox_normalizado - Ajuste #12)
        # bbox_normalizado inválido
        json_invalid_norm = {
            "pagina": 1,
            "detecciones_visuales": {
                "elementos": [
                    {
                        "id": "det_invalid_norm",
                        "tipo": "objeto",
                        "nombre": "Test",
                        "bbox_normalizado": {"x": 1.5, "y": 0.5, "ancho": 0.2, "alto": 0.2}
                    }
                ]
            }
        }
        res = client.post(f'/project/{test_project_id}/page/001/import-analysis/parse', json={
            "text_content": json.dumps(json_invalid_norm)
        })
        parsed_invalid_norm = json.loads(res.data)
        print(" -> Validación bbox_normalizado fuera de rango exitosa.")
        assert len(parsed_invalid_norm["detecciones_invalidas"]) == 1
        assert "rango 0.0-1.0" in parsed_invalid_norm["detecciones_invalidas"][0]["error_reason"]
        
        # bbox absoluto inválido (valores negativos)
        json_invalid_abs = {
            "pagina": 1,
            "detecciones_visuales": {
                "elementos": [
                    {
                        "id": "det_invalid_abs",
                        "tipo": "objeto",
                        "nombre": "Test",
                        "bbox": {"x": -10, "y": 50, "ancho": 100, "alto": 100}
                    }
                ]
            }
        }
        res = client.post(f'/project/{test_project_id}/page/001/import-analysis/parse', json={
            "text_content": json.dumps(json_invalid_abs)
        })
        parsed_invalid_abs = json.loads(res.data)
        print(" -> Validación bbox absoluto con negativos exitosa.")
        assert len(parsed_invalid_abs["detecciones_invalidas"]) == 1
        assert "negativas" in parsed_invalid_abs["detecciones_invalidas"][0]["error_reason"]

        # 6. Duplicate asset ID validation (Ajuste #12)
        # Gold Roger is already registered in mock test run (id "p001_obj_001")
        json_dup_asset = {
            "pagina": 1,
            "detecciones_visuales": {
                "elementos": [
                    {
                        "id": "p001_obj_001",
                        "tipo": "personaje",
                        "nombre": "Gold Roger",
                        "bbox": {"x": 10, "y": 10, "ancho": 10, "alto": 10}
                    }
                ]
            }
        }
        res = client.post(f'/project/{test_project_id}/page/001/import-analysis/parse', json={
            "text_content": json.dumps(json_dup_asset)
        })
        parsed_dup_asset = json.loads(res.data)
        print(" -> Validación ID de asset duplicado exitosa.")
        assert len(parsed_dup_asset["detecciones_invalidas"]) == 1
        assert "ya existe en el índice" in parsed_dup_asset["detecciones_invalidas"][0]["error_reason"]

        # 7. Entity Resolution Center match checks (Ajuste #10 & #12)
        # Existing entity by name ("Monkey D. Luffy")
        # Existing entity by alias ("Mugiwara")
        # New entity confirmation
        json_entity_matching = {
            "pagina": 1,
            "personajes": ["Monkey D. Luffy", "Mugiwara", "Nueva Entidad Test"]
        }
        res = client.post(f'/project/{test_project_id}/page/001/import-analysis/parse', json={
            "text_content": json.dumps(json_entity_matching)
        })
        parsed_ent_match = json.loads(res.data)
        print(" -> Validación resolución de entidades (nombre/alias/nueva) exitosa.")
        existentes_ids = [e["id"] for e in parsed_ent_match["entities_summary"]["existentes"]]
        assert luffy_id in existentes_ids, "Debería mapear a Luffy"
        # Mugiwara is alias of Luffy, so it should also resolve to luffy_id
        assert existentes_ids.count(luffy_id) == 2, "Tanto Luffy como Mugiwara deberían mapearse a Luffy"
        
        # 8. Save/Import tests (raw and parsed import archives, suggest relation, suggest timeline)
        # Let's save a parsed result
        res = client.post(f'/project/{test_project_id}/page/001/import-analysis/save', json={
            "text_content": markdown_complete,
            "parsed_json": parsed_res["raw_parsed"],
            "confirm_relations": False, # Desactivada por defecto (Ajuste #6)
            "confirm_timeline": False    # Desactivada por defecto (Ajuste #7)
        })
        assert res.status_code == 200
        save_res = json.loads(res.data)
        assert save_res["status"] == "success"
        print(" -> Guardado de importación exitoso.")
        
        # Check that imports_raw and imports_parsed directories exist and have files (Ajuste #2 & #3)
        raw_files = os.listdir(os.path.join(test_project_path, "Datos_JSON", "imports_raw"))
        parsed_files = os.listdir(os.path.join(test_project_path, "Datos_JSON", "imports_parsed"))
        assert len(raw_files) > 0, "No se guardó el raw import"
        assert len(parsed_files) > 0, "No se guardó el parsed import"
        print(" -> Respaldo de raw import (.md) y parsed import (.json) verificado con éxito.")
        
        # Check pages.json was updated with structured format (Ajuste #8)
        pages_wiki = json_mgr.load_pages()
        assert isinstance(pages_wiki["001"]["personajes"][0], dict), "Los personajes no están guardados en formato estructurado"
        assert "entity_id" in pages_wiki["001"]["personajes"][0], "Falta entity_id en formato estructurado"
        print(" -> Formato estructurado con entity_id verificado en paginas.json.")

        print("[OK] Toda la validación del ChatGPT Analysis Importer fue exitosa.")

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
