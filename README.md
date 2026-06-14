# MangaWiki Personal (Knowledge Base & Master Entity System)

MangaWiki Personal es una herramienta web local, ligera y de alto rendimiento diseñada en Python/Flask para organizar tomos y capítulos de Manga en una **Wiki Personal y Base de Conocimiento Visual estructurada**, compatible al 100% con **Obsidian**.

---

## 🎯 PROPÓSITO DEL PROYECTO
El objetivo es transformar carpetas sueltas de imágenes escaneadas de Manga en una verdadera base de conocimiento documental y visual. 

**Este proyecto está especialmente diseñado para co-programar e interactuar con Inteligencias Artificiales (como ChatGPT):**
*   Una IA externa (como ChatGPT) actúa como el motor de análisis y visión analizando las páginas, detectando elementos visuales (personajes, objetos, diálogos) y proveyendo un JSON de coordenadas (`bbox`).
*   La aplicación web procesa las coordenadas, realiza los recortes, actualiza el índice y organiza la bóveda de Obsidian (`Biblioteca/` y `Assets/`).
*   La aplicación cuenta con un **Master Entity System** para centralizar personajes, lugares, eventos, etc., bajo IDs permanentes inmutables, resolviendo de forma transparente alias y fusiones de duplicados con total reversibilidad.

---

## 🛠️ TECNOLOGÍAS UTILIZADAS
1.  **Core Backend:** Flask (Python 3.8+).
2.  **Procesamiento de PDF:** PyMuPDF (`fitz`) para conversión ligera de PDF a PNG y Pillow (`PIL`) para recortes manuales por coordenadas.
3.  **Bases de Datos (Sin SQL):** Archivos planos JSON estructurados y fichas Obsidian en Markdown (`.md`).
4.  **Frontend:** HTML5, CSS vanilla con diseño premium Glassmorphism (modo oscuro) y JavaScript reactivo del lado del cliente.

---

## 📁 ESTRUCTURA COMPLETA DEL PROYECTO (VAULT DE OBSIDIAN)
Cuando creas un proyecto, se genera la siguiente estructura de directorios bajo `MangaWikiPersonal/Proyectos/[Nombre_Proyecto]/`:

```text
MangaWiki_Personal/
├── 00_Index/
│   └── Index.md                      # Índice maestro con enlaces a toda la biblioteca
│
├── Capitulos/                        # Carpeta libre para organizar capítulos
│
├── Paginas/
│   ├── Pagina_001.md                 # Nota de página (Texto, Personajes, Eventos, etc.)
│   └── ...
│
├── Imagenes/
│   ├── pagina_001.png                # Render de página del PDF original
│   └── ...
│
├── PDF_Original/
│   └── [original].pdf                # Respaldo del PDF original cargado
│
├── Datos_JSON/
│   ├── proyecto.json                 # Metadatos del manga
│   ├── paginas.json                  # Datos recopilados por página
│   ├── entities.json                 # [MAESTRO] Registro central de entidades e IDs
│   ├── entity_redirects.json         # [MAESTRO] Mapeo de IDs fusionados/redirigidos
│   ├── entity_history.json           # [MAESTRO] Bitácora histórica de cambios en entidades
│   ├── entity_merge_log.json         # [MAESTRO] Respaldo de fusiones y assets reasignados
│   ├── relaciones.json               # Relaciones mapeadas por IDs
│   └── timeline.json                 # Hitos cronológicos con IDs de participantes
│
├── Assets/                           # ÚNICAMENTE ARCHIVOS DE IMÁGENES RECORTADAS
│   ├── index_assets.json             # Registro de metadatos de recortes
│   ├── Personajes/                   # Imágenes PNG de recortes de personajes
│   ├── Objetos/                      # Imágenes PNG de recortes de objetos
│   ├── Lugares/                      # Imágenes PNG de recortes de lugares
│   └── ... (15 subcarpetas de tipos de recortes)
│
└── Biblioteca/                       # NOTAS MARKDOWN CENTRALIZADAS (WIKI)
    ├── Personajes/                   # Notas Markdown de Personajes (ID, Alias, Visuales, Relaciones...)
    ├── Eventos/                      # Notas de Eventos (Hitos, consecuencias)
    ├── Lugares/                      # Notas de Lugares
    ├── Objetos/                      # Notas de Objetos
    ├── Organizaciones/               # Notas de Organizaciones / Grupos
    ├── Relaciones/                   # Enlaces Obsidian detallando relaciones
    └── Timeline/                     # Notas Markdown de los acontecimientos cronológicos
```

---

## 📄 ESQUEMAS JSON DE PERSISTENCIA (Para Guía de la IA)

### 1. Registro de Entidades Maestras (`entities.json`)
```json
[
  {
    "id": "char_000001",
    "tipo": "personaje",
    "nombre": "Monkey D. Luffy",
    "alias": ["Luffy", "Sombrero de Paja", "Mugiwara"],
    "primera_aparicion": {
      "pagina": "Pagina_001",
      "asset": "p001_obj_001"
    },
    "estado": "activo"
  }
]
```

### 2. Mapeo de Redirecciones (`entity_redirects.json`)
Soporta resolución recursiva. Si una entidad se fusiona en otra, se guarda su redirección aquí:
```json
{
  "char_000028": "char_000001"
}
```

### 3. Historial de Cambios (`entity_history.json`)
```json
[
  {
    "entity_id": "char_000001",
    "fecha": "2026-06-14 00:30:00",
    "accion": "alias_added",
    "valor": "Mugiwara"
  }
]
```

### 4. Relaciones Basadas en IDs (`relaciones.json`)
```json
[
  {
    "source_id": "char_000001",
    "target_id": "char_000002",
    "entidad_a": "Monkey D. Luffy",
    "entidad_b": "Shanks",
    "tipo": "mentor",
    "evidencia": "[[Pagina_005]]",
    "notas": "Shanks entrega su sombrero a Luffy."
  }
]
```

---

## 🤖 GUÍA DE INTEGRACIÓN PARA CHATGPT (IA EXTERNA)
Para alimentar la galería visual y clasificar assets, ChatGPT debe analizar la imagen y generar un JSON con coordenadas.

### Formato Esperado de Entrada (`detecciones.json`):
```json
[
  {
    "pagina": 1,
    "elementos": [
      {
        "id": "p001_obj_001",
        "tipo": "personaje",
        "nombre": "Monkey D. Luffy",
        "descripcion": "Luffy sonriendo.",
        "bbox": {
          "x": 100,
          "y": 150,
          "ancho": 250,
          "alto": 300
        },
        "tags": ["luffy", "protagonista"]
      }
    ]
  }
]
```

### Reglas de Coordenadas:
1.  **`bbox` (Píxeles):** Coordenadas directas referenciadas a la imagen PNG generada.
2.  **`bbox_normalizado` (Porcentajes):** Opcional, de `0.0` a `1.0`. La aplicación las escalará automáticamente multiplicándolas por las dimensiones reales de la imagen:
    ```json
    "bbox_normalizado": {
      "x": 0.1,
      "y": 0.15,
      "ancho": 0.25,
      "alto": 0.3
    }
    ```
3.  **Evitar duplicación:** La app verifica el `"id"` antes de recortar. Si ya existe en `index_assets.json`, lo saltará de forma segura.

---

## 🎛️ RESOLUTION CENTER, SOFT DELETE Y RESTAURACIÓN

### Fusión (Merge) de Entidades:
Cuando el usuario decide fusionar un duplicado (ej. `char_000028` "Luffy" es absorbido por `char_000001` "Monkey D. Luffy"):
1.  El estado de `char_000028` cambia a `"merged"` y apunta a `"merged_into": "char_000001"`.
2.  Se registra la redirección en `entity_redirects.json`.
3.  Se reasignan todos los assets, relaciones y timeline vinculados al ID principal.
4.  La nota de Obsidian del secundario se reescribe como una redirección informativa:
    ```markdown
    # Entidad Fusionada
    ## Entity ID: char_000028
    ## Fusionada En: [[Monkey_D._Luffy]]
    ```

### Restauración (Rollback):
Al restaurar, el sistema lee la bitácora en `entity_merge_log.json`, reactiva el ID secundario a `"activo"`, elimina la redirección, separa los alias y devuelve la propiedad de sus relaciones, assets y timeline correspondientes de forma 100% reversible.

---

## 🏥 SISTEMA DE SALUD (Health Score) & DIAGNÓSTICO
Cada entidad activa recibe un puntaje de completitud de 0 a 100 sumando 20 puntos por cada criterio:
*   Tiene alias.
*   Tiene assets.
*   Tiene relaciones.
*   Tiene timeline.
*   Tiene fuentes.

El **Consistómetro** audita la integridad referencial listando alias ambiguos, IDs duplicados, redirecciones rotas, assets sin entidad y enlaces rotos a páginas inexistentes.

---

## ⚙️ INSTALACIÓN Y EJECUCIÓN

1.  Asegúrate de tener instalado Python 3.8 o superior.
2.  Instala las dependencias necesarias:
    ```bash
    pip install -r requirements.txt
    ```
3.  Ejecuta la suite de pruebas para verificar el funcionamiento:
    ```bash
    python test_app.py
    ```
4.  Inicia la aplicación:
    ```bash
    python app.py
    ```
5.  Accede a la interfaz web en: **`http://localhost:5000`**
