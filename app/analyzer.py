from typing import Any


import unicodedata


def normalize(text: str) -> str:
    text = str(text or "").lower()

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    return " ".join(text.split())

def contains_any(text: str, terms: list[str]) -> bool:
    text = normalize(text)

    return any(
        normalize(term) in text
        for term in terms
    )


def evidence_match(
    text: str,
    direct_terms: list[str],
    related_terms: list[str],
) -> str:

    if contains_any(text, direct_terms):
        return "COMPROVADO_DIRETAMENTE"

    if contains_any(text, related_terms):
        return "COMPROVADO_POR_EXPERIENCIA_RELACIONADA"

    return "NAO_ENCONTRADO"


def analyze_job(
    job_text: str,
    profile: dict[str, Any],
) -> dict[str, Any]:

    job = normalize(job_text)

    profile_text = normalize(
        " ".join(
            [
                profile.get("summary", ""),
                " ".join(profile.get("target_roles", [])),
                " ".join(profile.get("experience_texts", [])),
                " ".join(profile.get("skills", [])),
            ]
        )
    )

    # ==================================================
    # REQUISITOS PROFISSIONAIS
    # ==================================================

    requirements = {

        "Recursos Humanos": {
            "direct": [
                "recursos humanos",
                "rh",
                "rh generalista",
                "gente e gestao",
            ],
            "related": [
                "gestao de pessoas",
                "gestao de equipes",
                "recursos humanos generalista",
            ],
        },

        "Departamento Pessoal": {
            "direct": [
                "departamento pessoal",
                "dp",
                "administracao de pessoal",
            ],
            "related": [
                "folha de pagamento",
                "folha",
                "admissao",
                "admissões",
                "demissao",
                "demissões",
                "encargos",
                "ferias",
                "férias",
                "decimo terceiro",
                "13º",
                "ponto eletronico",
                "ponto eletrônico",
                "e-social",
                "esocial",
                "relacoes trabalhistas",
                "relações trabalhistas",
            ],
        },

        "Folha de Pagamento": {
            "direct": [
                "folha de pagamento",
                "processamento de folha",
                "gestao da folha",
            ],
            "related": [
                "encargos",
                "provisoes de ferias",
                "provisões de férias",
                "13º",
                "decimo terceiro",
                "admissao",
                "demissao",
            ],
        },

        "Recrutamento e Seleção": {
            "direct": [
                "recrutamento e selecao",
                "recrutamento e seleção",
                "recrutamento",
                "selecao",
                "seleção",
                "r&s",
            ],
            "related": [
                "atracao de talentos",
                "atração de talentos",
                "contratacao",
                "contratação",
                "admissao",
                "admissão",
            ],
        },

        "Treinamento e Desenvolvimento": {
            "direct": [
                "treinamento e desenvolvimento",
                "treinamento",
                "desenvolvimento",
                "t&d",
            ],
            "related": [
                "desenvolvimento de lideranca",
                "desenvolvimento de liderança",
                "capacitação",
                "capacitacao",
                "avaliacao de desempenho",
                "avaliação de desempenho",
            ],
        },

        "Gestão de Equipes": {
            "direct": [
                "gestao de equipes",
                "gestão de equipes",
                "lideranca de equipes",
                "liderança de equipes",
            ],
            "related": [
                "lideranca",
                "liderança",
                "gestao de pessoas",
                "gestão de pessoas",
                "supervisao",
                "supervisão",
                "coordenacao",
                "coordenação",
            ],
        },

        "Power BI": {
            "direct": [
                "power bi",
                "powerbi",
            ],
            "related": [
                "dashboards",
                "dashboard",
                "business intelligence",
                "bi",
                "indicadores",
            ],
        },

        "Indicadores e KPIs": {
            "direct": [
                "indicadores",
                "kpis",
                "indicadores de rh",
                "indicadores de recursos humanos",
            ],
            "related": [
                "dashboards",
                "metas",
                "performance",
                "analise de dados",
                "análise de dados",
            ],
        },

        "e-Social": {
            "direct": [
                "e-social",
                "esocial",
            ],
            "related": [
                "obrigações trabalhistas",
                "obrigacoes trabalhistas",
                "conformidade trabalhista",
                "legislacao trabalhista",
                "legislação trabalhista",
            ],
        },

        "Legislação Trabalhista": {
            "direct": [
                "legislacao trabalhista",
                "legislação trabalhista",
            ],
            "related": [
                "relacoes trabalhistas",
                "relações trabalhistas",
                "e-social",
                "esocial",
                "encargos",
            ],
        },

        "Gestão de Custos": {
            "direct": [
                "gestao de custos",
                "gestão de custos",
                "reducao de custos",
                "redução de custos",
            ],
            "related": [
                "horas extras",
                "controle de despesas",
                "otimizacao",
                "otimização",
                "eficiencia operacional",
                "eficiência operacional",
            ],
        },

        "Implantação de RH": {
            "direct": [
                "implantacao de rh",
                "implantação de rh",
                "estruturação de rh",
                "estruturacao de rh",
            ],
            "related": [
                "implantacao",
                "implantação",
                "implantacao de setor",
                "implantação de setor",
                "estruturação",
                "estruturacao",
            ],
        },
    }

    requirements_result = []

    for requirement, rules in requirements.items():

        if not contains_any(
            job,
            rules["direct"] + rules["related"],
        ):
            continue

        status = evidence_match(
            profile_text,
            rules["direct"],
            rules["related"],
        )

        if status == "COMPROVADO_DIRETAMENTE":
            score = 1.0

        elif status == "COMPROVADO_POR_EXPERIENCIA_RELACIONADA":
            score = 0.75

        else:
            score = 0.0

        requirements_result.append(
            {
                "requirement": requirement,
                "status": status,
                "score": score,
            }
        )

    # ==================================================
    # TECNOLOGIAS
    # ==================================================

    technologies = {
        "Power BI": [
            "power bi",
            "powerbi",
        ],
        "TOTVS": [
            "totvs",
            "protheus",
            "rm labore",
            "rm totvs",
        ],
        "SAP": [
            "sap",
        ],
        "Excel": [
            "excel",
        ],
        "VBA": [
            "vba",
            "visual basic",
            "macros",
        ],
        "Domínio": [
            "dominio",
            "domínio",
        ],
    }

    technology_result = []

    for technology, terms in technologies.items():

        if contains_any(job, terms):

            if contains_any(profile_text, terms):
                status = "COMPROVADO"
            else:
                status = "NAO_ENCONTRADO"

            technology_result.append(
                {
                    "requirement": technology,
                    "status": status,
                }
            )

    # ==================================================
    # IDIOMAS
    # ==================================================

    languages = {
        "Inglês": [
            "ingles",
            "inglês",
        ],
        "Espanhol": [
            "espanhol",
        ],
        "Mandarim": [
            "mandarim",
        ],
    }

    language_result = []

    for language, terms in languages.items():

        if contains_any(job, terms):

            if contains_any(profile_text, terms):
                status = "INFORMADO_NO_PERFIL"
            else:
                status = "NAO_INFORMADO"

            language_result.append(
                {
                    "requirement": language,
                    "status": status,
                }
            )

    # ==================================================
    # SENIORIDADE
    # ==================================================

    seniority_terms = [
        "coordenador",
        "coordenacao",
        "coordenação",
        "supervisor",
        "supervisao",
        "supervisão",
        "gerente",
        "gerencia",
        "gerência",
        "especialista",
        "senior",
        "sênior",
    ]

    seniority_match = contains_any(
        job,
        seniority_terms,
    )

    # ==================================================
    # LOCALIZAÇÃO
    # ==================================================

    location_terms = [
        "salvador",
        "lauro de freitas",
        "camacari",
        "camaçari",
        "feira de santana",
        "bahia",
        "remoto",
        "remota",
        "hibrido",
        "híbrido",
    ]

    location_match = contains_any(
        job,
        location_terms,
    )

    # ==================================================
    # SCORE DE REQUISITOS
    # ==================================================

    total_requirements = len(
        requirements_result
    )

    requirement_score = 0

    if total_requirements > 0:

        requirement_points = sum(
            item["score"]
            for item in requirements_result
        )

        requirement_score = (
            requirement_points
            / total_requirements
        ) * 60

    # ==================================================
    # EXPERIÊNCIA
    # ==================================================

    experience_count = len(
        profile.get("experience_texts", [])
    )

    experience_score = min(
        10,
        experience_count * 1.5,
    )

    # ==================================================
    # SENIORIDADE
    # ==================================================

    seniority_score = (
        15
        if seniority_match
        else 5
    )

    # ==================================================
    # TECNOLOGIA
    # ==================================================

    technology_score = min(
        10,
        sum(
            2
            for item in technology_result
            if item["status"] == "COMPROVADO"
        ),
    )

    # ==================================================
    # LOCALIZAÇÃO
    # ==================================================

    location_score = (
        5
        if location_match
        else 2
    )

    # ==================================================
    # SCORE FINAL
    # ==================================================

    score = round(
        min(
            100,
            requirement_score
            + experience_score
            + seniority_score
            + technology_score
            + location_score,
        )
    )

    # ==================================================
    # RECOMENDAÇÃO
    # ==================================================

    if score >= 85:
        recommendation = "ALTA PRIORIDADE"

    elif score >= 70:
        recommendation = "BOA OPORTUNIDADE"

    elif score >= 55:
        recommendation = "AVALIAR"

    else:
        recommendation = "BAIXA PRIORIDADE"

    # ==================================================
    # FORÇAS
    # ==================================================

    strengths = [
        item["requirement"]
        for item in requirements_result
        if item["status"]
        in [
            "COMPROVADO_DIRETAMENTE",
            "COMPROVADO_POR_EXPERIENCIA_RELACIONADA",
        ]
    ]

    # ==================================================
    # GAPS
    # ==================================================

    gaps = [
        item["requirement"]
        for item in requirements_result
        if item["status"]
        == "NAO_ENCONTRADO"
    ]

    # ==================================================
    # PRÓXIMA AÇÃO
    # ==================================================

    if score >= 70:
        next_action = "PERSONALIZAR_CURRICULO"

    elif score >= 55:
        next_action = "REVISAR"

    else:
        next_action = "NAO_PRIORITARIA"

    return {
        "score": score,

        "recommendation": recommendation,

        "score_breakdown": {
            "requirements": round(
                requirement_score,
                1,
            ),
            "seniority": seniority_score,
            "technology": technology_score,
            "location": location_score,
            "experience": experience_score,
        },

        "requirements": requirements_result,

        "technologies": technology_result,

        "languages": language_result,

        "strengths": strengths,

        "gaps": gaps,

        "seniority_match": seniority_match,

        "location_match": location_match,

        "next_action": next_action,
    }