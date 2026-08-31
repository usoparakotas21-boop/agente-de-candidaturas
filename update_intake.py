import re
import sys

# Ler o arquivo main.py
with open("app/main.py", "r", encoding="utf-8") as f:
    content = f.read()

# Nova função completa
new_function = '''
@app.post("/intake/text")
def intake_text(req: JobIntakeRequest, user=Depends(authenticated_user)):
    try:
        parsed = parse_job_text(req.raw_text, req.source)
        quality = assess_job_capture(parsed)
    except ValueError as e:
        raise HTTPException(422, str(e))
    
    db = SessionLocal()
    try:
        oid = _owner_id(user)
        ext_id = f"{oid}:{parsed['external_id']}" if oid else parsed["external_id"]
        existing = db.scalar(select(Job).where(Job.external_id == ext_id))
        
        if existing:
            c = _candidate_for_user(db, user)
            app = _ensure_app(db, existing, c)
            _save_quality(app, quality)
            analysis = None
            if req.reprocess_existing:
                existing.source = parsed["source"]
                existing.company = parsed["company"]
                existing.title = parsed["title"]
                existing.description = parsed["description"]
                for f in ("location", "modality", "salary", "url"):
                    if parsed[f]:
                        setattr(existing, f, parsed[f])
                if req.auto_analyze:
                    arts = _build_application(existing, c)
                    analysis = arts["analysis"]
                    _save_analysis(app, analysis, c)
                    if app.status in ("IDENTIFICADA", "ARQUIVADA"):
                        _advance_app(db, app, "ANALISADA", "Vaga atualizada e reanalisada.")
                    else:
                        db.add(ApplicationEvent(application=app, status=app.status, note="Dados atualizados e score recalculado."))
            if analysis is None:
                _apply_decision(app, c, None)
            db.commit()
            db.refresh(existing)
            db.refresh(app)
            return {
                "status": "VAGA_ATUALIZADA" if req.reprocess_existing else "VAGA_JA_EXISTIA",
                "duplicate": True,
                "updated": req.reprocess_existing,
                "job_id": existing.id,
                "application_id": app.id,
                "application_status": app.status,
                "company": existing.company,
                "job_title": existing.title,
                "location": existing.location,
                "modality": existing.modality,
                "url": existing.url,
                "analysis": analysis
            }
        
        from .queue_service import enqueue
        
        captured_data = {
            "title": parsed.get("title"),
            "company": parsed.get("company"),
            "location": parsed.get("location"),
            "modality": parsed.get("modality"),
            "url": parsed.get("url"),
            "description": parsed.get("description"),
            "raw_excerpt": req.raw_text[:2000],
            "confidence_title": quality.get("field_confidence", {}).get("title"),
            "confidence_company": quality.get("field_confidence", {}).get("company"),
            "confidence_description": quality.get("field_confidence", {}).get("description"),
            "confidence_url": quality.get("field_confidence", {}).get("url"),
            "confidence_overall": quality.get("confidence"),
            "health_score": quality.get("health", {}).get("score"),
            "health_band": quality.get("health", {}).get("band"),
            "health_signals": quality.get("health", {}).get("signals", []),
            "fraud_suspected": quality.get("health", {}).get("fraud_suspected", False),
        }
        
        decision_result = {
            "decision": quality.get("decision", "REVISAR"),
            "reasons": quality.get("reasons", []),
            "engine_version": "0.24.0",
            "score": None,
        }
        
        item, created = enqueue(
            session=db,
            owner_id=oid,
            captured=captured_data,
            decision_result=decision_result,
            source="texto",
            source_ref=parsed.get("external_id"),
        )
        db.commit()
        
        job_id = item.job_id
        application = None
        if job_id:
            job = db.scalar(select(Job).where(Job.id == job_id))
            if job:
                c = _candidate_for_user(db, user)
                application = _ensure_app(db, job, c)
                db.commit()
                db.refresh(application)
        
        return {
            "status": "VAGA_ENFILEIRADA",
            "duplicate": False,
            "queue_item_id": item.id,
            "queue_decision": item.decision,
            "queue_status": item.status,
            "job_id": job_id,
            "application_id": application.id if application else None,
            "company": parsed.get("company"),
            "job_title": parsed.get("title"),
            "location": parsed.get("location"),
            "modality": parsed.get("modality"),
            "url": parsed.get("url"),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
'''

# Usar regex para encontrar e substituir a função
pattern = r'@app\.post\("/intake/text"\).*?finally:\s+db\.close\(\)'
content = re.sub(pattern, new_function, content, flags=re.DOTALL)

# Salvar
with open("app/main.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ main.py atualizado com sucesso!")