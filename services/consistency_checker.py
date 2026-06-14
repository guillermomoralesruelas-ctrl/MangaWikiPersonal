import os
import json
import re
from .markdown_generator import clean_filename, parse_md_sections
from .entity_manager import EntityManager

def check_project_consistency(project_path):
    report = {
        "orphaned_assets": [],          # Files in Assets/ not in index_assets.json
        "empty_sources": [],            # Markdown profiles in Biblioteca/ with empty Fuentes
        "broken_relationships": [],      # Relationships with broken/nonexistent IDs
        "missing_markdown_files": [],    # Broken Obsidian links [[Link]] pointing to nonexistent files
        "duplicated_ids": [],            # Duplicated IDs in entities.json
        "duplicated_aliases": [],        # Alias assigned to more than one entity
        "invalid_first_appearances": [], # Entities with invalid first appearance links
        "assets_missing_entity_id": [],  # Assets in index_assets.json without entity_id
        "orphan_entities": [],           # Active entities without alias, assets, relations, timeline
        "invalid_timeline_events": [],   # Timeline events with participants pointing to nonexistent IDs
        "broken_redirects": [],          # Redirects pointing to nonexistent IDs
        "warnings": []
    }
    
    # 1. Load entities database
    entity_mgr = EntityManager(project_path)
    entities = entity_mgr.load_entities()
    
    # Check Duplicated IDs & Duplicated Aliases
    id_counts = {}
    alias_map = {} # alias_lower -> list of entity IDs
    entity_ids = set()
    active_entity_ids = set()
    
    for ent in entities:
        eid = ent.get("id")
        name = ent.get("nombre")
        aliases = ent.get("alias", [])
        estado = ent.get("estado", "activo")
        
        if eid:
            id_counts[eid] = id_counts.get(eid, 0) + 1
            entity_ids.add(eid)
            if estado == "activo":
                active_entity_ids.add(eid)
            
        # Alias check
        for a in aliases:
            a_low = a.strip().lower()
            if a_low not in alias_map:
                alias_map[a_low] = []
            alias_map[a_low].append(eid)
            
    # Record duplicates
    for eid, count in id_counts.items():
        if count > 1:
            report["duplicated_ids"].append(f"ID duplicado '{eid}' encontrado {count} veces.")
            
    for alias_low, eids in alias_map.items():
        if len(eids) > 1:
            report["duplicated_aliases"].append(f"Alias '{alias_low}' asignado a múltiples IDs: {', '.join(eids)}.")
            
    # 2. Check Assets Index (assets_missing_entity_id & orphaned_assets)
    assets_index_path = os.path.join(project_path, "Assets", "index_assets.json")
    indexed_assets = {}
    asset_entity_counts = {}
    
    if os.path.exists(assets_index_path):
        try:
            with open(assets_index_path, 'r', encoding='utf-8') as f:
                assets_meta = json.load(f)
            for asset in assets_meta:
                aid = asset.get("id")
                filepath = os.path.basename(asset.get("archivo", ""))
                indexed_assets[filepath] = asset
                
                # Check missing entity_id
                ae_id = asset.get("entity_id")
                if not ae_id:
                    report["assets_missing_entity_id"].append(f"Asset '{aid}' sin campo entity_id.")
                else:
                    # Resolve redirects recursively
                    resolved_ae_id = entity_mgr.resolve_redirect_id(ae_id)
                    if resolved_ae_id not in entity_ids:
                        report["assets_missing_entity_id"].append(f"Asset '{aid}' apunta a un entity_id inexistente: '{ae_id}'.")
                    else:
                        asset_entity_counts[resolved_ae_id] = asset_entity_counts.get(resolved_ae_id, 0) + 1
        except Exception as e:
            report["warnings"].append(f"Error al cargar index_assets.json: {str(e)}")
            
    # Check Orphan Files
    assets_dir = os.path.join(project_path, "Assets")
    if os.path.exists(assets_dir):
        for root, dirs, files in os.walk(assets_dir):
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    if file not in indexed_assets:
                        rel_path = os.path.relpath(os.path.join(root, file), project_path)
                        report["orphaned_assets"].append(rel_path)
                        
    # 3. Check Relationships (broken_relationships)
    from .json_manager import ProjectJSONManager
    json_mgr = ProjectJSONManager(project_path)
    relations = json_mgr.load_relations()
    relation_entity_counts = {}
    
    for rel in relations:
        sid = rel.get("source_id")
        tid = rel.get("target_id")
        ent_a = rel.get("entidad_a")
        ent_b = rel.get("entidad_b")
        
        errors = []
        if sid:
            resolved_sid = entity_mgr.resolve_redirect_id(sid)
            if resolved_sid not in entity_ids:
                errors.append(f"Source ID inválido o inexistente: '{sid}'")
            else:
                relation_entity_counts[resolved_sid] = relation_entity_counts.get(resolved_sid, 0) + 1
        else:
            errors.append("Falta Source ID")
            
        if tid:
            resolved_tid = entity_mgr.resolve_redirect_id(tid)
            if resolved_tid not in entity_ids:
                errors.append(f"Target ID inválido o inexistente: '{tid}'")
            else:
                relation_entity_counts[resolved_tid] = relation_entity_counts.get(resolved_tid, 0) + 1
        else:
            errors.append("Falta Target ID")
            
        if errors:
            report["broken_relationships"].append({
                "entidad_a": ent_a or "Desconocida",
                "entidad_b": ent_b or "Desconocida",
                "tipo": rel.get("tipo", ""),
                "error": " & ".join(errors)
            })
            
    # 4. Check Timeline (invalid_timeline_events)
    timeline = json_mgr.load_timeline()
    timeline_entity_counts = {}
    
    for ev in timeline:
        parts = ev.get("participantes", [])
        num = ev.get("num", 0)
        name = ev.get("nombre", "Sin Nombre")
        
        bad_parts = []
        for p in parts:
            resolved_p = entity_mgr.resolve_redirect_id(p)
            if resolved_p not in entity_ids:
                bad_parts.append(p)
            else:
                timeline_entity_counts[resolved_p] = timeline_entity_counts.get(resolved_p, 0) + 1
                
        if bad_parts:
            report["invalid_timeline_events"].append(
                f"Acontecimiento {num:04d} '{name}' tiene participantes con IDs inválidos: {', '.join(bad_parts)}"
            )
            
    # 5. Check Redirects (broken_redirects)
    redirects = entity_mgr.load_redirects()
    for source, target in redirects.items():
        if entity_mgr.resolve_redirect_id(target) not in entity_ids:
            report["broken_redirects"].append(f"Redirección rota: {source} -> {target} (ID de destino inexistente)")

    # 6. Check First Appearances (invalid_first_appearances)
    pages_dir = os.path.join(project_path, "Paginas")
    for ent in entities:
        eid = ent.get("id")
        name = ent.get("nombre")
        first_app = ent.get("primera_aparicion", {})
        
        page = first_app.get("pagina")
        
        # Validate page exists
        if page and page != "Pendiente":
            p_file = os.path.join(pages_dir, f"{page}.md")
            if not os.path.exists(p_file):
                report["invalid_first_appearances"].append(f"Entidad '{name}' ({eid}) tiene una primera aparición inválida (Página inexistente: '{page}').")
                
    # 7. Check Orphan Entities
    for ent in entities:
        if ent.get("estado", "activo") == "activo":
            eid = ent["id"]
            alias_cnt = len(ent.get("alias", []))
            asset_cnt = asset_entity_counts.get(eid, 0)
            rel_cnt = relation_entity_counts.get(eid, 0)
            time_cnt = timeline_entity_counts.get(eid, 0)
            
            if alias_cnt == 0 and asset_cnt == 0 and rel_cnt == 0 and time_cnt == 0:
                report["orphan_entities"].append(f"Entidad huérfana '{ent['nombre']}' ({eid}) no posee alias, recortes, relaciones ni apariciones en timeline.")

    # 8. Check Biblioteca profiles for missing md files
    bib_dir = os.path.join(project_path, "Biblioteca")
    valid_names_clean = {clean_filename(x["nombre"]) for x in entities}
    
    if os.path.exists(bib_dir):
        for root, dirs, files in os.walk(bib_dir):
            for file in files:
                if file.endswith(".md"):
                    file_path = os.path.join(root, file)
                    rel_dir = os.path.basename(root)
                    
                    sections = parse_md_sections(file_path)
                    
                    # Check Fuentes
                    sources_sec = sections.get("Fuentes", "")
                    if not sources_sec or "* Pendiente" in sources_sec or sources_sec.strip() == "":
                        if rel_dir not in ["Relaciones", "Timeline"]:
                            report["empty_sources"].append(f"Biblioteca/{rel_dir}/{file}")
                            
                    # Scan for broken Obsidian links
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        
                        links = re.findall(r'\[\[([^\]]+)\]\]', content)
                        for link in links:
                            link_clean = clean_filename(link.split('|')[0])
                            
                            # Skip standard files
                            if link_clean.startswith("Pagina_") or link_clean.endswith(".png"):
                                continue
                                
                            if link_clean not in valid_names_clean:
                                found = False
                                for ent_folder in ["Personajes", "Eventos", "Lugares", "Objetos", "Organizaciones", "Relaciones", "Timeline"]:
                                    if os.path.exists(os.path.join(bib_dir, ent_folder, f"{link_clean}.md")):
                                        found = True
                                        break
                                if not found:
                                    report["missing_markdown_files"].append({
                                        "origen": f"Biblioteca/{rel_dir}/{file}",
                                        "enlace_roto": link
                                    })
                    except Exception as e:
                        report["warnings"].append(f"Error al analizar enlaces en {file}: {str(e)}")
                        
    return report
