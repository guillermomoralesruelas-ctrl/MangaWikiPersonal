import os
import json
from .json_manager import load_json, save_json
from .markdown_generator import clean_filename

PREFIX_MAP = {
    "personaje": "char",
    "evento": "event",
    "lugar": "place",
    "objeto": "obj",
    "organizacion": "org",
    "vehiculo": "vehicle",
    "arma": "weapon",
    "animal": "animal",
    "comida": "food",
    "simbolo": "symbol",
    "escena": "scene"
}

def levenshtein_distance(s1, s2):
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def calculate_similarity(s1, s2):
    s1_norm = s1.lower().strip()
    s2_norm = s2.lower().strip()
    if not s1_norm or not s2_norm:
        return 0.0
    if s1_norm == s2_norm:
        return 100.0
    dist = levenshtein_distance(s1_norm, s2_norm)
    max_len = max(len(s1_norm), len(s2_norm))
    return round((1.0 - (dist / max_len)) * 100, 1)

class EntityManager:
    def __init__(self, project_path):
        self.project_path = project_path
        self.entities_json_path = os.path.join(project_path, "Datos_JSON", "entities.json")
        self.redirects_json_path = os.path.join(project_path, "Datos_JSON", "entity_redirects.json")
        self.history_json_path = os.path.join(project_path, "Datos_JSON", "entity_history.json")
        self.merge_log_json_path = os.path.join(project_path, "Datos_JSON", "entity_merge_log.json")
        
    def load_entities(self):
        return load_json(self.entities_json_path, default_value=[])
        
    def save_entities(self, entities):
        save_json(self.entities_json_path, entities)

    def load_redirects(self):
        return load_json(self.redirects_json_path, default_value={})
        
    def save_redirects(self, redirects):
        save_json(self.redirects_json_path, redirects)
        
    def load_history(self):
        return load_json(self.history_json_path, default_value=[])
        
    def save_history(self, history):
        save_json(self.history_json_path, history)

    def load_merge_log(self):
        return load_json(self.merge_log_json_path, default_value=[])
        
    def save_merge_log(self, merge_log):
        save_json(self.merge_log_json_path, merge_log)

    def log_history(self, entity_id, action, value=""):
        import datetime
        history = self.load_history()
        history.append({
            "entity_id": entity_id,
            "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "accion": action,
            "valor": value
        })
        self.save_history(history)

    def resolve_redirect_id(self, entity_id):
        redirects = self.load_redirects()
        visited = set()
        current = entity_id
        while current in redirects:
            if current in visited:
                break
            visited.add(current)
            current = redirects[current]
        return current
        
    def generate_id(self, entity_type, existing_entities):
        prefix = PREFIX_MAP.get(entity_type.lower(), "obj")
        
        # Find the highest number for this prefix
        max_num = 0
        for ent in existing_entities:
            ent_id = ent.get("id", "")
            if ent_id.startswith(f"{prefix}_"):
                try:
                    num = int(ent_id.split("_")[1])
                    if num > max_num:
                        max_num = num
                except Exception:
                    pass
        return f"{prefix}_{max_num + 1:06d}"

    def get_or_create_entity(self, name, entity_type, page_val=None, asset_val=None):
        entities = self.load_entities()
        name_clean = name.strip()
        
        # Check if entity exists by name or alias
        for ent in entities:
            if ent.get("nombre").strip().lower() == name_clean.lower() or name_clean.lower() in [a.lower() for a in ent.get("alias", [])]:
                # Resolve redirect if merged
                target_id = self.resolve_redirect_id(ent["id"])
                for tent in entities:
                    if tent["id"] == target_id:
                        return tent, False
                return ent, False
                
        # Generate new entity
        new_id = self.generate_id(entity_type, entities)
        new_entity = {
            "id": new_id,
            "tipo": entity_type,
            "nombre": name_clean,
            "alias": [],
            "primera_aparicion": {
                "pagina": page_val if page_val else "Pendiente",
                "asset": asset_val if asset_val else "Pendiente"
            },
            "estado": "activo"
        }
        entities.append(new_entity)
        self.save_entities(entities)
        self.log_history(new_id, "created", name_clean)
        return new_entity, True

    def resolve_to_id(self, name):
        """Resolves a name or alias to its Entity ID, traversing redirects recursively."""
        entities = self.load_entities()
        name_clean = name.strip().lower()
        found_id = None
        for ent in entities:
            if ent.get("nombre").strip().lower() == name_clean or name_clean in [a.lower() for a in ent.get("alias", [])]:
                found_id = ent.get("id")
                break
        if found_id:
            return self.resolve_redirect_id(found_id)
        return None

    def run_auto_migration(self):
        """
        Migrates name-based entities, index_assets, relationships, and timeline
        to the new ID-based model. Re-generates Biblioteca Markdown files.
        """
        print(f"Iniciando migración automática en: {self.project_path}")
        
        # 1. Migrate core lists (personajes, eventos, lugares, objetos, organizaciones) to entities.json
        entities = self.load_entities()
        existing_names = {x["nombre"].strip().lower(): x for x in entities}
        
        json_dir = os.path.join(self.project_path, "Datos_JSON")
        
        def migrate_list(filename, ent_type):
            filepath = os.path.join(json_dir, filename)
            if os.path.exists(filepath):
                try:
                    raw_list = load_json(filepath, default_value=[])
                    for item in raw_list:
                        # Handles both string list and dictionary list
                        name = item.get("nombre") if isinstance(item, dict) else item
                        if not name or not name.strip():
                            continue
                        name_clean = name.strip()
                        resolved_id = self.resolve_to_id(name_clean)
                        if not resolved_id:
                            new_id = self.generate_id(ent_type, entities)
                            new_ent = {
                                "id": new_id,
                                "tipo": ent_type,
                                "nombre": name_clean,
                                "alias": [],
                                "primera_aparicion": {
                                    "pagina": "Pendiente",
                                    "asset": "Pendiente"
                                },
                                "estado": "activo"
                            }
                            entities.append(new_ent)
                            existing_names[name_clean.lower()] = new_ent
                            self.log_history(new_id, "created", name_clean)
                except Exception:
                    pass
                    
        migrate_list("personajes.json", "personaje")
        migrate_list("eventos.json", "evento")
        migrate_list("lugares.json", "lugar")
        migrate_list("objetos.json", "objeto")
        migrate_list("organizaciones.json", "organizacion")
        
        self.save_entities(entities)
        
        # 2. Update Assets index (index_assets.json) to include entity_id
        assets_index_path = os.path.join(self.project_path, "Assets", "index_assets.json")
        assets = load_json(assets_index_path, default_value=[])
        assets_updated = False
        
        for asset in assets:
            if "entity_id" not in asset or not asset["entity_id"]:
                ent_name = asset.get("nombre")
                ent_type = asset.get("tipo", "objeto")
                
                # Check mapping for type mapping
                # Map asset type to entity type
                # e.g., vehiculo -> vehicle, arma -> weapon etc.
                entity_id = self.resolve_to_id(ent_name)
                if not entity_id:
                    # Create the entity on the fly
                    new_ent, _ = self.get_or_create_entity(ent_name, ent_type, f"Pagina_{asset.get('pagina', 1):03d}", asset.get("id"))
                    entity_id = new_ent["id"]
                    # Reload entities cache
                    entities = self.load_entities()
                    existing_names[ent_name.lower()] = new_ent
                    
                asset["entity_id"] = entity_id
                assets_updated = True
                
        if assets_updated:
            save_json(assets_index_path, assets)
            
        # 3. Update Relationships (relaciones.json) to use IDs
        rel_path = os.path.join(json_dir, "relaciones.json")
        relations = load_json(rel_path, default_value=[])
        rel_updated = False
        
        for rel in relations:
            # Check if source_id and target_id are present
            if "source_id" not in rel or not rel["source_id"]:
                ent_a = rel.get("entidad_a")
                if ent_a:
                    sid = self.resolve_to_id(ent_a)
                    if not sid:
                        new_ent, _ = self.get_or_create_entity(ent_a, "personaje")
                        sid = new_ent["id"]
                    rel["source_id"] = sid
                    rel_updated = True
                    
            if "target_id" not in rel or not rel["target_id"]:
                ent_b = rel.get("entidad_b")
                if ent_b:
                    tid = self.resolve_to_id(ent_b)
                    if not tid:
                        new_ent, _ = self.get_or_create_entity(ent_b, "personaje")
                        tid = new_ent["id"]
                    rel["target_id"] = tid
                    rel_updated = True
                    
        if rel_updated:
            save_json(rel_path, relations)
            
        # 4. Update Timeline (timeline.json) to use IDs
        time_path = os.path.join(json_dir, "timeline.json")
        timeline = load_json(time_path, default_value=[])
        time_updated = False
        
        for event in timeline:
            parts = event.get("participantes", [])
            new_parts = []
            for p in parts:
                # If it's not already an ID format (like char_000001)
                if not p.startswith(("char_", "org_", "event_")):
                    pid = self.resolve_to_id(p)
                    if not pid:
                        new_ent, _ = self.get_or_create_entity(p, "personaje")
                        pid = new_ent["id"]
                    new_parts.append(pid)
                    time_updated = True
                else:
                    new_parts.append(p)
            if time_updated:
                event["participantes"] = new_parts
                
        if time_updated:
            save_json(time_path, timeline)
            
        # 5. Re-generate Obsidian sheets in Biblioteca/ to sync Markdown layout with IDs
        self.rebuild_all_markdown_files(entities, assets, relations, timeline)
        
    def rebuild_all_markdown_files(self, entities, assets, relations, timeline):
        from .markdown_generator import generate_entity_markdown, generate_relation_markdown, generate_timeline_markdown
        
        # Build mapping of entity ID -> linked assets
        entity_assets = {}
        for asset in assets:
            eid = asset.get("entity_id")
            if eid:
                if eid not in entity_assets:
                    entity_assets[eid] = []
                entity_assets[eid].append(asset["id"])
                
        # Build mapping of entity ID -> pages appearances (from assets and page scans)
        # Scan page records
        from .json_manager import ProjectJSONManager
        json_mgr = ProjectJSONManager(self.project_path)
        pages = json_mgr.load_pages()
        
        entity_pages = {}
        for p_num, p_info in pages.items():
            # Gather entities present (extracting string name from dictionary if needed)
            p_chars = [x.get("nombre") if isinstance(x, dict) else x for x in p_info.get("personajes", [])]
            p_events = [x.get("nombre") if isinstance(x, dict) else x for x in p_info.get("eventos", [])]
            p_places = [x.get("nombre") if isinstance(x, dict) else x for x in p_info.get("lugares", [])]
            p_objects = [x.get("nombre") if isinstance(x, dict) else x for x in p_info.get("objetos", [])]
            
            entities_present = p_chars + p_events + p_places + p_objects
            for name in entities_present:
                if name:
                    eid = self.resolve_to_id(name)
                    if eid:
                        if eid not in entity_pages:
                            entity_pages[eid] = set()
                        entity_pages[eid].add(p_num)
                    
        # Update first appearances for entities
        for ent in entities:
            eid = ent["id"]
            if ent.get("estado") == "merged":
                self.rewrite_merged_markdown(ent)
                continue
                
            ent_type = ent["tipo"]
            
            # Match folder in Biblioteca
            from .asset_extractor import BIBLIOTECA_MAP
            bib_folder = BIBLIOTECA_MAP.get(ent_type, "Eventos")
            
            pages_list = list(entity_pages.get(eid, set()))
            # Also include pages from assets
            for asset in assets:
                if asset.get("entity_id") == eid:
                    pages_list.append(f"{asset.get('pagina'):03d}")
            pages_list = sorted(list(set(pages_list)))
            
            # Resolve first appearance metadata
            first_p = "Pendiente"
            first_a = "Pendiente"
            if pages_list:
                first_p = f"Pagina_{pages_list[0]}"
                # Find asset on that page
                for asset in assets:
                    if asset.get("entity_id") == eid and f"{asset.get('pagina'):03d}" == pages_list[0]:
                        first_a = asset["id"]
                        break
            
            ent["primera_aparicion"] = {
                "pagina": first_p,
                "asset": first_a
            }
            
            # Recreate markdown file
            extra_sec = {
                "Entity ID": eid,
                "Alias": "\n".join([f"* {a}" for a in ent.get("alias", [])]) if ent.get("alias") else "* Pendiente",
                "Primera Aparición": f"[[{first_p}]]" if first_p != "Pendiente" else "Pendiente",
                "Assets Vinculados": "\n".join([f"* {a}" for a in entity_assets.get(eid, [])]) if entity_assets.get(eid) else "* Pendiente"
            }
            
            generate_entity_markdown(
                self.project_path,
                bib_folder,
                ent["nombre"],
                pages_list,
                entity_assets.get(eid, []),
                extra_sections=extra_sec
            )
            
        # Re-save entities with updated first appearances
        self.save_entities(entities)
        
        # Recreate Relationships md
        for rel in relations:
            generate_relation_markdown(self.project_path, rel)
            
        # Recreate Timeline md
        # First lookup entity names for participants to write human readable links in md
        id_name_map = {x["id"]: x["nombre"] for x in entities}
        for ev in timeline:
            ev_copy = ev.copy()
            # Map participants IDs back to names for the Markdown format, so links match
            ev_copy["participantes"] = [id_name_map.get(p_id, p_id) for p_id in ev.get("participantes", [])]
            generate_timeline_markdown(self.project_path, ev_copy)

    def rewrite_merged_markdown(self, secondary):
        from .markdown_generator import clean_filename
        cleaned_name = clean_filename(secondary["nombre"])
        from .asset_extractor import BIBLIOTECA_MAP
        bib_folder = BIBLIOTECA_MAP.get(secondary["tipo"], "Eventos")
        
        file_path = os.path.join(self.project_path, "Biblioteca", bib_folder, f"{cleaned_name}.md")
        content = f"""# Entidad Fusionada

## Entity ID

{secondary["id"]}

## Fusionada En

[[{clean_filename(self.resolve_redirect_id(secondary["id"]))}]]

## Estado

merged
"""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    def get_possible_duplicates(self):
        """Looks for potential duplicate entities and calculates confidence scores."""
        entities = [e for e in self.load_entities() if e.get("estado") == "activo"]
        duplicates = []
        for i in range(len(entities)):
            for j in range(i + 1, len(entities)):
                e1 = entities[i]
                e2 = entities[j]
                
                # Check similarity between names
                score = calculate_similarity(e1["nombre"], e2["nombre"])
                
                # Also check aliases similarities
                max_score = score
                for a1 in e1.get("alias", []):
                    max_score = max(max_score, calculate_similarity(a1, e2["nombre"]))
                for a2 in e2.get("alias", []):
                    max_score = max(max_score, calculate_similarity(e1["nombre"], a2))
                    
                if max_score >= 80:
                    duplicates.append({
                        "entity_1": e1,
                        "entity_2": e2,
                        "confidence": max_score
                    })
        return sorted(duplicates, key=lambda x: x["confidence"], reverse=True)

    def calculate_health_score(self, entity):
        """Calculates a health score from 0 to 100 based on completeness metrics."""
        if entity.get("estado") == "merged":
            return 100
            
        score = 0
        points = {
            "has_alias": 20,
            "has_assets": 20,
            "has_relations": 20,
            "has_timeline": 20,
            "has_sources": 20
        }
        
        if entity.get("alias"):
            score += points["has_alias"]
            
        eid = entity["id"]
        
        # Check assets
        assets_path = os.path.join(self.project_path, "Assets", "index_assets.json")
        assets = load_json(assets_path, default_value=[])
        has_assets = any(a.get("entity_id") == eid for a in assets)
        if has_assets:
            score += points["has_assets"]
            
        # Check relations
        from .json_manager import ProjectJSONManager
        json_mgr = ProjectJSONManager(self.project_path)
        relations = json_mgr.load_relations()
        has_relations = any(r.get("source_id") == eid or r.get("target_id") == eid for r in relations)
        if has_relations:
            score += points["has_relations"]
            
        # Check timeline
        timeline = json_mgr.load_timeline()
        has_timeline = any(eid in ev.get("participantes", []) for ev in timeline)
        if has_timeline:
            score += points["has_timeline"]
            
        # Check sources
        pages = json_mgr.load_pages()
        has_sources = False
        name_lower = entity["nombre"].lower().strip()
        aliases_lower = [a.lower().strip() for a in entity.get("alias", [])]
        for p_num, p_info in pages.items():
            p_chars = [x.get("nombre") if isinstance(x, dict) else x for x in p_info.get("personajes", [])]
            p_events = [x.get("nombre") if isinstance(x, dict) else x for x in p_info.get("eventos", [])]
            p_places = [x.get("nombre") if isinstance(x, dict) else x for x in p_info.get("lugares", [])]
            p_objects = [x.get("nombre") if isinstance(x, dict) else x for x in p_info.get("objetos", [])]
            ent_names = [x.lower().strip() for x in (p_chars + p_events + p_places + p_objects) if x]
            if name_lower in ent_names or any(al in ent_names for al in aliases_lower):
                has_sources = True
                break
        if has_sources:
            score += points["has_sources"]
            
        return score

    def merge_entities(self, master_id, secondary_id, reason="Duplicado"):
        """Fuses secondary_id into master_id using soft delete."""
        import datetime
        entities = self.load_entities()
        
        master = None
        secondary = None
        for ent in entities:
            if ent["id"] == master_id:
                master = ent
            elif ent["id"] == secondary_id:
                secondary = ent
                
        if not master or not secondary:
            return False, "Una o ambas entidades no existen."
            
        if secondary.get("estado") == "merged":
            return False, "La entidad secundaria ya está fusionada."
            
        # 1. Update entities.json: Soft Delete secondary
        secondary["estado"] = "merged"
        secondary["merged_into"] = master_id
        
        # Merge aliases
        for alias in secondary.get("alias", []):
            if alias.strip().lower() != master["nombre"].strip().lower() and alias.strip().lower() not in [x.lower() for x in master.get("alias", [])]:
                master.setdefault("alias", []).append(alias)
        # Also secondary's main name becomes an alias for master
        if secondary["nombre"].strip().lower() != master["nombre"].strip().lower() and secondary["nombre"].strip().lower() not in [x.lower() for x in master.get("alias", [])]:
            master.setdefault("alias", []).append(secondary["nombre"])
            
        self.save_entities(entities)
        
        # 2. Update redirects mapping
        redirects = self.load_redirects()
        redirects[secondary_id] = master_id
        # Also update any transitively pointing redirects
        for rid, target in list(redirects.items()):
            if target == secondary_id:
                redirects[rid] = master_id
        self.save_redirects(redirects)
        
        # 3. Update references in JSONs and collect lists for rollback
        from .json_manager import ProjectJSONManager
        json_mgr = ProjectJSONManager(self.project_path)
        
        transferred_assets = []
        transferred_relations = []
        transferred_timeline = []
        
        # Assets
        assets_path = os.path.join(self.project_path, "Assets", "index_assets.json")
        assets = load_json(assets_path, default_value=[])
        for asset in assets:
            if asset.get("entity_id") == secondary_id:
                asset["entity_id"] = master_id
                transferred_assets.append(asset["id"])
        save_json(assets_path, assets)
        
        # Relations
        relations = json_mgr.load_relations()
        for rel in relations:
            rel_changed = False
            if rel.get("source_id") == secondary_id:
                rel["source_id"] = master_id
                rel_changed = True
            if rel.get("target_id") == secondary_id:
                rel["target_id"] = master_id
                rel_changed = True
            if rel_changed:
                transferred_relations.append(rel)
        json_mgr.save_relations(relations)
        
        # Timeline
        timeline = json_mgr.load_timeline()
        for ev in timeline:
            parts = ev.get("participantes", [])
            if secondary_id in parts:
                new_parts = [master_id if x == secondary_id else x for x in parts]
                ev["participantes"] = list(set(new_parts))
                transferred_timeline.append(ev.get("num"))
        json_mgr.save_timeline(timeline)
        
        # Paginas.json
        pages = json_mgr.load_pages()
        sec_name = secondary["nombre"].strip()
        mas_name = master["nombre"].strip()
        for p_num, p_info in pages.items():
            for list_key in ["personajes", "eventos", "lugares", "objetos"]:
                if list_key in p_info:
                    new_items = []
                    for x in p_info[list_key]:
                        if isinstance(x, dict):
                            eid = x.get("entity_id")
                            nombre = x.get("nombre")
                            if eid == secondary_id or nombre == sec_name:
                                new_items.append({"entity_id": master_id, "nombre": mas_name})
                            else:
                                new_items.append(x)
                        else:
                            if x == sec_name:
                                new_items.append(mas_name)
                            else:
                                new_items.append(x)
                    
                    # Deduplicate list
                    seen = set()
                    deduped = []
                    for item in new_items:
                        key = item["entity_id"] if isinstance(item, dict) else item
                        if key not in seen:
                            seen.add(key)
                            deduped.append(item)
                    p_info[list_key] = deduped
        json_mgr.save_pages(pages)
        
        # 4. Log the merge
        merge_log = self.load_merge_log()
        merge_log.append({
            "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "master": master_id,
            "merged": secondary_id,
            "motivo": reason,
            "transferred_assets": transferred_assets,
            "transferred_relations": transferred_relations,
            "transferred_timeline": transferred_timeline
        })
        self.save_merge_log(merge_log)
        
        # Log History
        self.log_history(master_id, "merged_absorb", secondary_id)
        self.log_history(secondary_id, "merged_into", master_id)
        
        # 5. Re-generate Obsidian Markdown files
        self.run_auto_migration()
        
        # Rewrite secondary note to redirect layout
        self.rewrite_merged_markdown(secondary)
        
        return True, "Fusión realizada con éxito."

    def restore_entity(self, entity_id):
        """Restores a merged entity back to active state, reversing transfers."""
        entities = self.load_entities()
        secondary = None
        for ent in entities:
            if ent["id"] == entity_id:
                secondary = ent
                break
                
        if not secondary:
            return False, "La entidad no existe."
            
        if secondary.get("estado") != "merged":
            return False, "La entidad no está en estado fusionado."
            
        master_id = secondary.get("merged_into")
        
        # 1. Update entities.json state
        secondary["estado"] = "activo"
        if "merged_into" in secondary:
            del secondary["merged_into"]
            
        # Clean master aliases
        master = None
        if master_id:
            for ent in entities:
                if ent["id"] == master_id:
                    master = ent
                    break
        if master:
            if secondary["nombre"] in master.get("alias", []):
                master["alias"].remove(secondary["nombre"])
            for alias in secondary.get("alias", []):
                if alias in master.get("alias", []):
                    master["alias"].remove(alias)
            
        # 2. Remove redirect
        redirects = self.load_redirects()
        if entity_id in redirects:
            del redirects[entity_id]
        self.save_redirects(redirects)
        
        # 3. Revert transfers using target log
        merge_log = self.load_merge_log()
        target_log = None
        new_log = []
        for log in merge_log:
            if log.get("merged") == entity_id:
                target_log = log
            else:
                new_log.append(log)
        self.save_merge_log(new_log)
        
        if target_log:
            # Restore assets
            trans_assets = target_log.get("transferred_assets", [])
            assets_path = os.path.join(self.project_path, "Assets", "index_assets.json")
            assets = load_json(assets_path, default_value=[])
            for asset in assets:
                if asset.get("id") in trans_assets:
                    asset["entity_id"] = entity_id
            save_json(assets_path, assets)
            
            # Restore relations
            trans_relations = target_log.get("transferred_relations", [])
            from .json_manager import ProjectJSONManager
            json_mgr = ProjectJSONManager(self.project_path)
            relations = json_mgr.load_relations()
            for rel in relations:
                for tr_rel in trans_relations:
                    if rel.get("entidad_a") == tr_rel.get("entidad_a") and rel.get("entidad_b") == tr_rel.get("entidad_b") and rel.get("tipo") == tr_rel.get("tipo"):
                        if tr_rel.get("source_id") == entity_id or tr_rel.get("source_id") == master_id:
                            rel["source_id"] = tr_rel.get("source_id")
                        if tr_rel.get("target_id") == entity_id or tr_rel.get("target_id") == master_id:
                            rel["target_id"] = tr_rel.get("target_id")
            json_mgr.save_relations(relations)
            
            # Restore timeline
            trans_timeline = target_log.get("transferred_timeline", [])
            timeline = json_mgr.load_timeline()
            for ev in timeline:
                if ev.get("num") in trans_timeline:
                    parts = ev.get("participantes", [])
                    if master_id in parts:
                        # Replace master_id with secondary entity_id
                        parts = [entity_id if x == master_id else x for x in parts]
                    else:
                        parts.append(entity_id)
                    ev["participantes"] = list(set(parts))
            json_mgr.save_timeline(timeline)
            
        self.save_entities(entities)
        
        # Log History
        self.log_history(entity_id, "restored", secondary["nombre"])
        if master_id:
            self.log_history(master_id, "merged_restore_rollback", entity_id)
            
        # 4. Re-run migration to restore all notes
        self.run_auto_migration()
        
        return True, "Entidad restaurada con éxito."

    def add_alias(self, entity_id, alias_name):
        alias_clean = alias_name.strip()
        if not alias_clean:
            return False, "El nombre del alias no puede estar vacío."
            
        entities = self.load_entities()
        target = None
        for ent in entities:
            if ent["id"] == entity_id:
                target = ent
            if ent.get("nombre").strip().lower() == alias_clean.lower():
                return False, f"El alias ya está registrado como el nombre principal de la entidad '{ent['nombre']}'."
            if alias_clean.lower() in [a.lower() for a in ent.get("alias", [])]:
                if ent["id"] == entity_id:
                    return False, f"El alias ya está registrado para esta entidad."
                else:
                    return False, f"El alias '{alias_clean}' ya está en uso por la entidad '{ent['nombre']}' ({ent['id']})."
                    
        if not target:
            return False, "La entidad no existe."
            
        target.setdefault("alias", []).append(alias_clean)
        self.save_entities(entities)
        self.log_history(entity_id, "alias_added", alias_clean)
        
        self.run_auto_migration()
        return True, "Alias agregado con éxito."

    def delete_alias(self, entity_id, alias_name):
        alias_clean = alias_name.strip()
        entities = self.load_entities()
        target = None
        for ent in entities:
            if ent["id"] == entity_id:
                target = ent
                break
        if not target:
            return False, "La entidad no existe."
            
        aliases = target.get("alias", [])
        if alias_clean not in aliases:
            found = None
            for a in aliases:
                if a.lower() == alias_clean.lower():
                    found = a
                    break
            if found:
                alias_clean = found
            else:
                return False, "El alias no se encuentra registrado en esta entidad."
                
        target["alias"].remove(alias_clean)
        self.save_entities(entities)
        self.log_history(entity_id, "alias_deleted", alias_clean)
        
        self.run_auto_migration()
        return True, "Alias eliminado con éxito."

    def get_entity_by_id(self, entity_id):
        """Returns the entity with the specified ID or None."""
        entities = self.load_entities()
        for ent in entities:
            if ent["id"] == entity_id:
                return ent
        return None
