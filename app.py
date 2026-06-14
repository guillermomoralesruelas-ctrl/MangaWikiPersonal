import os
import sys
import json
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory

from services.project_manager import ProjectManager
from services.json_manager import ProjectJSONManager, load_json
from services.markdown_generator import (
    generate_page_markdown,
    generate_character_markdown,
    generate_index_markdown,
    generate_entity_markdown,
    generate_relation_markdown,
    generate_timeline_markdown,
    clean_filename
)
from services.asset_extractor import process_detections, TYPE_MAP, BIBLIOTECA_MAP
from services.consistency_checker import check_project_consistency

app = Flask(__name__)
app.secret_key = "mangawiki_secret_key_local_only"

# Define default base path for all projects
BASE_PROJECTS_DIR = os.path.abspath("c:/Users/oaxac/Documents/programas/Manga/onepiece/MangaWikiPersonal/Proyectos")
project_manager = ProjectManager(BASE_PROJECTS_DIR)

# Ensure upload directory exists for temporary PDFs
UPLOAD_FOLDER = os.path.join(os.path.abspath("."), "temp_uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    projects = project_manager.list_projects()
    return render_template('index.html', projects=projects, project=None)

@app.route('/create-project', methods=['POST'])
def create_project():
    project_name = request.form.get('project_name')
    pdf_file = request.files.get('pdf_file')
    
    if not project_name or not pdf_file or pdf_file.filename == '':
        flash("Por favor, introduce un nombre y selecciona un archivo PDF válido.", "error")
        return redirect(url_for('index'))
        
    try:
        # Save uploaded PDF to temp location
        temp_pdf_path = os.path.join(UPLOAD_FOLDER, pdf_file.filename)
        pdf_file.save(temp_pdf_path)
        
        # Create project via ProjectManager
        project_id = project_manager.create_project(project_name, temp_pdf_path)
        
        # Remove temporary PDF upload
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
            
        flash(f"MangaWiki '{project_name}' creado con éxito.", "success")
        return redirect(url_for('view_project', project_id=project_id))
    except Exception as e:
        flash(f"Error al procesar el archivo PDF: {str(e)}", "error")
        return redirect(url_for('index'))

@app.route('/project/<project_id>')
def view_project(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    pages = json_mgr.load_pages()
    
    # Sort pages to get first 6
    sorted_pages = sorted(pages.items(), key=lambda x: x[0])
    first_pages = sorted_pages[:6]
    
    # Run auto-migration to ensure entity master is up to date
    from services.entity_manager import EntityManager
    ent_mgr = EntityManager(project_path)
    ent_mgr.run_auto_migration()
    entities = ent_mgr.load_entities()
    
    total_entities_active = len([x for x in entities if x.get("estado") == "activo"])
    chars = [x for x in entities if x.get("tipo") == "personaje" and x.get("estado") == "activo"]
    events = [x for x in entities if x.get("tipo") == "evento" and x.get("estado") == "activo"]
    places = [x for x in entities if x.get("tipo") == "lugar" and x.get("estado") == "activo"]
    objects = [x for x in entities if x.get("tipo") == "objeto" and x.get("estado") == "activo"]
    orgs = [x for x in entities if x.get("tipo") == "organizacion" and x.get("estado") == "activo"]
    
    relations = json_mgr.load_relations()
    timeline = json_mgr.load_timeline()
    
    alias_count = sum(len(x.get("alias", [])) for x in entities if x.get("estado") == "activo")
    
    # Load assets count
    assets_index_path = os.path.join(project_path, "Assets", "index_assets.json")
    assets = load_json(assets_index_path, default_value=[])
    
    # New Resolution Center metrics
    duplicates_count = len(ent_mgr.get_possible_duplicates())
    merges_count = len(ent_mgr.load_merge_log())
    
    no_alias_count = 0
    no_assets_count = 0
    no_relations_count = 0
    healthy_count = 0
    incomplete_count = 0
    orphan_count = 0
    
    for ent in entities:
        if ent.get("estado") == "activo":
            eid = ent["id"]
            
            # has alias
            has_alias = bool(ent.get("alias"))
            if not has_alias:
                no_alias_count += 1
                
            # has assets
            has_assets = any(a.get("entity_id") == eid for a in assets)
            if not has_assets:
                no_assets_count += 1
                
            # has relations
            has_relations = any(r.get("source_id") == eid or r.get("target_id") == eid for r in relations)
            if not has_relations:
                no_relations_count += 1
                
            # health score
            hs = ent_mgr.calculate_health_score(ent)
            if hs >= 80:
                healthy_count += 1
            elif hs >= 40:
                incomplete_count += 1
            else:
                orphan_count += 1
                
    stats = {
        "total_entities": total_entities_active,
        "characters": len(chars),
        "events": len(events),
        "places": len(places),
        "objects": len(objects),
        "organizations": len(orgs),
        "relations": len(relations),
        "timeline": len(timeline),
        "assets": len(assets),
        "aliases": alias_count,
        
        # New Resolution Center metrics
        "duplicates": duplicates_count,
        "merges": merges_count,
        "no_alias": no_alias_count,
        "no_assets": no_assets_count,
        "no_relations": no_relations_count,
        "healthy": healthy_count,
        "incomplete": incomplete_count,
        "orphans": orphan_count
    }

    # Run Analysis Engine to fetch high-level dashboard metrics
    try:
        from services.analysis_engine import AnalysisEngine
        engine = AnalysisEngine(project_path)
        report_data = engine.run_full_analysis()
        stats["knowledge_score"] = report_data["knowledge_score"]
        stats["coverage_pct"] = report_data["coverage_pct"]
        stats["critical_entities_count"] = report_data["critical_entities_count"]
        stats["suggested_relations_count"] = report_data["suggested_relations_count"]
        stats["recommendations_count"] = report_data["recommendations_count"]
    except Exception as e:
        stats["knowledge_score"] = 0.0
        stats["coverage_pct"] = 0.0
        stats["critical_entities_count"] = 0
        stats["suggested_relations_count"] = 0
        stats["recommendations_count"] = 0
    
    return render_template('project.html', 
                           project=meta, 
                           first_pages=first_pages, 
                           characters=[x["nombre"] for x in chars[:15]], 
                           places=[x["nombre"] for x in places[:15]],
                           stats=stats,
                           active_page='project')

@app.route('/project/<project_id>/pages')
def list_pages(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    pages = json_mgr.load_pages()
    
    # Sort pages
    sorted_pages = dict(sorted(pages.items(), key=lambda x: x[0]))
    
    return render_template('list_pages.html', 
                           project=meta, 
                           pages=sorted_pages, 
                           total_pages=len(sorted_pages),
                           active_page='pages')

@app.route('/project/<project_id>/image/<page_num>')
def get_page_image(project_id, page_num):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    image_dir = os.path.join(project_path, "Imagenes")
    filename = f"pagina_{page_num}.png"
    return send_from_directory(image_dir, filename)

@app.route('/project/<project_id>/page/edit/<page_num>')
def edit_page(project_id, page_num):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    pages = json_mgr.load_pages()
    
    page_data = pages.get(page_num)
    if not page_data:
        flash("Página no encontrada.", "error")
        return redirect(url_for('view_project', project_id=project_id))
        
    # Calculate prev/next
    total = meta.get("total_pages", 0)
    curr_int = int(page_num)
    prev_page = f"{curr_int - 1:03d}" if curr_int > 1 else None
    next_page = f"{curr_int + 1:03d}" if curr_int < total else None
    
    return render_template('edit_page.html',
                           project=meta,
                           page_num=page_num,
                           page_data=page_data,
                           prev_page=prev_page,
                           next_page=next_page,
                           active_page='pages')

@app.route('/project/<project_id>/page/save/<page_num>', methods=['POST'])
def save_page(project_id, page_num):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    pages = json_mgr.load_pages()
    
    if page_num not in pages:
        flash("Página no encontrada.", "error")
        return redirect(url_for('view_project', project_id=project_id))
        
    # Helper to parse comma-separated values to list
    def parse_csv(value):
        if not value:
            return []
        return [x.strip() for x in value.split(',') if x.strip()]
        
    # Helper to parse newline or text fields
    def parse_paragraphs(value):
        if not value:
            return ""
        return value.strip()

    # Update page info in memory
    pages[page_num]["texto"] = parse_paragraphs(request.form.get("texto"))
    pages[page_num]["narracion"] = parse_paragraphs(request.form.get("narracion"))
    pages[page_num]["descripcion_visual"] = parse_paragraphs(request.form.get("descripcion_visual"))
    pages[page_num]["personajes"] = parse_csv(request.form.get("personajes"))
    pages[page_num]["eventos"] = parse_csv(request.form.get("eventos"))
    pages[page_num]["lugares"] = parse_csv(request.form.get("lugares"))
    pages[page_num]["objetos"] = parse_csv(request.form.get("objetos"))
    
    # Curiosities and Relations (can be single texts or lists, let's treat them as texts)
    pages[page_num]["curiosidades"] = parse_paragraphs(request.form.get("curiosidades"))
    pages[page_num]["relaciones"] = parse_paragraphs(request.form.get("relaciones"))
    pages[page_num]["notas"] = parse_paragraphs(request.form.get("notas"))
    
    # Tags parsing (split by whitespace)
    tags_str = request.form.get("etiquetas", "")
    pages[page_num]["etiquetas"] = [t.strip() for t in tags_str.split() if t.strip()]
    if not pages[page_num]["etiquetas"]:
        pages[page_num]["etiquetas"] = ["#pagina", "#manga"]
        
    # 1. Save page details to JSON
    json_mgr.save_pages(pages)
    
    # 2. Re-generate Markdown note for this page
    generate_page_markdown(project_path, pages[page_num])
    
    # 3. Recalculate and update the global lists of entities from ALL pages
    all_chars = set()
    all_events = set()
    all_places = set()
    all_objects = set()
    
    # Entity to pages appearance mapping
    char_appearances = {}
    event_appearances = {}
    place_appearances = {}
    object_appearances = {}
    
    for p_num, p_info in pages.items():
        # Characters
        for char in p_info.get("personajes", []):
            all_chars.add(char)
            if char not in char_appearances:
                char_appearances[char] = set()
            char_appearances[char].add(p_num)
            
        # Events
        for ev in p_info.get("eventos", []):
            all_events.add(ev)
            if ev not in event_appearances:
                event_appearances[ev] = set()
            event_appearances[ev].add(p_num)
            
        # Places
        for pl in p_info.get("lugares", []):
            all_places.add(pl)
            if pl not in place_appearances:
                place_appearances[pl] = set()
            place_appearances[pl].add(p_num)
            
        # Objects
        for obj in p_info.get("objetos", []):
            all_objects.add(obj)
            if obj not in object_appearances:
                object_appearances[obj] = set()
            object_appearances[obj].add(p_num)
            
    # Save the updated entity lists to JSON
    json_mgr.save_characters(list(sorted(all_chars)))
    json_mgr.save_events(list(sorted(all_events)))
    json_mgr.save_places(list(sorted(all_places)))
    json_mgr.save_objects(list(sorted(all_objects)))
    
    # 4. Auto-migrate to entities.json database and update Obsidian sheets
    from services.entity_manager import EntityManager
    EntityManager(project_path).run_auto_migration()
        
    # 5. Re-generate Index.md
    meta = json_mgr.load_project_meta()
    generate_index_markdown(
        project_path,
        meta.get("name", project_id),
        meta.get("total_pages", 0),
        characters=list(all_chars),
        events=list(all_events),
        places=list(all_places),
        objects=list(all_objects),
        orgs=json_mgr.load_organizations()
    )
    
    flash(f"Página {page_num} guardada con éxito.", "success")
    
    # Redirect to next page or back to edit
    curr_int = int(page_num)
    if curr_int < meta.get("total_pages", 0):
        next_page_str = f"{curr_int + 1:03d}"
        return redirect(url_for('edit_page', project_id=project_id, page_num=next_page_str))
    
    return redirect(url_for('edit_page', project_id=project_id, page_num=page_num))

@app.route('/project/<project_id>/entity/<entity_type>')
def list_entities(project_id, entity_type):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    
    items = []
    title = ""
    if entity_type == 'characters':
        items = json_mgr.load_characters()
        title = "Personajes"
    elif entity_type == 'events':
        items = json_mgr.load_events()
        title = "Eventos"
    elif entity_type == 'places':
        items = json_mgr.load_places()
        title = "Lugares"
    elif entity_type == 'objects':
        items = json_mgr.load_objects()
        title = "Objetos"
    else:
        flash("Tipo de entidad inválido.", "error")
        return redirect(url_for('view_project', project_id=project_id))
        
    return render_template('list_items.html',
                           project=meta,
                           items=items,
                           title=title,
                           entity_type=entity_type,
                           active_page=entity_type)

@app.route('/project/<project_id>/character/<name>')
def view_character(project_id, name):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    
    cleaned_name = clean_filename(name)
    char_md_path = os.path.join(project_path, "Biblioteca", "Personajes", f"{cleaned_name}.md")
    
    # Read details from the markdown file to keep it interactive
    desc = "Pendiente."
    events = "Pendiente."
    relations = "Pendiente."
    notes = "Pendiente."
    
    if os.path.exists(char_md_path):
        try:
            with open(char_md_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            current_section = None
            sections = {"desc": [], "events": [], "relations": [], "notes": []}
            for line in lines:
                if line.startswith("# "):
                    continue
                elif line.startswith("## Descripción general"):
                    current_section = "desc"
                elif line.startswith("## Apariciones"):
                    current_section = "skip"
                elif line.startswith("## Eventos relacionados"):
                    current_section = "events"
                elif line.startswith("## Relaciones"):
                    current_section = "relations"
                elif line.startswith("## Notas personales"):
                    current_section = "notes"
                elif line.startswith("## ") or line.startswith("### "):
                    current_section = None
                else:
                    if current_section and current_section != "skip" and current_section in sections:
                        sections[current_section].append(line)
            
            if sections["desc"]: desc = "".join(sections["desc"]).strip()
            if sections["events"]: events = "".join(sections["events"]).strip()
            if sections["relations"]: relations = "".join(sections["relations"]).strip()
            if sections["notes"]: notes = "".join(sections["notes"]).strip()
        except Exception:
            pass

    details = {
        "desc": desc,
        "events": events,
        "relations": relations,
        "notes": notes
    }
    
    # Get appearances from pages.json
    pages = json_mgr.load_pages()
    appearances = []
    for p_num, p_info in pages.items():
        if name in p_info.get("personajes", []):
            appearances.append(p_num)
            
    appearances.sort()
    
    return render_template('view_character.html',
                           project=meta,
                           character_name=name,
                           filename=cleaned_name,
                           details=details,
                           appearances=appearances,
                           active_page='characters')

@app.route('/project/<project_id>/assets')
def list_assets(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    
    # Load assets index
    assets_index_path = os.path.join(project_path, "Assets", "index_assets.json")
    assets = load_json(assets_index_path, default_value=[])
    
    # Calculate stats
    stats = {
        "total": len(assets),
        "personajes": len([x for x in assets if x.get("tipo") == "personaje"]),
        "objetos": len([x for x in assets if x.get("tipo") == "objeto"]),
        "lugares": len([x for x in assets if x.get("tipo") == "lugar"]),
        "otros": len([x for x in assets if x.get("tipo") not in ["personaje", "objeto", "lugar"]])
    }
    
    # Sort assets by page and ID
    assets = sorted(assets, key=lambda x: (x.get("pagina", 0), x.get("id", "")))
    
    return render_template('assets.html',
                           project=meta,
                           assets=assets,
                           stats=stats,
                           type_map=TYPE_MAP,
                           active_page='assets')

@app.route('/project/<project_id>/assets/upload', methods=['POST'])
def upload_detections(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    detections_file = request.files.get('detections_file')
    if not detections_file or detections_file.filename == '':
        flash("Selecciona un archivo JSON válido de detecciones.", "error")
        return redirect(url_for('list_assets', project_id=project_id))
        
    try:
        data = json.load(detections_file)
        result = process_detections(project_path, data)
        
        # Auto-migrate and assign IDs to new assets
        from services.entity_manager import EntityManager
        EntityManager(project_path).run_auto_migration()
        
        msg = f"Se procesaron {result['processed']} recortes correctamente."
        if result['skipped'] > 0:
            msg += f" (Se omitieron {result['skipped']} IDs ya existentes)."
            
        flash(msg, "success")
        
        # Flash any warnings
        if result['warnings']:
            for w in result['warnings'][:5]: # limit flash spam
                flash(f"Aviso: {w}", "info")
                
    except Exception as e:
        flash(f"Error al procesar el archivo de detecciones: {str(e)}", "error")
        
    return redirect(url_for('list_assets', project_id=project_id))

@app.route('/project/<project_id>/assets/serve/<path:filename>')
def serve_asset_image(project_id, filename):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    assets_dir = os.path.join(project_path, "Assets")
    directory = os.path.dirname(os.path.join(assets_dir, filename))
    basename = os.path.basename(filename)
    return send_from_directory(directory, basename)

@app.route('/project/<project_id>/entities')
def list_entities_explorer(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    
    from services.entity_manager import EntityManager
    ent_mgr = EntityManager(project_path)
    entities = ent_mgr.load_entities()
    
    assets_path = os.path.join(project_path, "Assets", "index_assets.json")
    assets = load_json(assets_path, default_value=[])
    relations = json_mgr.load_relations()
    timeline = json_mgr.load_timeline()
    
    entity_stats = []
    for ent in entities:
        eid = ent["id"]
        
        # calculate counts
        asset_count = sum(1 for a in assets if a.get("entity_id") == eid)
        rel_count = sum(1 for r in relations if r.get("source_id") == eid or r.get("target_id") == eid)
        time_count = sum(1 for ev in timeline if eid in ev.get("participantes", []))
        
        appearances_count = time_count # simple count fallback
        health = ent_mgr.calculate_health_score(ent)
        
        entity_stats.append({
            "entity": ent,
            "health": health,
            "stats": {
                "appearances": appearances_count,
                "assets": asset_count,
                "relations": rel_count
            }
        })
        
    duplicates = ent_mgr.get_possible_duplicates()
    
    return render_template('entities.html',
                           project=meta,
                           entities=entity_stats,
                           duplicates=duplicates,
                           active_page='entities')

@app.route('/project/<project_id>/entity/<entity_id>')
def view_entity(project_id, entity_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    
    from services.entity_manager import EntityManager
    ent_mgr = EntityManager(project_path)
    entities = ent_mgr.load_entities()
    
    entity = None
    for ent in entities:
        if ent["id"] == entity_id:
            entity = ent
            break
            
    if not entity:
        flash("Entidad no encontrada.", "error")
        return redirect(url_for('list_entities_explorer', project_id=project_id))
        
    health = ent_mgr.calculate_health_score(entity)
    
    assets_path = os.path.join(project_path, "Assets", "index_assets.json")
    all_assets = load_json(assets_path, default_value=[])
    assets = [a for a in all_assets if a.get("entity_id") == entity_id]
    
    all_relations = json_mgr.load_relations()
    relations = [r for r in all_relations if r.get("source_id") == entity_id or r.get("target_id") == entity_id]
    
    all_timeline = json_mgr.load_timeline()
    timeline = [ev for ev in all_timeline if entity_id in ev.get("participantes", [])]
    
    history = [log for log in ent_mgr.load_history() if log.get("entity_id") == entity_id]
    
    return render_template('view_entity.html',
                           project=meta,
                           entity=entity,
                           health=health,
                           assets=assets,
                           relations=relations,
                           timeline=timeline,
                           history=history,
                           active_page='entities')

@app.route('/project/<project_id>/entity/<entity_id>/alias/add', methods=['POST'])
def add_entity_alias(project_id, entity_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    alias_name = request.form.get("alias_name")
    from services.entity_manager import EntityManager
    ent_mgr = EntityManager(project_path)
    
    success, msg = ent_mgr.add_alias(entity_id, alias_name)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "error")
        
    return redirect(url_for('view_entity', project_id=project_id, entity_id=entity_id))

@app.route('/project/<project_id>/entity/<entity_id>/alias/delete', methods=['POST'])
def delete_entity_alias(project_id, entity_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    alias_name = request.form.get("alias_name")
    from services.entity_manager import EntityManager
    ent_mgr = EntityManager(project_path)
    
    success, msg = ent_mgr.delete_alias(entity_id, alias_name)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "error")
        
    return redirect(url_for('view_entity', project_id=project_id, entity_id=entity_id))

@app.route('/project/<project_id>/merge', methods=['POST'])
def merge_entities_post(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    master_id = request.form.get("master_id")
    secondary_id = request.form.get("secondary_id")
    reason = request.form.get("reason", "Duplicado")
    
    from services.entity_manager import EntityManager
    ent_mgr = EntityManager(project_path)
    
    success, msg = ent_mgr.merge_entities(master_id, secondary_id, reason)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "error")
        
    return redirect(url_for('list_entities_explorer', project_id=project_id))

@app.route('/project/<project_id>/entity-recovery')
def view_recovery(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    
    from services.entity_manager import EntityManager
    ent_mgr = EntityManager(project_path)
    entities = ent_mgr.load_entities()
    
    merged_entities = [x for x in entities if x.get("estado") == "merged"]
    merge_log = ent_mgr.load_merge_log()
    
    for ent in merged_entities:
        for log in merge_log:
            if log.get("merged") == ent["id"]:
                ent["merge_info"] = log
                break
                
    global_history = ent_mgr.load_history()
    global_history = sorted(global_history, key=lambda x: x.get("fecha", ""), reverse=True)
    
    return render_template('recovery.html',
                           project=meta,
                           merged_entities=merged_entities,
                           global_history=global_history,
                           active_page='entities')

@app.route('/project/<project_id>/entity-recovery/restore', methods=['POST'])
def restore_entity_post(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    entity_id = request.form.get("entity_id")
    from services.entity_manager import EntityManager
    ent_mgr = EntityManager(project_path)
    
    success, msg = ent_mgr.restore_entity(entity_id)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "error")
        
    return redirect(url_for('view_recovery', project_id=project_id))

@app.route('/project/<project_id>/analysis')
def view_analysis(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    
    from services.analysis_engine import AnalysisEngine
    engine = AnalysisEngine(project_path)
    report_data = engine.run_full_analysis()
    
    return render_template('analysis.html',
                           project=meta,
                           data=report_data,
                           active_page='analysis')

@app.route('/project/<project_id>/analysis/export', methods=['POST'])
def export_analysis_report(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    from services.analysis_engine import AnalysisEngine
    engine = AnalysisEngine(project_path)
    paths = engine.export_reports()
    
    flash(f"Reporte exportado con éxito en: {os.path.basename(paths['json_path'])} y {os.path.basename(paths['md_path'])}", "success")
    flash(f"Copia versionada guardada en Datos_JSON/Reportes_Analisis/", "info")
    return redirect(url_for('view_analysis', project_id=project_id))

@app.route('/project/<project_id>/library')
def library_dashboard(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    
    # Load all entity lists from entities.json
    from services.entity_manager import EntityManager
    ent_mgr = EntityManager(project_path)
    entities = ent_mgr.load_entities()
    
    characters = [x["nombre"] for x in entities if x.get("tipo") == "personaje"]
    events = [x["nombre"] for x in entities if x.get("tipo") == "evento"]
    places = [x["nombre"] for x in entities if x.get("tipo") == "lugar"]
    objects = [x["nombre"] for x in entities if x.get("tipo") == "objeto"]
    orgs = [x["nombre"] for x in entities if x.get("tipo") == "organizacion"]
    
    relations = json_mgr.load_relations()
    timeline = json_mgr.load_timeline()
    
    # Sort timeline elements by event number
    timeline = sorted(timeline, key=lambda x: x.get("num", 1))
    
    return render_template('library.html',
                           project=meta,
                           characters=characters,
                           events=events,
                           places=places,
                           objects=objects,
                           organizations=orgs,
                           relations=relations,
                           timeline=timeline,
                           active_page='library')

@app.route('/project/<project_id>/relation/new', methods=['GET', 'POST'])
def new_relation(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    
    from services.entity_manager import EntityManager
    ent_mgr = EntityManager(project_path)
    
    if request.method == 'POST':
        ent_a = request.form.get("entidad_a")
        ent_b = request.form.get("entidad_b")
        rel_type = request.form.get("tipo")
        evidence = request.form.get("evidencia")
        notes = request.form.get("notes") # Form text area name is 'notas' or 'notes'? Let's check both
        if not notes:
            notes = request.form.get("notas")
            
        if not ent_a or not ent_b or not rel_type:
            flash("Todos los campos excepto notas son obligatorios.", "error")
            return redirect(url_for('new_relation', project_id=project_id))
            
        sid = ent_mgr.resolve_to_id(ent_a)
        tid = ent_mgr.resolve_to_id(ent_b)
        
        if not sid or not tid:
            flash("Entidades seleccionadas inválidas.", "error")
            return redirect(url_for('new_relation', project_id=project_id))
            
        relations = json_mgr.load_relations()
        new_rel = {
            "source_id": sid,
            "target_id": tid,
            "entidad_a": ent_a.strip(),
            "entidad_b": ent_b.strip(),
            "tipo": rel_type.strip(),
            "evidencia": evidence.strip(),
            "notas": notes.strip() if notes else "Pendiente"
        }
        relations.append(new_rel)
        json_mgr.save_relations(relations)
        
        # Generate Obsidian sheet
        generate_relation_markdown(project_path, new_rel)
        
        flash(f"Relación registrada con éxito.", "success")
        return redirect(url_for('library_dashboard', project_id=project_id))
        
    # For GET: get list of candidates from entities.json
    entities = ent_mgr.load_entities()
    candidates = sorted([x["nombre"] for x in entities if x.get("tipo") in ["personaje", "organizacion"]])
    
    return render_template('new_relation.html', project=meta, candidates=candidates, active_page='library')

@app.route('/project/<project_id>/timeline/new', methods=['GET', 'POST'])
def new_timeline_event(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    
    from services.entity_manager import EntityManager
    ent_mgr = EntityManager(project_path)
    
    if request.method == 'POST':
        num = request.form.get("num", type=int)
        name = request.form.get("nombre")
        first_app = request.form.get("primera_aparicion")
        participants = request.form.getlist("participantes")
        desc = request.form.get("descripcion")
        conseq = request.form.get("consecuencias")
        
        if not name or not num:
            flash("Número y nombre del acontecimiento son obligatorios.", "error")
            return redirect(url_for('new_timeline_event', project_id=project_id))
            
        timeline = json_mgr.load_timeline()
        
        # Check duplicate number
        if any(x.get("num") == num for x in timeline):
            flash(f"Ya existe un acontecimiento con el número {num:04d} en el timeline.", "error")
            return redirect(url_for('new_timeline_event', project_id=project_id))
            
        # Resolve participant names to IDs
        part_ids = [ent_mgr.resolve_to_id(p) for p in participants if p.strip()]
        
        new_ev = {
            "num": num,
            "nombre": name.strip(),
            "primera_aparicion": first_app.strip() if first_app else "Pendiente",
            "participantes": [pid for pid in part_ids if pid],
            "descripcion": desc.strip() if desc else "Pendiente",
            "consecuencias": conseq.strip() if conseq else "Pendiente"
        }
        timeline.append(new_ev)
        json_mgr.save_timeline(timeline)
        
        # Generate Obsidian sheet (requires names list for md links)
        ev_copy = new_ev.copy()
        ev_copy["participantes"] = [p.strip() for p in participants if p.strip()]
        generate_timeline_markdown(project_path, ev_copy)
        
        flash(f"Acontecimiento registrado en el Timeline.", "success")
        return redirect(url_for('library_dashboard', project_id=project_id))
        
    timeline = json_mgr.load_timeline()
    next_num = max([x.get("num", 0) for x in timeline]) + 1 if timeline else 1
    
    # Load candidates from entities.json
    entities = ent_mgr.load_entities()
    candidates = sorted([x["nombre"] for x in entities if x.get("tipo") == "personaje"])
    
    return render_template('new_timeline.html', project=meta, next_num=next_num, candidates=candidates, active_page='library')

@app.route('/project/<project_id>/admin/consistency')
def view_consistency_report(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if not os.path.exists(project_path):
        flash("Proyecto no encontrado.", "error")
        return redirect(url_for('index'))
        
    json_mgr = ProjectJSONManager(project_path)
    meta = json_mgr.load_project_meta()
    
    report = check_project_consistency(project_path)
    
    return render_template('consistency.html', project=meta, report=report, active_page='project')

@app.route('/project/<project_id>/open-folder')
def open_obsidian_info(project_id):
    project_path = os.path.join(BASE_PROJECTS_DIR, project_id)
    if os.path.exists(project_path):
        try:
            # Native Windows folder opening
            os.startfile(project_path)
            flash("Carpeta del proyecto abierta en el Explorador.", "success")
        except Exception as e:
            flash(f"No se pudo abrir la carpeta automáticamente: {str(e)}", "error")
    else:
        flash("La ruta del proyecto no existe.", "error")
        
    return redirect(url_for('view_project', project_id=project_id))

if __name__ == '__main__':
    # Default local dev port
    print(f"Iniciando MangaWiki Personal en http://localhost:5000")
    print(f"Bóveda de proyectos configurada en: {BASE_PROJECTS_DIR}")
    app.run(host='127.0.0.1', port=5000, debug=True)
