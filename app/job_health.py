"""
Módulo de Saúde da Vaga - Versão 0.24.0
Avalia a qualidade e confiabilidade de um anúncio de vaga.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional
from .ats_registry import (
    is_ats_domain,
    is_redirect_domain,
    is_confidential_company,
)


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
        text = f"{job_data.get('title', '')} {job_data.get('description', '')}".lower()
        company = job_data.get("company", "").lower()
        
        # Pedido de pagamento
        payment_patterns = [
            "taxa de cadastro", "kit inicial", "material de treinamento",
            "investimento inicial", "pague", "depósito", "taxa de inscrição",
            "valores de", "pagamento antecipado"
        ]
        for pattern in payment_patterns:
            if pattern in text:
                self._add_signal(
                    "PEDIDO_PAGAMENTO",
                    f"Esta vaga pede pagamento: '{pattern}'",
                    "C", -60,
                    f"Trecho suspeito: '...{pattern}...'"
                )
                return
        
        # Pedido de documento antes da entrevista
        doc_patterns = [
            "envie seu cpf", "foto do rg", "dados bancários",
            "cópia do documento", "documentos pessoais", "envie seus documentos"
        ]
        for pattern in doc_patterns:
            if pattern in text:
                self._add_signal(
                    "PEDIDO_DOCUMENTO",
                    f"Pedido de documentos antes da entrevista: '{pattern}'",
                    "C", -50,
                    f"Trecho suspeito: '...{pattern}...'"
                )
                return
        
        # Renda irreal
        income_patterns = [
            r"ganhe até r\$\s*\d{1,3}\.\d{3}\s*por dia",
            r"renda extra sem sair de casa",
            r"ganho imediato",
            r"r\$\s*\d{1,2}\.\d{3},\d{2}\s*por dia",
            r"até r\$\s*\d{1,3}\.\d{3}",
        ]
        for pattern in income_patterns:
            if re.search(pattern, text):
                self._add_signal(
                    "RENDA_IRREAL",
                    "Promessa de renda irreal ou exagerada",
                    "C", -40,
                    f"Trecho suspeito: '{re.search(pattern, text).group()}'"
                )
                return
        
        # Marketing multinível (MMN)
        mmn_patterns = [
            "marketing de rede", "mmn", "seja seu próprio chefe",
            "monte sua equipe", "empreendedorismo digital",
            "sistema de indicação", "ganhe com suas indicações"
        ]
        for pattern in mmn_patterns:
            if pattern in text:
                self._add_signal(
                    "MARKETING_MULTINIVEL",
                    f"Sinais de marketing multinível: '{pattern}'",
                    "C", -50,
                    f"Termo encontrado: '{pattern}'"
                )
                return
        
        # Contato só por WhatsApp/Telegram
        if "whatsapp" in text and any(tld in text for tld in ["gmail.com", "hotmail.com", "yahoo.com", "outlook.com"]):
            self._add_signal(
                "CONTATO_INSEGURO",
                "Contato via WhatsApp com e-mail em domínio gratuito",
                "C", -30,
                "E-mail gratuito combinado com WhatsApp"
            )
        
        # CLT prometido com remuneração 100% comissionada
        if "clt" in text and ("comissão" in text or "comissões" in text) and "fixo" not in text:
            self._add_signal(
                "CLT_SEM_FIXO",
                "CLT prometido com remuneração apenas comissionada",
                "C", -25,
                "'CLT' combinado com 'comissão' sem salário fixo"
            )
        
        # PJ ou MEI apresentado como emprego
        if ("pj" in text or "mei" in text) and "clt" not in text:
            self._add_signal(
                "PJ_COMO_EMPREGO",
                "Contratação PJ/MEI apresentada como emprego",
                "C", -15,
                "Termo 'PJ' ou 'MEI' na descrição"
            )
        
        # Excesso de urgência
        urgency_patterns = [
            "vaga urgente", "últimas vagas", "início imediato",
            "contratação imediata", "preencha já", "vagas limitadas"
        ]
        urgency_count = sum(1 for p in urgency_patterns if p in text)
        if urgency_count >= 3:
            self._add_signal(
                "URGENCIA_EXCESSIVA",
                "Urgência excessiva no anúncio",
                "C", -10,
                f"{urgency_count} termos de urgência encontrados"
            )
        
        # Erros grosseiros de escrita
        if self._has_many_spelling_errors(text):
            self._add_signal(
                "ERROS_ORTIGRAFICOS",
                "Muitos erros de ortografia no anúncio",
                "C", -10,
                "Densidade alta de erros ortográficos"
            )
    
    def _has_many_spelling_errors(self, text: str) -> bool:
        """Detecta possíveis erros ortográficos (heurística básica)."""
        # Palavras comuns com erros frequentes em vagas brasileiras
        suspicious = [
            "concursso", "empressa", "experiencia", "opurtunidade",
            "candidato", "entrevista", "salario", "beneficios",
            "horario", "trabalho", "equipe", "projeto"
        ]
        error_count = sum(1 for s in suspicious if s in text.lower())
        return error_count >= 3
    
    # ============ GRUPO D - Origem ============
    def _evaluate_source(self, job_data: dict):
        """Avalia a confiabilidade da origem da vaga."""
        url = job_data.get("url", "")
        source = job_data.get("source", "")
        
        # URL em domínio de ATS conhecido
        is_ats, ats_name = is_ats_domain(url)
        if is_ats:
            self._add_signal(
                "ATS_CONHECIDO",
                f"Vaga publicada em plataforma confiável: {ats_name}",
                "D", +20,
                f"Fonte: {ats_name}"
            )
        
        # URL em domínio corporativo
        if url and not is_ats:
            from urllib.parse import urlparse
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
                # Empresas grandes costumam ter .com.br ou .com
                if any(tld in domain for tld in [".com.br", ".com", ".org"]):
                    self._add_signal(
                        "DOMINIO_CORPORATIVO",
                        "URL em domínio corporativo",
                        "D", +15,
                        f"Domínio: {domain}"
                    )
            except Exception:
                pass
        
        # URL encurtada
        if is_redirect_domain(url):
            self._add_signal(
                "URL_ENCURTADA",
                "URL encurtada (menos confiável)",
                "D", -20,
                "Link encurtado"
            )
        
        # Sem URL
        if not url:
            self._add_signal(
                "SEM_URL",
                "A vaga não tem URL para verificação",
                "D", -15,
                "URL não informada"
            )
        
        # Origem é alerta de e-mail de portal conhecido
        if source == "gmail" and is_ats:
            self._add_signal(
                "ALERTA_EMAIL",
                "Vaga recebida por alerta de e-mail confiável",
                "D", +5,
                f"Fonte: {source}"
            )