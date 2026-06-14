import os

def clean_filename(name):
    # Standardize string for Obsidian files/links (replace spaces with underscores, keep letters/numbers)
    cleaned = name.strip().replace(" ", "_")
    # Clean up multiple underscores
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned

def generate_page_markdown(project_path, page_data):
    """
    Generates or overwrites a page Markdown note.
    """
    page_num = page_data.get("num_pagina")
    page_str = f"{page_num:03d}" if isinstance(page_num, int) else page_num
    
    file_path = os.path.join(project_path, "Paginas", f"Pagina_{page_str}.md")
    
    def format_list(items, is_link=False, link_dir=None):
        if not items:
            return "* Pendiente."
        lines = []
        for item in items:
            name = item.get("nombre") if isinstance(item, dict) else item
            if not name or not name.strip():
                continue
            if is_link:
                link_name = clean_filename(name)
                # If a specific directory in Biblioteca is used
                prefix = f"Biblioteca/{link_dir}/" if link_dir else ""
                lines.append(f"* [[{link_name}]]")
            else:
                lines.append(f"* {name.strip()}")
        return "\n".join(lines) if lines else "* Pendiente."

    def format_text(text):
        t = text.strip() if text else ""
        return t if t else "Pendiente."

    content = f"""# Página {page_str}

## Imagen

![[pagina_{page_str}.png]]

## Texto de la página

{format_text(page_data.get('texto'))}

## Narración de la escena

{format_text(page_data.get('narracion'))}

## Personajes presentes

{format_list(page_data.get('personajes', []), is_link=True, link_dir="Personajes")}

## Descripción visual

{format_text(page_data.get('descripcion_visual'))}

## Eventos importantes

{format_list(page_data.get('eventos', []), is_link=True, link_dir="Eventos")}

## Lugares

{format_list(page_data.get('lugares', []), is_link=True, link_dir="Lugares")}

## Objetos importantes

{format_list(page_data.get('objetos', []), is_link=True, link_dir="Objetos")}

## Curiosidades

{format_list(page_data.get('curiosidades', []))}

## Relaciones detectadas

{format_list(page_data.get('relaciones', []))}

## Notas personales

{format_text(page_data.get('notas'))}

## Etiquetas

{" ".join(page_data.get('etiquetas', ['#pagina', '#manga', '#pendiente']))}
"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

def parse_md_sections(file_path):
    sections = {}
    if not os.path.exists(file_path):
        return sections
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        current_header = None
        current_content = []
        
        for line in lines:
            if line.startswith("# "):
                continue
            elif line.startswith("## "):
                if current_header:
                    sections[current_header] = "".join(current_content).strip()
                current_header = line.replace("## ", "").strip()
                current_content = []
            else:
                if current_header:
                    current_content.append(line)
                    
        if current_header:
            sections[current_header] = "".join(current_content).strip()
    except Exception:
        pass
    return sections

def generate_entity_markdown(project_path, folder_name, name, pages_list, assets_list=None, extra_sections=None):
    """
    Generates or updates a Markdown note inside Biblioteca/[folder_name]/[name].md
    Saves Fuentes and Apariciones Visuales automatically.
    """
    cleaned_name = clean_filename(name)
    display_name = name.strip()
    file_path = os.path.join(project_path, "Biblioteca", folder_name, f"{cleaned_name}.md")
    
    # Parse existing content to preserve fields edited by user in Obsidian
    existing = parse_md_sections(file_path)
    
    # Standard text sections based on type
    desc = existing.get("Descripción general") or existing.get("Descripción") or "Pendiente."
    notes = existing.get("Notas personales") or existing.get("Notas") or "Pendiente."
    
    # Merge appearances (sources)
    fuentes_lines = []
    for p_num in sorted(pages_list):
        fuentes_lines.append(f"* [[Pagina_{p_num}]]")
    
    if assets_list:
        for asset_id in sorted(assets_list):
            fuentes_lines.append(f"* [[{clean_filename(asset_id)}]]")
            
    fuentes_str = "\n".join(fuentes_lines) if fuentes_lines else "* Pendiente."
    
    # Parse and merge Visual Appearances
    visual_lines = []
    # Read existing visual embeds from markdown
    if "Apariciones Visuales" in existing:
        for line in existing["Apariciones Visuales"].split("\n"):
            if line.strip().startswith("![[") and line.strip().endswith("]]"):
                visual_lines.append(line.strip())
                
    # Add new ones
    if assets_list:
        # We need the filename of the asset. The asset_id might be "p001_obj_001" and we want "p001_obj_001_Gold_Roger.png"
        # Since Obsidian will look inside subfolders, we can search in index_assets.json or write a wild reference.
        # But if we know the actual filenames, we link them. Let's make sure we find them.
        assets_index_path = os.path.join(project_path, "Assets", "index_assets.json")
        if os.path.exists(assets_index_path):
            try:
                with open(assets_index_path, 'r', encoding='utf-8') as f:
                    assets_meta = json.load(f)
                id_map = {x["id"]: os.path.basename(x["archivo"]) for x in assets_meta}
                for asset_id in assets_list:
                    filename = id_map.get(asset_id)
                    if filename:
                        embed = f"![[{filename}]]"
                        if embed not in visual_lines:
                            visual_lines.append(embed)
            except Exception:
                pass
                
    visual_str = "\n\n".join(visual_lines) if visual_lines else "Pendiente."

    # Assemble sections
    content = f"""# {display_name}

## Descripción general

{desc}

## Fuentes

{fuentes_str}

## Apariciones Visuales

{visual_str}
"""

    # Add entity specific sections
    if folder_name == "Personajes":
        events = existing.get("Eventos relacionados") or "Pendiente."
        relations = existing.get("Relaciones") or "Pendiente."
        content += f"""
## Eventos relacionados

{events}

## Relaciones

{relations}
"""
    if extra_sections:
        for sec_name, def_val in extra_sections.items():
            val = existing.get(sec_name) or def_val
            content += f"\n## {sec_name}\n\n{val}\n"

    # Add standard footer notes
    content += f"""
## Notas personales

{notes}
"""

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

def generate_character_markdown(project_path, name, pages_list, assets_list=None):
    generate_entity_markdown(project_path, "Personajes", name, pages_list, assets_list)

def generate_relation_markdown(project_path, rel):
    """
    Generates/updates a relationship note in Biblioteca/Relaciones/EntidadA_EntidadB.md
    """
    ent_a = rel.get("entidad_a")
    ent_b = rel.get("entidad_b")
    rel_type = rel.get("tipo", "Pendiente")
    evidence = rel.get("evidencia", "Pendiente")
    notes = rel.get("notas", "Pendiente")
    
    clean_a = clean_filename(ent_a)
    clean_b = clean_filename(ent_b)
    file_path = os.path.join(project_path, "Biblioteca", "Relaciones", f"{clean_a}_{clean_b}.md")
    
    # Load existing to preserve custom notes
    existing = parse_md_sections(file_path)
    notes_val = existing.get("Notas") or notes
    if not notes_val:
        notes_val = "Pendiente"
        
    content = f"""# Relación

## Entidad A

[[{clean_a}]]

## Entidad B

[[{clean_b}]]

## Tipo

{rel_type}

## Evidencia

{evidence}

## Notas

{notes_val}
"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

def generate_timeline_markdown(project_path, ev):
    """
    Generates/updates a timeline note in Biblioteca/Timeline/0001_Nombre_Acontecimiento.md
    """
    num = ev.get("num", 1)
    name = ev.get("nombre")
    first_app = ev.get("primera_aparicion", "Pendiente")
    participants = ev.get("participantes", [])
    desc = ev.get("descripcion", "Pendiente")
    conseq = ev.get("consecuencias", "Pendiente")
    
    clean_name = clean_filename(name)
    file_name = f"{num:04d}_{clean_name}.md"
    file_path = os.path.join(project_path, "Biblioteca", "Timeline", file_name)
    
    existing = parse_md_sections(file_path)
    desc_val = existing.get("Descripción") or desc
    conseq_val = existing.get("Consecuencias") or conseq
    
    parts_str = "\n".join([f"* [[{clean_filename(p)}]]" for p in participants]) if participants else "* Pendiente"
    
    content = f"""# Evento

## Nombre

{name}

## Primera aparición

{first_app}

## Participantes

{parts_str}

## Descripción

{desc_val}

## Consecuencias

{conseq_val}
"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

def generate_index_markdown(project_path, project_name, total_pages, characters, events, places, objects, orgs=None):
    """
    Generates or updates 00_Index/Index.md with project overview.
    """
    file_path = os.path.join(project_path, "00_Index", "Index.md")
    
    page_links = []
    for i in range(1, total_pages + 1):
        page_links.append(f"* [[Pagina_{i:03d}]]")
    page_links_str = "\n".join(page_links)

    def format_entity_links(items):
        if not items:
            return "* Ninguno detectado."
        lines = []
        for item in sorted(items):
            # Item can be string or dict (e.g. {"nombre": "Gold Roger", "fuentes": [...]})
            name = item.get("nombre") if isinstance(item, dict) else item
            if not name or not name.strip():
                continue
            cleaned = clean_filename(name)
            lines.append(f"* [[{cleaned}]]")
        return "\n".join(lines) if lines else "* Ninguno detectado."

    content = f"""# {project_name}

**Total de páginas:** {total_pages}

## Acceso a páginas

{page_links_str}

## Lista de personajes

{format_entity_links(characters)}

## Lista de eventos

{format_entity_links(events)}

## Lista de lugares

{format_entity_links(places)}

## Lista de objetos

{format_entity_links(objects)}

## Lista de organizaciones

{format_entity_links(orgs if orgs else [])}
"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
