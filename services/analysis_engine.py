import os
import re
import json
import datetime
from .json_manager import load_json, save_json
from .entity_manager import EntityManager
from .markdown_generator import clean_filename

# Configurable thresholds (Ajuste 2)
MIN_COAPPEARANCES = 2
IMPORTANT_CHARACTER_MIN_APPEARANCES = 5
LOW_HEALTH_THRESHOLD = 40
MEDIUM_HEALTH_THRESHOLD = 70

class AnalysisEngine:
    def __init__(self, project_path):
        self.project_path = project_path
        self.entity_mgr = EntityManager(project_path)
        
    def run_full_analysis(self):
        """Runs the 7 knowledge analysis engines and returns a structured report."""
        entities = self.entity_mgr.load_entities()
        active_entities = [e for e in entities if e.get("estado") == "activo"]
        
        # Load indexes
        assets_path = os.path.join(self.project_path, "Assets", "index_assets.json")
        assets = load_json(assets_path, default_value=[])
        
        from .json_manager import ProjectJSONManager
        json_mgr = ProjectJSONManager(self.project_path)
        pages = json_mgr.load_pages()
        relations = json_mgr.load_relations()
        timeline = json_mgr.load_timeline()
        
        # Helper data structures
        entity_ids = {e["id"] for e in active_entities}
        entity_name_map = {e["nombre"]: e for e in active_entities}
        
        # Count stats per entity ID
        asset_counts = {}
        for a in assets:
            ae_id = a.get("entity_id")
            if ae_id:
                resolved_id = self.entity_mgr.resolve_redirect_id(ae_id)
                asset_counts[resolved_id] = asset_counts.get(resolved_id, 0) + 1
                
        relation_counts = {}
        for r in relations:
            sid = r.get("source_id")
            tid = r.get("target_id")
            if sid:
                resolved_sid = self.entity_mgr.resolve_redirect_id(sid)
                relation_counts[resolved_sid] = relation_counts.get(resolved_sid, 0) + 1
            if tid:
                resolved_tid = self.entity_mgr.resolve_redirect_id(tid)
                relation_counts[resolved_tid] = relation_counts.get(resolved_tid, 0) + 1
                
        # Count appearances of entities in paginas.json
        appearance_counts = {}
        page_appearances = {} # char_name -> set of page nums
        for p_num, p_info in pages.items():
            p_chars = [x.get("nombre") if isinstance(x, dict) else x for x in p_info.get("personajes", [])]
            p_events = [x.get("nombre") if isinstance(x, dict) else x for x in p_info.get("eventos", [])]
            p_places = [x.get("nombre") if isinstance(x, dict) else x for x in p_info.get("lugares", [])]
            p_objects = [x.get("nombre") if isinstance(x, dict) else x for x in p_info.get("objetos", [])]
            
            all_names = p_chars + p_events + p_places + p_objects
            for name in all_names:
                if name:
                    resolved_id = self.entity_mgr.resolve_to_id(name)
                    if resolved_id:
                        appearance_counts[resolved_id] = appearance_counts.get(resolved_id, 0) + 1
                        
            # Track page appearances specifically for characters
            for char_name in p_chars:
                if char_name:
                    resolved_id = self.entity_mgr.resolve_to_id(char_name)
                    if resolved_id:
                        if resolved_id not in page_appearances:
                            page_appearances[resolved_id] = set()
                        page_appearances[resolved_id].add(p_num)

        timeline_counts = {}
        for ev in timeline:
            for part in ev.get("participantes", []):
                resolved_part = self.entity_mgr.resolve_redirect_id(part)
                timeline_counts[resolved_part] = timeline_counts.get(resolved_part, 0) + 1

        # ANALYSIS 1: Entities without enough info
        low_info_entities = []
        critical_entities = []
        for ent in active_entities:
            eid = ent["id"]
            alias_cnt = len(ent.get("alias", []))
            asset_cnt = asset_counts.get(eid, 0)
            rel_cnt = relation_counts.get(eid, 0)
            time_cnt = timeline_counts.get(eid, 0)
            app_cnt = appearance_counts.get(eid, 0)
            
            health = self.entity_mgr.calculate_health_score(ent)
            
            # Critical check (Ajuste 6): many appearances but low health score
            is_critical = False
            priority = "Baja"
            recommendation = "N/A"
            
            if app_cnt >= IMPORTANT_CHARACTER_MIN_APPEARANCES and health < MEDIUM_HEALTH_THRESHOLD:
                is_critical = True
                priority = "Alta"
                recommendation = f"Ficha crítica con {app_cnt} apariciones. Requiere alias, recortes visuales o relaciones."
            elif health < LOW_HEALTH_THRESHOLD:
                priority = "Alta"
                recommendation = "Información extremadamente pobre. Registrar alias o assets visuales."
            elif health < MEDIUM_HEALTH_THRESHOLD:
                priority = "Media"
                recommendation = "Falta documentación complementaria."
                
            if health < MEDIUM_HEALTH_THRESHOLD:
                info_item = {
                    "id": eid,
                    "nombre": ent["nombre"],
                    "tipo": ent["tipo"],
                    "health_score": health,
                    "prioridad": priority,
                    "recomendacion": recommendation,
                    "is_critical": is_critical
                }
                low_info_entities.append(info_item)
                if is_critical:
                    critical_entities.append(info_item)

        # ANALYSIS 2: Important characters incomplete
        important_chars_incomplete = []
        for ent in active_entities:
            if ent["tipo"] == "personaje":
                eid = ent["id"]
                app_cnt = appearance_counts.get(eid, 0)
                asset_cnt = asset_counts.get(eid, 0)
                rel_cnt = relation_counts.get(eid, 0)
                
                if app_cnt >= IMPORTANT_CHARACTER_MIN_APPEARANCES and rel_cnt == 0:
                    important_chars_incomplete.append({
                        "id": eid,
                        "nombre": ent["nombre"],
                        "apariciones": app_cnt,
                        "assets": asset_cnt,
                        "alerta": "Personaje importante sin ninguna relación social registrada."
                    })

        # ANALYSIS 3: Orphan events
        orphan_events = []
        for ent in active_entities:
            if ent["tipo"] == "evento":
                eid = ent["id"]
                # Check timeline and metadata
                in_timeline = any(eid in ev.get("participantes", []) or ent["nombre"] == ev.get("nombre") for ev in timeline)
                first_app = ent.get("primera_aparicion", {})
                page_app = first_app.get("pagina", "Pendiente")
                
                # An event is orphan if not in timeline participants and has no page origin
                if not in_timeline and (page_app == "Pendiente" or page_app == ""):
                    orphan_events.append({
                        "id": eid,
                        "nombre": ent["nombre"],
                        "alerta": "Evento huérfano sin participantes, página origen ni hito cronológico."
                    })

        # ANALYSIS 4: Underdocumented places
        underdocumented_places = []
        for ent in active_entities:
            if ent["tipo"] == "lugar":
                eid = ent["id"]
                app_cnt = appearance_counts.get(eid, 0)
                
                # Check markdown note for place to see if it's empty
                bib_folder = "Lugares"
                cleaned_name = clean_filename(ent["nombre"])
                md_path = os.path.join(self.project_path, "Biblioteca", bib_folder, f"{cleaned_name}.md")
                
                empty_note = True
                if os.path.exists(md_path):
                    with open(md_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # Check if body has real text other than templates
                    desc_match = re.search(r'## Descripción general\s*([\s\S]*?)\s*(##|$)', content)
                    if desc_match and desc_match.group(1).strip() != "Pendiente.":
                        empty_note = False
                        
                if app_cnt >= 3 and empty_note:
                    underdocumented_places.append({
                        "id": eid,
                        "nombre": ent["nombre"],
                        "apariciones": app_cnt,
                        "sugerencia": "Lugar muy mencionado pero sin descripción o detalles en su ficha."
                    })

        # ANALYSIS 5: Suggested relations (Ajuste 1: suggestions only)
        suggested_relations = []
        resolved_chars = list(page_appearances.keys())
        for i in range(len(resolved_chars)):
            for j in range(i + 1, len(resolved_chars)):
                c1 = resolved_chars[i]
                c2 = resolved_chars[j]
                
                # Calculate intersection of pages
                common_pages = page_appearances[c1].intersection(page_appearances[c2])
                co_occurrences = len(common_pages)
                
                if co_occurrences >= MIN_COAPPEARANCES:
                    # Check if relationship already exists
                    exists = False
                    for r in relations:
                        sid = self.entity_mgr.resolve_redirect_id(r.get("source_id"))
                        tid = self.entity_mgr.resolve_redirect_id(r.get("target_id"))
                        if (sid == c1 and tid == c2) or (sid == c2 and tid == c1):
                            exists = True
                            break
                            
                    if not exists:
                        # Find names
                        name1 = next((x["nombre"] for x in active_entities if x["id"] == c1), "Desconocido")
                        name2 = next((x["nombre"] for x in active_entities if x["id"] == c2), "Desconocido")
                        
                        total_c1 = len(page_appearances[c1])
                        total_c2 = len(page_appearances[c2])
                        
                        # Confidence score
                        confidence = min(100.0, round((co_occurrences / min(total_c1, total_c2)) * 100, 1))
                        
                        suggested_relations.append({
                            "source_id": c1,
                            "source_name": name1,
                            "target_id": c2,
                            "target_name": name2,
                            "co_occurrences": co_occurrences,
                            "confidence": confidence,
                            "pages": sorted(list(common_pages))
                        })
                        
        suggested_relations = sorted(suggested_relations, key=lambda x: x["confidence"], reverse=True)

        # ANALYSIS 6: Incomplete timeline
        incomplete_timeline = []
        for ev in timeline:
            num = ev.get("num")
            nombre = ev.get("nombre")
            first_app = ev.get("primera_aparicion", "Pendiente")
            desc = ev.get("descripcion", "Pendiente")
            
            if not num or first_app == "Pendiente" or desc == "Pendiente":
                incomplete_timeline.append({
                    "num": num,
                    "nombre": nombre,
                    "primera_aparicion": first_app,
                    "problema": "Falta numeración, primera aparición o descripción."
                })

        # ANALYSIS 7: Manga coverage
        total_pages = len(pages)
        documented_pages = 0
        pending_pages = []
        
        for p_num, p_info in pages.items():
            # A page is documented if it has text, narration or description
            is_doc = bool(p_info.get("texto") or p_info.get("narracion") or p_info.get("descripcion_visual"))
            if is_doc:
                documented_pages += 1
            else:
                pending_pages.append(p_num)
                
        coverage_pct = round((documented_pages / total_pages * 100) if total_pages > 0 else 0, 1)

        # Immediate Attention Pages (Ajuste 5)
        immediate_attention_pages = []
        for p_num, p_info in pages.items():
            points = 0
            reasons = []
            if not p_info.get("texto"):
                points += 1
                reasons.append("Sin texto")
            if not p_info.get("narracion"):
                points += 1
                reasons.append("Sin narración")
            if not p_info.get("descripcion_visual"):
                points += 1
                reasons.append("Sin descripción visual")
            if not p_info.get("personajes"):
                points += 1
                reasons.append("Sin personajes")
            if not p_info.get("eventos") and not p_info.get("lugares") and not p_info.get("objetos"):
                points += 1
                reasons.append("Sin entidades asociadas")
            if not p_info.get("etiquetas") or p_info.get("etiquetas") == ["#pagina", "#manga", "#pendiente"]:
                points += 1
                reasons.append("Sin etiquetas válidas")
                
            if points > 0:
                immediate_attention_pages.append({
                    "pagina": p_num,
                    "score": points,
                    "reasons": reasons
                })
        immediate_attention_pages = sorted(immediate_attention_pages, key=lambda x: x["score"], reverse=True)

        # Calculation of global Knowledge Score (Ajuste 8)
        # Entity completeness: average health score of all active entities
        entity_completeness = sum(self.entity_mgr.calculate_health_score(ent) for ent in active_entities) / len(active_entities) if active_entities else 100.0
        
        # Timeline completeness: proportion of events with page & positions
        timeline_completeness = (sum(1 for ev in timeline if ev.get("primera_aparicion") != "Pendiente" and ev.get("descripcion") != "Pendiente") / len(timeline)) * 100 if timeline else 100.0
        
        # Relations completeness: active entities with relations
        relations_completeness = (sum(1 for ent in active_entities if relation_counts.get(ent["id"], 0) > 0) / len(active_entities)) * 100 if active_entities else 100.0
        
        # Assets completeness: active entities with assets
        assets_completeness = (sum(1 for ent in active_entities if asset_counts.get(ent["id"], 0) > 0) / len(active_entities)) * 100 if active_entities else 100.0
        
        knowledge_score = round((entity_completeness * 0.3) + (timeline_completeness * 0.3) + (relations_completeness * 0.2) + (assets_completeness * 0.2), 1)

        # Top 10 Actions Recommended (Ajuste 4)
        recommendations = []
        
        # 1. Suggested relations (High confidence first)
        for sug in suggested_relations[:4]:
            recommendations.append({
                "prioridad": "Alta" if sug["confidence"] > 80 else "Media",
                "descripcion": f"Agregar relación sugerida entre {sug['source_name']} y {sug['target_name']} (Confianza: {sug['confidence']}% por co-aparición en {sug['co_occurrences']} páginas)."
            })
            
        # 2. Critical incomplete entities
        for crit in critical_entities[:3]:
            recommendations.append({
                "prioridad": "Alta",
                "descripcion": f"Documentar ficha crítica de {crit['nombre']} ({crit['tipo']}) - Health: {crit['health_score']}%. {crit['recomendacion']}"
            })
            
        # 3. Orphan events
        for o_ev in orphan_events[:2]:
            recommendations.append({
                "prioridad": "Media",
                "descripcion": f"Vincular hito cronológico o página al evento huérfano: '{o_ev['nombre']}'."
            })
            
        # 4. Underdocumented places
        for pl in underdocumented_places[:2]:
            recommendations.append({
                "prioridad": "Media",
                "descripcion": f"Agregar descripción o notas personales a la ficha del lugar: '{pl['nombre']}'."
            })
            
        # 5. Empty pages
        for p_empty in immediate_attention_pages[:2]:
            recommendations.append({
                "prioridad": "Baja",
                "descripcion": f"Rellenar transcripción o narración en la Página {p_empty['pagina']} (Faltan: {', '.join(p_empty['reasons'][:3])})."
            })
            
        # Slice exactly top 10
        recommendations = recommendations[:10]

        return {
            "knowledge_score": knowledge_score,
            "coverage_pct": coverage_pct,
            "documented_pages": documented_pages,
            "total_pages": total_pages,
            "critical_entities_count": len(critical_entities),
            "suggested_relations_count": len(suggested_relations),
            "recommendations_count": len(recommendations),
            "low_info_entities": low_info_entities,
            "important_chars_incomplete": important_chars_incomplete,
            "orphan_events": orphan_events,
            "underdocumented_places": underdocumented_places,
            "suggested_relations": suggested_relations,
            "incomplete_timeline": incomplete_timeline,
            "immediate_attention_pages": immediate_attention_pages,
            "top_recommendations": recommendations,
            "meta": {
                "total_entities": len(active_entities),
                "total_relations": len(relations),
                "total_timeline": len(timeline),
                "total_assets": len(assets)
            }
        }

    def export_reports(self):
        """Generates analysis_report.json and analysis_report.md (Ajuste 3) with timestamps (Ajuste 7)."""
        report_data = self.run_full_analysis()
        
        # Save primary JSON
        json_dir = os.path.join(self.project_path, "Datos_JSON")
        os.makedirs(json_dir, exist_ok=True)
        primary_json_path = os.path.join(json_dir, "analysis_report.json")
        save_json(primary_json_path, report_data)
        
        # Build Markdown report content
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        md_content = f"""# REPORTE DE ANÁLISIS DE CONOCIMIENTO (KNOWLEDGE ANALYSIS)

*   **Fecha de Generación:** {timestamp}
*   **Proyecto / Tomo:** {self.project_path}
*   **Global Knowledge Score:** {report_data['knowledge_score']}%
*   **Cobertura de Páginas:** {report_data['coverage_pct']}% ({report_data['documented_pages']} de {report_data['total_pages']} páginas)

---

## 🏆 TOP 10 ACCIONES RECOMENDADAS
"""
        for i, rec in enumerate(report_data["top_recommendations"], 1):
            md_content += f"{i}. **[{rec['prioridad']}]** {rec['descripcion']}\n"
            
        md_content += f"""
---

## 🔍 DETECCIONES CRÍTICAS POR MÓDULOS

### 1. Entidades Críticas / Incompletas
(Entidades activas con baja documentación y/o muchas apariciones)
"""
        for crit in report_data["low_info_entities"][:10]:
            is_crit = "🚨 CRÍTICO" if crit["is_critical"] else "⚠️ INCOMPLETO"
            md_content += f"*   **{crit['nombre']}** ({crit['tipo']} | {crit['id']}) - **Salud: {crit['health_score']}%** [{is_crit}]\n    *Recomendación:* {crit['recomendacion']}\n"
            
        md_content += """
### 2. Personajes Importantes Incompletos
(Personajes con alta frecuencia de apariciones pero cero relaciones registradas)
"""
        for char in report_data["important_chars_incomplete"][:5]:
            md_content += f"*   **{char['nombre']}** ({char['id']}): {char['apariciones']} apariciones | {char['assets']} assets. *Alerta:* {char['alerta']}\n"
            
        md_content += """
### 3. Relaciones Sugeridas por Co-aparición
(Personajes que coinciden frecuentemente en las mismas páginas y no registran relación explícita)
"""
        for sug in report_data["suggested_relations"][:10]:
            md_content += f"*   **{sug['source_name']} ⇄ {sug['target_name']}** (Confianza: {sug['confidence']}% | Co-aparición en {sug['co_occurrences']} páginas)\n    *Páginas de Co-aparición:* {', '.join([f'[[Pagina_{p}]]' for p in sug['pages']])}\n"
            
        md_content += """
### 4. Páginas que Requieren Atención Inmediata
(Ranking de páginas con carencia de textos, transcripciones o etiquetas)
"""
        for p_empty in report_data["immediate_attention_pages"][:10]:
            md_content += f"*   **Página {p_empty['pagina']}** (Score de lagunas: {p_empty['score']}/6)\n    *Problemas detectados:* {', '.join(p_empty['reasons'])}\n"
            
        md_content += """
### 5. Eventos Huérfanos
(Acontecimientos sin participantes activos, fecha o página asignada)
"""
        for ev in report_data["orphan_events"][:5]:
            md_content += f"*   **{ev['nombre']}** ({ev['id']}) - {ev['alerta']}\n"
            
        md_content += """
### 6. Lugares Subdocumentados
(Islas/Ciudades con altas menciones en páginas pero con ficha Markdown vacía)
"""
        for pl in report_data["underdocumented_places"][:5]:
            md_content += f"*   **{pl['nombre']}** ({pl['id']}) - Sugerencia: {pl['sugerencia']} ({pl['apariciones']} apariciones)\n"
            
        # Save primary MD
        primary_md_path = os.path.join(json_dir, "analysis_report.md")
        with open(primary_md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
            
        # Save versioned backups (Ajuste 7)
        version_dir = os.path.join(json_dir, "Reportes_Analisis")
        os.makedirs(version_dir, exist_ok=True)
        version_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        version_json_path = os.path.join(version_dir, f"analysis_report_{version_stamp}.json")
        save_json(version_json_path, report_data)
        
        version_md_path = os.path.join(version_dir, f"analysis_report_{version_stamp}.md")
        with open(version_md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
            
        return {
            "json_path": primary_json_path,
            "md_path": primary_md_path,
            "versioned_json_path": version_json_path,
            "versioned_md_path": version_md_path
        }
