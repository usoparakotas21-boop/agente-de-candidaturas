import sys
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import BillingSubscription, Candidate, EbookPurchase, LinkedinRebrandingPurchase

def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def show_metrics(session):
    print("=== MÉTRICAS DA CANDIDATURA CERTA ===")
    
    # 1. Access and Conversion
    total_users = session.scalar(select(func.count(Candidate.id))) or 0
    print(f"\n[1] MÉTRICAS DE CONVERSÃO:")
    print(f"Total de contas criadas (usuários): {total_users}")
    print("-> Nota: Visitantes únicos devem ser consultados no Google Analytics ou painel de hospedagem (Render), pois a aplicação não grava cookies de rastreio de navegação sem login.")
    
    # 2. Users by Plan
    subs = session.execute(
        select(BillingSubscription.owner_id, BillingSubscription.plan_code, BillingSubscription.access_until)
        .where(BillingSubscription.status.in_(['authorized', 'paused', 'canceled']))
        .order_by(BillingSubscription.updated_at.desc())
    ).all()
    
    now = _utc(datetime.utcnow())
    active_plans = {"essential": 0, "start": 0, "pro": 0, "consultoria": 0}
    seen_owners = set()
    
    for sub in subs:
        if sub.owner_id in seen_owners: continue
        seen_owners.add(sub.owner_id)
        if sub.access_until and _utc(sub.access_until) > now:
            code = (sub.plan_code or "essential").lower()
            if code in active_plans:
                active_plans[code] += 1
            else:
                active_plans["essential"] += 1
    
    active_plans["essential"] = max(0, total_users - active_plans["start"] - active_plans["pro"] - active_plans["consultoria"])
    
    print(f"\n[2] DISTRIBUIÇÃO DA BASE (Métricas por Plano):")
    for p, c in active_plans.items():
        print(f" - {p.upper()}: {c} usuários")
        
    # 3. Billing
    mrr = session.scalar(
        select(func.sum(BillingSubscription.monthly_amount))
        .where(BillingSubscription.status == 'authorized')
        .where(BillingSubscription.access_until >= now)
    ) or 0
    
    total_ebook = session.scalar(select(func.count(EbookPurchase.id))) or 0
    total_linkedin = session.scalar(select(func.count(LinkedinRebrandingPurchase.id))) or 0
    
    print(f"\n[3] CONTROLE DE VENDAS E FATURAMENTO:")
    print(f" - Faturamento Mensal Recorrente Estimado (Ativos): R$ {mrr:.2f}")
    print(f" - Vendas Avulsas E-Book DISC: {total_ebook}")
    print(f" - Vendas Avulsas Rebranding LinkedIn: {total_linkedin}")

def grant_cortesia(session, email: str, plan: str):
    plan = plan.lower()
    if plan not in ['start', 'pro', 'consultoria', 'essential']:
        print(f"Plano inválido: {plan}. Use start, pro ou consultoria.")
        return
        
    candidate = session.scalar(select(Candidate).where(Candidate.email == email))
    if not candidate:
        print(f"Usuário não encontrado com o e-mail: {email}")
        return
        
    owner_id = candidate.owner_id
    if not owner_id:
        print(f"Usuário não concluiu o cadastro (sem owner_id).")
        return
    
    if plan == 'essential':
        # Revoga acessos antigos
        session.execute(
            BillingSubscription.__table__.update()
            .where(BillingSubscription.owner_id == owner_id)
            .values(status="canceled", access_until=datetime.utcnow())
        )
        session.commit()
        print(f"Plano do usuário {email} alterado para ESSENTIAL (acesso premium revogado).")
        return

    sub = BillingSubscription(
        owner_id=owner_id,
        plan_code=plan,
        external_reference=f"CORTESIA-{uuid.uuid4()}",
        payer_email=email,
        monthly_amount=0,
        currency="BRL",
        status="authorized",
        access_until=datetime.utcnow() + timedelta(days=365) # 1 ano de cortesia
    )
    session.add(sub)
    session.commit()
    print(f"CORTESIA CONCEDIDA! O usuário {email} agora tem 1 ano grátis no plano {plan.upper()}.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python admin_cli.py metrics           (Mostra os indicadores de negócio)")
        print("  python admin_cli.py grant EMAIL PLANO (Gera uma cortesia para o usuário)")
        sys.exit(1)
        
    session = SessionLocal()
    try:
        if sys.argv[1] == "metrics":
            show_metrics(session)
        elif sys.argv[1] == "grant" and len(sys.argv) == 4:
            grant_cortesia(session, sys.argv[2], sys.argv[3])
        else:
            print("Comando inválido.")
    finally:
        session.close()
