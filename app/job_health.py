"""
Módulo de Saúde da Vaga - Versão 0.24.0
Avalia a qualidade e confiabilidade de um anúncio de vaga.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional
from .ats_registry import (
    is_ats_domain,
    is_redirect_domain,
    is_confidential_company,
)


def _normalize_risk_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(normalized.casefold().split())


def _has_protective_negation(sentence: str) -> bool:
    return bool(
        re.search(
            r"\b(?:nao|nunca|jamais)\b[^.!?\n]{0,120}\b(?:cobra(?:mos|r)?|cobranca|solicita(?:mos|r)?|pede(?:mos|r)?|exige(?:mos|r)?|precisa|necessita|ha|existe|sera cobrada|pague|pagar|envie|enviar|transferir|depositar)\b",
            sentence,
        )
        or re.search(r"\b(?:desconfie|evite)\b[^.!?\n]{0,100}\b(?:taxa|pix|deposito|documento|pagamento)\b", sentence)
        or re.search(r"\b(?:gratuit[oa]s?|sem custo|sem cobranca|gratuitamente)\b", sentence)
    )


def _risk_clauses(text: str) -> list[str]:
    """Split raw text before accent folding so the verb “é” is not split as “e”."""
    return [
        _normalize_risk_text(clause)
        for clause in re.split(
            r"[,;!?]+\s*|\.\s+|\n+|\b(?:mas|por[eé]m|contudo|entretanto|e)\s+",
            text,
        )
        if clause.strip()
    ]


def _actionable_match(patterns: tuple[str, ...], text: str) -> re.Match | None:
    for clause in _risk_clauses(text):
        if _has_protective_negation(clause):
            continue
        for pattern in patterns:
            match = re.search(pattern, clause)
            if match:
                return match
    return None


@dataclass
class HealthSignal:
    """Representa um sinal de saúde da vaga."""
    code: str
    label: str
    group: str  # A | B | C | D
    adjustment: int
    evidence: Optional[str] = None


@dataclass
class HealthResult:
    """Resultado da avaliação de saúde da vaga."""
    score: int
    band: str  # SAUDAVEL | ACEITAVEL | DUVIDOSA | SUSPEITA
    fraud_suspected: bool
    signals: list[HealthSignal] = field(default_factory=list)


class JobHealthEvaluator:
    """Avalia a saúde de uma vaga com base em sinais heurísticos."""
    
    def __init__(self):
        self.signals: list[HealthSignal] = []
        self.fraud_suspected = False
        self.score = 100
    
    def evaluate(self, job_data: dict, history: Optional[dict] = None) -> HealthResult:
        """
        Avalia a saúde da vaga.
        
        Args:
            job_data: Dicionário com dados da vaga (title, company, description, etc.)
            history: Histórico de aparições (seen_count, first_seen_at, last_seen_at)
        
        Returns:
            HealthResult com score, band e sinais
        """
        self.signals = []
        self.fraud_suspected = False
        self.score = 100
        
        # Grupo A - Repostagem e vaga fantasma
        self._evaluate_reposting(job_data, history)
        
        # Grupo B - Qualidade do anúncio
        self._evaluate_quality(job_data)
        
        # Grupo C - Risco de golpe (foco Brasil)
        self._evaluate_fraud_risk(job_data)
        
        # Grupo D - Confiabilidade da origem
        self._evaluate_source(job_data)
        
        # Calcular score final
        self.score = max(0, min(100, self.score))
        
        # Verificar se há suspeita de fraude
        if any(s.adjustment <= -40 and s.group == "C" for s in self.signals):
            self.fraud_suspected = True
            self.score = min(self.score, 15)
        
        # Determinar banda
        if self.fraud_suspected:
            band = "SUSPEITA"
        elif self.score >= 80:
            band = "SAUDAVEL"
        elif self.score >= 55:
            band = "ACEITAVEL"
        elif self.score >= 30:
            band = "DUVIDOSA"
        else:
            band = "SUSPEITA"
        
        return HealthResult(
            score=self.score,
            band=band,
            fraud_suspected=self.fraud_suspected,
            signals=self.signals
        )
    
    def _add_signal(self, code: str, label: str, group: str, adjustment: int, evidence: Optional[str] = None):
        """Adiciona um sinal e ajusta o score."""
        self.signals.append(HealthSignal(
            code=code,
            label=label,
            group=group,
            adjustment=adjustment,
            evidence=evidence
        ))
        self.score += adjustment
    
    # ============ GRUPO A - Repostagem ============
    def _evaluate_reposting(self, job_data: dict, history: Optional[dict]):
        """Avalia sinais de vaga fantasma/repostagem."""
        # Vaga reaparecendo há muito tempo (>45 dias)
        if history and history.get("first_seen_at") and history.get("last_seen_at"):
            from datetime import datetime, timedelta
            try:
                first = datetime.fromisoformat(history["first_seen_at"])
                last = datetime.fromisoformat(history["last_seen_at"])
                days_active = (last - first).days
                
                if days_active > 45:
                    self._add_signal(
                        "VAGA_FANTASMA",
                        f"Esta vaga está sendo republicada há {days_active} dias",
                        "A", -25,
                        f"Primeira aparição: {first.strftime('%d/%m/%Y')}"
                    )
                elif history.get("seen_count", 0) >= 5:
                    self._add_signal(
                        "REPOSTAGEM_FREQUENTE",
                        f"Esta vaga já apareceu {history['seen_count']} vezes",
                        "A", -15,
                        f"Vista {history['seen_count']} vezes"
                    )
            except Exception:
                pass
        
        # Banco de talentos disfarçado
        text = f"{job_data.get('title', '')} {job_data.get('description', '')}".lower()
        bank_patterns = [
            "banco de talentos", "cadastro reserva", "talent pool", 
            "candidatura espontânea", "banco de currículos"
        ]
        for pattern in bank_patterns:
            if pattern in text:
                self._add_signal(
                    "BANCO_DE_TALENTOS",
                    "Isto parece um cadastro de reserva, não uma vaga aberta",
                    "A", -40,
                    f"Termo encontrado: '{pattern}'"
                )
                break
    
    # ============ GRUPO B - Qualidade ============
    def _evaluate_quality(self, job_data: dict):
        """Avalia a qualidade e concretude do anúncio."""
        description = job_data.get("description", "")
        title = job_data.get("title", "")
        company = job_data.get("company", "")
        
        # Descrição muito curta
        desc_length = len(description.strip())
        if desc_length < 400:
            self._add_signal(
                "DESCRICAO_CURTA",
                f"Descrição muito curta ({desc_length} caracteres)",
                "B", -15,
                f"Descrição com {desc_length} caracteres"
            )
        
        # Sem responsabilidades concretas
        if not self._has_responsibilities(description):
            self._add_signal(
                "SEM_RESPONSABILIDADES",
                "Não foram encontradas responsabilidades concretas na descrição",
                "B", -10,
                "Ausência de lista de responsabilidades"
            )
        
        # Sem requisitos identificáveis
        if not self._has_requirements(description):
            self._add_signal(
                "SEM_REQUISITOS",
                "Não foram encontrados requisitos claros",
                "B", -10,
                "Ausência de requisitos ou qualificações"
            )
        
        # Empresa não identificada ou confidencial
        if is_confidential_company(company):
            self._add_signal(
                "EMPRESA_CONFIDENCIAL",
                "A empresa não foi identificada claramente",
                "B", -20,
                f"Empresa: '{company or 'não informada'}'"
            )
        
        # Sem faixa salarial
        if not job_data.get("salary") or job_data.get("salary") == "":
            self._add_signal(
                "SEM_SALARIO",
                "A vaga não informa faixa salarial",
                "B", -5,
                "Salário não informado"
            )
        else:
            self._add_signal(
                "COM_SALARIO",
                "Faixa salarial informada",
                "B", +10,
                f"Salário: {job_data.get('salary')}"
            )
        
        # Descrição com responsabilidades e requisitos
        if self._has_responsibilities(description) and self._has_requirements(description):
            self._add_signal(
                "DESCRICAO_COMPLETA",
                "Descrição com responsabilidades e requisitos claros",
                "B", +10,
                "Anúncio bem estruturado"
            )
    
    def _has_responsibilities(self, text: str) -> bool:
        """Verifica se a descrição tem responsabilidades concretas."""
        text_lower = text.lower()
        # Padrões de responsabilidades
        patterns = [
            r"respons[aá]vel por",
            r"atividades",
            r"atribuiç[õo]es",
            r"ir[aá] atuar",
            r"suas atividades",
            r"principais atividades",
            r"vai atuar",
            r"atuar[aá]",
            r"(?:\n|\.)\s*[-•*]\s*",
            r"habilidades",
            r"compet[eê]ncias",
        ]
        return any(re.search(p, text_lower) for p in patterns)
    
    def _has_requirements(self, text: str) -> bool:
        """Verifica se a descrição tem requisitos ou qualificações."""
        text_lower = text.lower()
        patterns = [
            r"requisitos",
            r"qualificaç[õo]es",
            r"formaç[aã]o",
            r"necess[aá]rio",
            r"experi[eê]ncia",
            r"conhecimento",
            r"habilidades",
            r"compet[eê]ncias",
            r"desej[aá]vel",
            r"diferencial",
            r"ensino",
            r"graduaç[aã]o",
            r"curso",
            r"certificaç[aã]o",
        ]
        return any(re.search(p, text_lower) for p in patterns)
    
    # ============ GRUPO C - Risco de Golpe ============
    def _evaluate_fraud_risk(self, job_data: dict):
        """Avalia sinais de golpe ou relação de trabalho enganosa."""
        raw_text = f"{job_data.get('title', '')} {job_data.get('description', '')}"
        text = _normalize_risk_text(raw_text)

        payment_patterns = (
            r"\btaxa(?:s)?\s+(?:de\s+)?(?:cadastro|inscricao|participacao|processo seletivo|entrevista|treinamento|material)\b",
            r"\b(?:cobram|cobraremos|cobranca de)\s+(?:uma\s+)?taxa\b",
            r"\b(?:pague|pagar|efetue|realize|transfira|deposite)\b[^.!?\n]{0,100}\b(?:taxa|pix|deposito|transferencia|pagamento|kit|curso|material|treinamento)\b",
            r"\b(?:pix|chave pix|deposito|transferencia|pagamento)\b[^.!?\n]{0,100}\b(?:para|a fim de)\s+(?:participar|concorrer|se candidatar|continuar|garantir|agendar)\b",
            r"\b(?:compre|adquira|pague|pagar)\b[^.!?\n]{0,80}\b(?:kit|curso|material|treinamento)\b",
            r"\b(?:compra|comprar|aquisicao|adquirir|adquira)\b[^.!?\n]{0,80}\b(?:kit|curso|material|treinamento)\b",
            r"\binvestimento inicial\b|\bpagamento antecipado\b",
        )
        if _actionable_match(payment_patterns, raw_text):
            self._add_signal(
                "PEDIDO_PAGAMENTO",
                "O anúncio solicita taxa, pagamento ou transferência para avançar no processo",
                "C", -60,
                "Solicitação de pagamento associada à candidatura",
            )
            return

        # A coleta de documento só é tratada como risco alto quando há pedido
        # antecipado por canal informal, não por uma etapa normal de admissão.
        document_terms = r"\b(?:cpf|rg|identidade|dados bancarios|documentos pessoais|copia do documento|selfie|foto do documento)\b"
        request_terms = r"\b(?:envie|enviar|encaminhe|encaminhar|mande|mandar|informe|informar|compartilhe|compartilhar|anexe|anexar|forneca|fornecer)\b"
        early_terms = r"\b(?:antes da entrevista|antes de ser entrevistado|para se candidatar|para participar do processo seletivo|na primeira etapa|antes da contratacao)\b"
        informal_terms = r"\b(?:whatsapp|telegram|gmail\.com|hotmail\.com|outlook\.com|yahoo\.com)\b"
        for sentence in _risk_clauses(raw_text):
            if not _has_protective_negation(sentence) and all(
                re.search(pattern, sentence)
                for pattern in (document_terms, request_terms, early_terms, informal_terms)
            ):
                self._add_signal(
                    "PEDIDO_DOCUMENTO",
                    "O anúncio pede documento sensível antes da entrevista por canal informal",
                    "C", -50,
                    "Documento ou dado bancário solicitado antes da entrevista",
                )
                return

        income_patterns = (
            r"ganhe ate r\$\s*\d{1,3}\.\d{3}\s*por dia",
            r"renda extra sem sair de casa",
            r"ganho imediato",
            r"r\$\s*\d{1,2}\.\d{3},\d{2}\s*por dia",
            r"ate r\$\s*\d{1,3}\.\d{3}",
        )
        if _actionable_match(income_patterns, raw_text):
            self._add_signal(
                "RENDA_IRREAL",
                "Promessa de renda irreal ou exagerada",
                "C", -40,
                "Promessa de remuneração diária excepcional",
            )
            return

        mmn_patterns = (
            r"marketing de rede", r"\bmmn\b", r"seja seu proprio chefe",
            r"monte sua equipe", r"empreendedorismo digital",
            r"sistema de indicacao", r"ganhe com suas indicacoes",
        )
        if _actionable_match(mmn_patterns, raw_text):
            self._add_signal(
                "MARKETING_MULTINIVEL",
                "O anúncio apresenta sinais de marketing multinível",
                "C", -50,
                "Promessa de renda baseada em rede ou indicação",
            )
            return

        direct_contact_pattern = r"\b(?:chame|fale|contate|contatar|entre em contato|envie seu curriculo|mande seu curriculo)\b[^.!?\n]{0,100}\b(?:whatsapp|telegram)\b"
        free_email_pattern = r"\b(?:gmail|hotmail|outlook|yahoo)\.com\b"
        for clause in _risk_clauses(raw_text):
            if (
                not _has_protective_negation(clause)
                and re.search(direct_contact_pattern, clause)
                and re.search(free_email_pattern, clause)
            ):
                self._add_signal(
                    "CONTATO_INSEGURO",
                    "O anúncio direciona a candidatura para mensageria e e-mail pessoal",
                    "C", -30,
                    "Convite de contato por mensageria com e-mail gratuito",
                )
                break

        if re.search(r"\bclt\b", text) and re.search(r"\bcomissoes?\b", text) and not re.search(r"\b(?:salario|remuneracao) fixo\b", text):
            self._add_signal(
                "CLT_SEM_FIXO",
                "CLT prometido com remuneração apenas comissionada",
                "C", -25,
                "CLT combinado com comissão sem indicação de salário fixo",
            )

        if re.search(r"\b(?:pj|mei)\b", text) and not re.search(r"\bclt\b", text):
            self._add_signal(
                "PJ_COMO_EMPREGO",
                "A vaga informa contratação PJ/MEI; confira o regime antes de avançar",
                "C", -8,
                "Modalidade PJ/MEI identificada",
            )

        urgency_patterns = (
            "vaga urgente", "ultimas vagas", "inicio imediato",
            "contratacao imediata", "preencha ja", "vagas limitadas"
        )
        urgency_count = sum(1 for p in urgency_patterns if p in text)
        if urgency_count >= 3:
            self._add_signal(
                "URGENCIA_EXCESSIVA",
                "Urgência excessiva no anúncio",
                "C", -10,
                f"{urgency_count} termos de urgência encontrados"
            )

        if self._has_many_spelling_errors(text):
            self._add_signal(
                "ERROS_ORTIGRAFICOS",
                "Muitos erros de ortografia no anúncio",
                "C", -10,
                "Densidade alta de erros ortográficos"
            )
    
    def _has_many_spelling_errors(self, text: str) -> bool:
        """Detecta possíveis erros ortográficos (heurística básica)."""
        # Apenas formas claramente incorretas; remover acentos de uma palavra
        # correta não deve ser contabilizado como erro de ortografia.
        suspicious = [
            "concursso", "empressa", "opurtunidade", "oportuniddade",
            "experienca", "candidatto", "entrevsta", "benefisios",
        ]
        error_count = sum(1 for s in suspicious if s in _normalize_risk_text(text))
        return error_count >= 2
    
    # ============ GRUPO D - Origem ============
    def _evaluate_source(self, job_data: dict):
        """Avalia apenas sinais verificáveis da origem; domínio genérico não prova legitimidade."""
        url = job_data.get("url", "")
        source = job_data.get("source", "")
        
        # A plataforma conhecida identifica o canal de publicação, mas não
        # confirma por si só a empresa nem a legitimidade do anúncio.
        is_ats, ats_name = is_ats_domain(url)
        if is_ats:
            self._add_signal(
                "ATS_CONHECIDO",
                f"Link em plataforma de recrutamento conhecida: {ats_name}",
                "D", +15,
                "O domínio do link corresponde à plataforma; confira a empresa e o anúncio",
            )
        
        if url:
            from urllib.parse import urlparse
            try:
                parsed = urlparse(url.strip())
                if parsed.scheme.casefold() == "http":
                    self._add_signal(
                        "URL_SEM_HTTPS",
                        "O anúncio usa HTTP sem criptografia no endereço",
                        "D", -10,
                        "O link não usa HTTPS",
                    )
            except Exception:
                pass
        
        # Um canal de chegada por e-mail não valida o remetente nem o anúncio.
        # Links encurtados seguem como sinal de cautela, salvo o encurtador
        # oficial do LinkedIn quando essa origem foi identificada no alerta.
        if is_redirect_domain(url):
            from urllib.parse import urlparse
            host = (urlparse(url).hostname or "").casefold().rstrip(".")
            source_name = _normalize_risk_text(source)
            is_linkedin_short_link = (
                source_name == "linkedin"
                and (host == "lnkd.in" or host.endswith(".lnkd.in"))
            )
            if not is_linkedin_short_link:
                self._add_signal(
                    "URL_ENCURTADA",
                    "O anúncio usa um link encurtado; confira o destino antes de avançar",
                    "D", -20,
                    "Destino final não está visível no link",
                )
        
        # Sem URL
        if not url:
            self._add_signal(
                "SEM_URL",
                "A vaga não tem URL para verificação",
                "D", -15,
                "URL não informada"
            )
