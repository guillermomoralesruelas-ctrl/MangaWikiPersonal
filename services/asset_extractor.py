import os
import json
import re
from PIL import Image
from .markdown_generator import clean_filename, generate_entity_markdown

TYPE_MAP = {
    "personaje": "Personajes",
    "objeto": "Objetos",
    "lugar": "Lugares",
    "escena": "Escenas",
    "expresion": "Expresiones",
    "dialogo": "Dialogos",
    "simbolo": "Simbolos",
    "grupo": "Grupos",
    "vehiculo": "Vehiculos",
    "arma": "Armas",
    "vestimenta": "Vestimenta",
    "comida": "Comida",
    "animal": "Animales",
    "efecto_visual": "Efectos_Visuales",
    "sin_clasificar": "Sin_Clasificar"
}

# Maps the 15 asset types to the primary Biblioteca folders
BIBLIOTECA_MAP = {
    "personaje": "Personajes",
    "animal": "Personajes",
    "grupo": "Organizaciones",
    "objeto": "Objetos",
    "vehiculo": "Objetos",
    "arma": "Objetos",
    "vestimenta": "Objetos",
    "comida": "Objetos",
    "simbolo": "Objetos",
    "lugar": "Lugares",
    "escena": "Eventos",
    "expresion": "Eventos",
    "dialogo": "Eventos",
    "efecto_visual": "Eventos",
    "sin_clasificar": "Eventos"
}

def sanitize_name(name):
    sanitized = re.sub(r'[^a-zA-Z0-9]', '_', name)
    while "__" in sanitized:
        sanitized = sanitized.replace("__", "_")
    return sanitized.strip('_')

def process_detections(project_path, detections_data):
    """
    Processes a list or dict of detections, crops assets, maps folders, 
    registers metadata in index_assets.json, and generates Obsidian sheets in the Biblioteca folder.
    """
    pages_list = []
    if isinstance(detections_data, dict):
        pages_list = [detections_data]
    elif isinstance(detections_data, list):
        pages_list = detections_data
    else:
        raise ValueError("El formato de las detecciones debe ser un objeto JSON o una lista de objetos.")
        
    assets_dir = os.path.join(project_path, "Assets")
    os.makedirs(assets_dir, exist_ok=True)
    
    # Create type directories in Assets
    for folder in TYPE_MAP.values():
        os.makedirs(os.path.join(assets_dir, folder), exist_ok=True)
        
    index_path = os.path.join(assets_dir, "index_assets.json")
    
    # Load current asset index
    if os.path.exists(index_path):
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                asset_index = json.load(f)
        except Exception:
            asset_index = []
    else:
        asset_index = []
        
    existing_ids = {item["id"]: item for item in asset_index}
    
    processed = 0
    skipped = 0
    warnings = []
    
    for page_data in pages_list:
        page_num = page_data.get("pagina")
        if page_num is None:
            warnings.append("Elemento sin número de página especificado, omitiendo.")
            continue
            
        elements = page_data.get("elementos", [])
        page_str = f"{int(page_num):03d}"
        image_path = os.path.join(project_path, "Imagenes", f"pagina_{page_str}.png")
        
        if not os.path.exists(image_path):
            warnings.append(f"No se encontró la imagen para la página {page_str} (ruta: {image_path}).")
            continue
            
        try:
            img = Image.open(image_path)
            img_width, img_height = img.size
        except Exception as e:
            warnings.append(f"Error al abrir la imagen de la página {page_str}: {str(e)}")
            continue
            
        for elem in elements:
            elem_id = elem.get("id")
            elem_tipo = elem.get("tipo", "sin_clasificar").lower()
            elem_nombre = elem.get("nombre", "Sin_Nombre")
            elem_tags = elem.get("tags", [])
            elem_desc = elem.get("descripcion", "")
            
            if not elem_id:
                warnings.append(f"Elemento sin ID en la página {page_num}, omitiendo.")
                continue
                
            if elem_id in existing_ids:
                skipped += 1
                warnings.append(f"El ID '{elem_id}' ya existe en el índice de assets. Se omitió para evitar duplicar.")
                continue
                
            folder_name = TYPE_MAP.get(elem_tipo, "Sin_Clasificar")
            dest_folder = os.path.join(assets_dir, folder_name)
            
            bbox = elem.get("bbox")
            bbox_norm = elem.get("bbox_normalizado")
            
            x, y, w, h = 0, 0, 0, 0
            
            if bbox:
                x = int(bbox.get("x", 0))
                y = int(bbox.get("y", 0))
                w = int(bbox.get("ancho", 0))
                h = int(bbox.get("alto", 0))
            elif bbox_norm:
                x = int(float(bbox_norm.get("x", 0)) * img_width)
                y = int(float(bbox_norm.get("y", 0)) * img_height)
                w = int(float(bbox_norm.get("ancho", 0)) * img_width)
                h = int(float(bbox_norm.get("alto", 0)) * img_height)
            else:
                warnings.append(f"El elemento '{elem_id}' no contiene información de bbox o bbox_normalizado.")
                continue
                
            left = max(0, x)
            top = max(0, y)
            right = min(img_width, x + w)
            bottom = min(img_height, y + h)
            
            if (right - left) <= 0 or (bottom - top) <= 0:
                warnings.append(f"El recorte del elemento '{elem_id}' tiene dimensiones inválidas o está fuera de los límites.")
                continue
                
            try:
                crop_area = (left, top, right, bottom)
                cropped_img = img.crop(crop_area)
                
                sanitized_elem_name = sanitize_name(elem_nombre)
                file_name = f"{elem_id}_{sanitized_elem_name}.png"
                dest_image_path = os.path.join(dest_folder, file_name)
                
                cropped_img.save(dest_image_path)
            except Exception as e:
                warnings.append(f"Error al realizar el recorte del elemento '{elem_id}': {str(e)}")
                continue
                
            # Add to index mapping
            relative_filepath = f"Assets/{folder_name}/{file_name}"
            new_asset = {
                "id": elem_id,
                "pagina": int(page_num),
                "archivo": relative_filepath,
                "tipo": elem_tipo,
                "nombre": elem_nombre,
                "tags": elem_tags,
                "descripcion": elem_desc
            }
            asset_index.append(new_asset)
            existing_ids[elem_id] = new_asset
            processed += 1
            
            # Recalculate appearances and visual assets for the entity profile in Biblioteca
            bib_folder = BIBLIOTECA_MAP.get(elem_tipo, "Eventos")
            
            # Find all pages and all asset IDs that refer to this entity name
            entity_pages = set()
            entity_assets = []
            
            for asset in asset_index:
                if asset["nombre"].strip().lower() == elem_nombre.strip().lower():
                    entity_pages.add(f"{asset['pagina']:03d}")
                    entity_assets.append(asset["id"])
                    
            try:
                generate_entity_markdown(
                    project_path,
                    bib_folder,
                    elem_nombre,
                    list(entity_pages),
                    entity_assets
                )
            except Exception as e:
                warnings.append(f"Error al escribir la ficha Markdown en Biblioteca para '{elem_nombre}': {str(e)}")
            
    # Save updated index back to JSON
    try:
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(asset_index, f, ensure_ascii=False, indent=4)
    except Exception as e:
        warnings.append(f"Error al guardar el índice index_assets.json: {str(e)}")
        
    return {
        "processed": processed,
        "skipped": skipped,
        "warnings": warnings
    }
