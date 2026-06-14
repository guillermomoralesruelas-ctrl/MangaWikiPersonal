import os
import re
import json
from .json_manager import load_json
from .entity_manager import EntityManager, levenshtein_distance

class ChatGPTImporter:
    def __init__(self, project_path):
        self.project_path = project_path
        self.entity_mgr = EntityManager(project_path)
        
    def parse_analysis(self, text_content, expected_page_num):
        """
        Parses text content (Markdown or JSON) and returns a structured dictionary.
        Validates page numbers, bbox coordinates, duplicate asset IDs, and entity mappings.
        """
        raw_text = text_content.strip()
        parsed_data = {}
        is_json = False
        
        # 1. Attempt JSON parsing
        try:
            if (raw_text.startswith('{') and raw_text.endswith('}')) or (raw_text.startswith('[') and raw_text.endswith(']')):
                parsed_data = json.loads(raw_text)
                is_json = True
        except Exception:
            pass
            
        if not is_json:
            # 2. Markdown Parsing via Regex
            parsed_data = self._parse_markdown(raw_text)
            
        # Standardize empty lists and values
        parsed_data.setdefault("pagina", None)
        parsed_data.setdefault("tipo_pagina", "Historia principal")
        parsed_data.setdefault("narracion", "")
        parsed_data.setdefault("descripcion_visual", "")
        parsed_data.setdefault("personajes", [])
        parsed_data.setdefault("eventos", [])
        parsed_data.setdefault("lugares", [])
        parsed_data.setdefault("objetos", [])
        parsed_data.setdefault("relaciones", [])
        parsed_data.setdefault("curiosidades", [])
        parsed_data.setdefault("etiquetas", [])
        parsed_data.setdefault("detecciones_visuales", {"pagina": expected_page_num, "elementos": []})
        
        # Run validations and compile results
        warnings = []
        
        # Page mismatch check (Ajuste Obligatorio #9)
        page_found = parsed_data.get("pagina")
        if page_found is not None:
            try:
                # Convert both to integers to compare safely
                found_int = int(page_found)
                expected_int = int(expected_page_num)
                if found_int != expected_int:
                    warnings.append(f"La página del análisis (Página {found_int}) no coincide con la página actual (Página {expected_int}).")
            except (ValueError, TypeError):
                # Fallback to string comparison
                if str(page_found).strip().zfill(3) != str(expected_page_num).strip().zfill(3):
                    warnings.append(f"La página del análisis ({page_found}) no coincide con la página actual ({expected_page_num}).")
        else:
            warnings.append("No se encontró especificación de número de página en el análisis pegado.")
            
        # Validate missing fields
        if not parsed_data.get("narracion"):
            warnings.append("Falta el campo importante: Narración.")
        if not parsed_data.get("descripcion_visual"):
            warnings.append("Falta el campo importante: Descripción visual.")
            
        # Load asset index for duplicate asset ID validation
        assets_index_path = os.path.join(self.project_path, "Assets", "index_assets.json")
        assets_index = load_json(assets_index_path, default_value=[])
        existing_asset_ids = {a["id"] for a in assets_index}
        
        # Validate Visual Detections
        valid_detections = []
        invalid_detections = []
        
        det_block = parsed_data.get("detecciones_visuales", {})
        # Sometimes it's nested or loaded directly
        if not isinstance(det_block, dict):
            det_block = {"elementos": []}
        elements = det_block.get("elementos", [])
        if not isinstance(elements, list):
            elements = []
            
        for el in elements:
            el_id = el.get("id")
            el_nombre = el.get("nombre", "Sin_Nombre")
            el_tipo = el.get("tipo", "objeto")
            bbox = el.get("bbox")
            bbox_norm = el.get("bbox_normalizado")
            
            is_valid = True
            reasons = []
            
            if not el_id:
                is_valid = False
                reasons.append("Falta ID de elemento")
            elif el_id in existing_asset_ids:
                is_valid = False
                reasons.append(f"El ID de asset '{el_id}' ya existe en el índice")
                
            if not bbox and not bbox_norm:
                is_valid = False
                reasons.append("Falta bbox y bbox_normalizado")
            else:
                if bbox_norm:
                    # Validate floating values [0, 1]
                    try:
                        x = float(bbox_norm.get("x", -1))
                        y = float(bbox_norm.get("y", -1))
                        w = float(bbox_norm.get("ancho", -1))
                        h = float(bbox_norm.get("alto", -1))
                        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 <= w <= 1.0 and 0.0 <= h <= 1.0):
                            is_valid = False
                            reasons.append("bbox_normalizado contiene valores fuera del rango 0.0-1.0")
                    except (ValueError, TypeError):
                        is_valid = False
                        reasons.append("bbox_normalizado contiene coordenadas no numéricas")
                elif bbox:
                    # Validate non-negative integers
                    try:
                        x = int(bbox.get("x", -1))
                        y = int(bbox.get("y", -1))
                        w = int(bbox.get("ancho", -1))
                        h = int(bbox.get("alto", -1))
                        if x < 0 or y < 0 or w <= 0 or h <= 0:
                            is_valid = False
                            reasons.append("bbox absoluto contiene coordenadas negativas o dimensiones nulas")
                    except (ValueError, TypeError):
                        is_valid = False
                        reasons.append("bbox contiene coordenadas no numéricas")
                        
            if is_valid:
                valid_detections.append(el)
            else:
                el_copy = dict(el)
                el_copy["error_reason"] = ", ".join(reasons)
                invalid_detections.append(el_copy)
                warnings.append(f"Detección visual '{el_nombre}' omitida: {', '.join(reasons)}.")
                
        # Resolve entities using Entity Resolution Center (Ajuste Obligatorio #8 & #10)
        entities_summary = {
            "existentes": [],
            "nuevas": [],
            "duplicados_posibles": []
        }
        
        entities_all = self.entity_mgr.load_entities()
        active_entities = [e for e in entities_all if e.get("estado") == "activo"]
        
        # Helper to process entities lists
        def resolve_entity_item(name, type_cat):
            name_clean = name.strip()
            if not name_clean:
                return
            resolved_id = self.entity_mgr.resolve_to_id(name_clean)
            if resolved_id:
                ent = self.entity_mgr.get_entity_by_id(resolved_id)
                entities_summary["existentes"].append({
                    "id": resolved_id,
                    "nombre": ent["nombre"],
                    "tipo": type_cat,
                    "alias_match": name_clean if ent["nombre"].lower() != name_clean.lower() else None
                })
            else:
                # Potential duplicates check (Levenshtein)
                sim_found = []
                for ent in active_entities:
                    if ent["tipo"] == type_cat:
                        dist = levenshtein_distance(name_clean.lower(), ent["nombre"].lower())
                        max_len = max(len(name_clean), len(ent["nombre"]))
                        similarity = (1 - dist / max_len) * 100 if max_len > 0 else 100
                        if similarity >= 70:
                            sim_found.append({"id": ent["id"], "nombre": ent["nombre"], "similarity": round(similarity, 1)})
                            
                item_details = {
                    "nombre": name_clean,
                    "tipo": type_cat
                }
                
                if sim_found:
                    item_details["posibles_duplicados"] = sim_found
                    entities_summary["duplicados_posibles"].append(item_details)
                    warnings.append(f"Entidad nueva '{name_clean}' ({type_cat}) tiene nombres similares: " + 
                                    ", ".join([f"'{s['nombre']}' ({s['similarity']}% sim)" for s in sim_found]))
                else:
                    entities_summary["nuevas"].append(item_details)

        for char in parsed_data["personajes"]:
            # Handle if it was parsed as string or dict
            char_name = char.get("nombre") if isinstance(char, dict) else char
            resolve_entity_item(char_name, "personaje")
            
        for ev in parsed_data["eventos"]:
            ev_name = ev.get("nombre") if isinstance(ev, dict) else ev
            resolve_entity_item(ev_name, "evento")
            
        for pl in parsed_data["lugares"]:
            pl_name = pl.get("nombre") if isinstance(pl, dict) else pl
            resolve_entity_item(pl_name, "lugar")
            
        for obj in parsed_data["objetos"]:
            obj_name = obj.get("nombre") if isinstance(obj, dict) else obj
            resolve_entity_item(obj_name, "objeto")
            
        # Format relations into list of dicts: source -> target: evidence
        formatted_relations = []
        for rel in parsed_data["relaciones"]:
            if isinstance(rel, dict):
                formatted_relations.append(rel)
            else:
                # Parse relation string format: Source -> Target: Evidence
                match = re.match(r'(.*?)\s*->\s*(.*?):\s*(.*)', rel)
                if match:
                    formatted_relations.append({
                        "source": match.group(1).strip(),
                        "target": match.group(2).strip(),
                        "tipo": "interaccion",
                        "evidencia": match.group(3).strip()
                    })
                else:
                    formatted_relations.append({
                        "source": "Desconocido",
                        "target": "Desconocido",
                        "tipo": "interaccion",
                        "evidencia": rel.strip()
                    })

        return {
            "pagina": page_found or expected_page_num,
            "tipo_pagina": parsed_data["tipo_pagina"],
            "narracion": parsed_data["narracion"],
            "descripcion_visual": parsed_data["descripcion_visual"],
            "personajes": parsed_data["personajes"],
            "eventos": parsed_data["eventos"],
            "lugares": parsed_data["lugares"],
            "objetos": parsed_data["objetos"],
            "relaciones": formatted_relations,
            "curiosidades": parsed_data["curiosidades"],
            "etiquetas": parsed_data["etiquetas"],
            "detecciones_validas": valid_detections,
            "detecciones_invalidas": invalid_detections,
            "entities_summary": entities_summary,
            "warnings": warnings,
            "raw_parsed": parsed_data
        }

    def _parse_markdown(self, md_text):
        """Extracts fields from custom structured markdown using regex."""
        parsed = {}
        
        # Page extraction
        page_match = re.search(r'## Página\s+(\d+)', md_text, re.IGNORECASE)
        if page_match:
            parsed["pagina"] = int(page_match.group(1))
            
        # Tipo de página
        tipo_match = re.search(r'### Tipo de página\s*\n\s*(.*?)\s*(?=\n\s*###|\n\s*##|$)', md_text, re.IGNORECASE)
        if tipo_match:
            parsed["tipo_pagina"] = tipo_match.group(1).strip()
            
        # Text block helper
        def extract_text_block(header):
            pattern = rf'### {header}\s*\n\s*([\s\S]*?)\s*(?=\n\s*###|\n\s*##|$)'
            match = re.search(pattern, md_text, re.IGNORECASE)
            return match.group(1).strip() if match else ""
            
        # List helper
        def extract_list_block(header):
            text = extract_text_block(header)
            if not text:
                return []
            lines = text.split('\n')
            items = []
            for l in lines:
                l_strip = l.strip()
                if l_strip.startswith('-') or l_strip.startswith('*'):
                    item_text = re.sub(r'^[-*]\s*', '', l_strip).strip()
                    if item_text:
                        items.append(item_text)
            return items

        parsed["narracion"] = extract_text_block("Narración")
        parsed["descripcion_visual"] = extract_text_block("Descripción visual")
        
        parsed["personajes"] = extract_list_block("Personajes presentes")
        parsed["eventos"] = extract_list_block("Eventos importantes")
        parsed["lugares"] = extract_list_block("Lugares")
        parsed["objetos"] = extract_list_block("Objetos importantes")
        parsed["relaciones"] = extract_list_block("Relaciones detectadas")
        parsed["curiosidades"] = extract_list_block("Curiosidades")
        
        # Tags extraction (look for #tag)
        tags_block = extract_text_block("Etiquetas")
        parsed["etiquetas"] = [t.strip() for t in tags_block.split() if t.strip().startswith('#')]
        if not parsed["etiquetas"]:
            # Fallback scan tags in whole document
            parsed["etiquetas"] = [t for t in re.findall(r'#\w+', md_text)]
            
        # Fenced JSON block parsing for detections
        json_blocks = re.findall(r'```json\s*\n\s*([\s\S]*?)\s*\n\s*```', md_text, re.IGNORECASE)
        detections = {"elementos": []}
        for block in json_blocks:
            try:
                block_data = json.loads(block)
                # Check if it has elementos
                if isinstance(block_data, dict):
                    if "elementos" in block_data:
                        detections["elementos"].extend(block_data["elementos"])
                    elif "pagina" in block_data:
                        # it's a direct detection page wrapper
                        detections = block_data
                elif isinstance(block_data, list):
                    detections["elementos"].extend(block_data)
            except Exception:
                pass
        parsed["detecciones_visuales"] = detections
        
        return parsed
