"""
Integração do módulo de saúde da vaga com o motor de decisão.
Versão 0.24.0
"""

from typing import Any, Optional
from .job_health import JobHealthEvaluator, HealthResult
from .queue_service import enqueue


def evaluate_job_health(job_data: dict, history: Optional[dict] = None) -> HealthResult:
    """
    Avalia a saúde de uma vaga.
    Wrapper para o JobHealthEvaluator.
    """
    evaluator = JobHealthEvaluator()
    return evaluator.evaluate(job_data, history)


def should_block_by_health(health_result: HealthResult) -> tuple[bool, str | None]:
    """
    Determina se a vaga deve ser bloqueada com base na saúde.
    Retorna (bloquear, motivo)
    """
    if health_result.fraud_suspected:
        return True, "Alerta de golpe detectado"
    
    if health_result.band == "SUSPEITA":
        return True, "Vaga suspeita (score muito baixo)"
    
    if health_result.band == "DUVIDOSA":
        # Para DUVIDOSA, não bloqueamos, mas marcamos para revisão
        return False, None
    
    return False, None


def get_health_decision_override(health_result: HealthResult) -> str | None:
    """
    Retorna uma decisão override baseada na saúde.
    - SUSPEITA ou fraude -> DESCARTAR
    - DUVIDOSA -> REVISAR
    - SAUDAVEL ou ACEITAVEL -> None (deixa o motor decidir)
    """
    if health_result.fraud_suspected or health_result.band == "SUSPEITA":
        return "DESCARTAR"
    if health_result.band == "DUVIDOSA":
        return "REVISAR"
    return None


def enrich_job_with_health(job_data: dict, health_result: HealthResult) -> dict:
    """
    Enriquece os dados da vaga com as informações de saúde.
    """
    enriched = dict(job_data)
    enriched["health_score"] = health_result.score
    enriched["health_band"] = health_result.band
    enriched["health_signals"] = [
        {
            "code": s.code,
            "label": s.label,
            "group": s.group,
            "adjustment": s.adjustment,
            "evidence": s.evidence
        }
        for s in health_result.signals
    ]
    enriched["fraud_suspected"] = health_result.fraud_suspected
    return enriched


# Função para ser usada no pipeline de captura
def process_with_health_check(
    job_data: dict,
    history: Optional[dict] = None,
    decision_result: Optional[dict] = None
) -> dict:
    """
    Processa uma vaga com verificação de saúde.
    Retorna o resultado enriquecido com a saúde.
    """
    # Avaliar saúde
    health_result = evaluate_job_health(job_data, history)
    
    # Enriquecer os dados
    enriched = enrich_job_with_health(job_data, health_result)
    
    # Verificar se deve sobrescrever a decisão
    override = get_health_decision_override(health_result)
    if override and decision_result:
        # Sobrescrever a decisão
        decision_result["decision"] = override
        decision_result["reasons"].append(f"SAUDE_{health_result.band}")
        decision_result["reasons"].append("FRAUDE_SUSPEITA" if health_result.fraud_suspected else "SAUDE_BAIXA")
    
    return {
        "job_data": enriched,
        "health": health_result,
        "decision_override": override
    }