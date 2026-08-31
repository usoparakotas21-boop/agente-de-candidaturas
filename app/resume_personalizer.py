from typing import Any


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def contains_any(text: str, terms: list[str]) -> bool:
    text = normalize(text)
    return any(normalize(term) in text for term in terms)


def personalize_resume(
    job_title: str,
    job_description: str,
    profile: dict[str, Any],
) -> dict[str, Any]:

    job_text = normalize(
        f"{job_title} {job_description}"
    )

    experiences = profile.get(
        "experiences",
        []
    )

    skills = profile.get(
        "skills",
        []
    )

    # -----------------------------------------------
    # PALAVRAS-CHAVE POR ÁREA
    # -----------------------------------------------

    keyword_groups = {

        "rh": [
            "recursos humanos",
            "rh",
            "gestao de pessoas",
            "gestão de pessoas",
            "gente e gestao",
            "gente e gestão",
        ],

        "dp": [
            "departamento pessoal",
            "administracao de pessoal",
            "administração de pessoal",
            "folha",
            "folha de pagamento",
            "admissao",
            "admissão",
            "demissao",
            "demissão",
            "ponto",
            "encargos",
            "e-social",
            "esocial",
        ],

        "recrutamento": [
            "recrutamento",
            "selecao",
            "seleção",
            "r&s",
            "atracao de talentos",
            "atração de talentos",
        ],

        "td": [
            "treinamento",
            "desenvolvimento",
            "t&d",
            "lideranca",
            "liderança",
            "avaliacao de desempenho",
            "avaliação de desempenho",
        ],

        "dados": [
            "power bi",
            "powerbi",
            "dashboard",
            "dashboards",
            "kpi",
            "kpis",
            "indicadores",
            "business intelligence",
            "data analytics",
        ],

        "gestao": [
            "gestao de equipes",
            "gestão de equipes",
            "coordenacao",
            "coordenação",
            "supervisao",
            "supervisão",
            "lideranca",
            "liderança",
        ],

        "custos": [
            "reducao de custos",
            "redução de custos",
            "horas extras",
            "eficiencia operacional",
            "eficiência operacional",
            "otimizacao",
            "otimização",
        ],

        "trabalhista": [
            "legislacao trabalhista",
            "legislação trabalhista",
            "relacoes trabalhistas",
            "relações trabalhistas",
            "e-social",
            "esocial",
            "compliance",
        ],
    }

    # -----------------------------------------------
    # IDENTIFICA ÁREAS DA VAGA
    # -----------------------------------------------

    active_groups = []

    for group, terms in keyword_groups.items():

        if contains_any(job_text, terms):
            active_groups.append(group)

    # -----------------------------------------------
    # PRIORIDADE DAS EXPERIÊNCIAS
    # -----------------------------------------------

    ranked_experiences = []

    for experience in experiences:

        text = normalize(
            " ".join(
                [
                    experience.get("company", ""),
                    experience.get("role", ""),
                    experience.get("description", ""),
                ]
            )
        )

        matched_groups = []

        for group in active_groups:

            if contains_any(
                text,
                keyword_groups[group],
            ):
                matched_groups.append(group)

        score = len(matched_groups)

        ranked_experiences.append(
            {
                "company": experience.get(
                    "company",
                    "",
                ),
                "role": experience.get(
                    "role",
                    "",
                ),
                "description": experience.get(
                    "description",
                    "",
                ),
                "start_date": experience.get("start_date", ""),
                "end_date": experience.get("end_date", ""),
                "period": experience.get("period", ""),
                "bullets": experience.get("bullets", []),
                "relevance_score": score,
                "matched_areas": matched_groups,
            }
        )

    ranked_experiences.sort(
        key=lambda item: item["relevance_score"],
        reverse=True,
    )

    # -----------------------------------------------
    # COMPETÊNCIAS RELEVANTES
    # -----------------------------------------------

    prioritized_skills = []

    for skill in skills:

        if contains_any(
            job_text,
            [skill],
        ):
            prioritized_skills.append(
                {
                    "skill": skill,
                    "reason": "Encontrada na descrição da vaga.",
                }
            )

    # Depois adiciona competências relacionadas
    # às áreas identificadas.

    for skill in skills:

        if any(
            skill.lower()
            in " ".join(
                keyword_groups[group]
            ).lower()
            for group in active_groups
        ):

            already_exists = any(
                item["skill"].lower()
                == skill.lower()
                for item in prioritized_skills
            )

            if not already_exists:

                prioritized_skills.append(
                    {
                        "skill": skill,
                        "reason": "Relacionada aos requisitos da vaga.",
                    }
                )

    # -----------------------------------------------
    # EVIDÊNCIAS
    # -----------------------------------------------

    evidences = []

    for experience in ranked_experiences:

        if experience["relevance_score"] > 0:

            evidences.append(
                {
                    "company": experience["company"],
                    "role": experience["role"],
                    "areas": experience["matched_areas"],
                }
            )

    # -----------------------------------------------
    # RESUMO DIRECIONADO
    # -----------------------------------------------

    role = job_title.strip()

    summary_parts = [
        f"Profissional de Recursos Humanos com mais de 10 anos de experiência, "
        f"com trajetória alinhada à posição de {role}.",
    ]

    if "rh" in active_groups:
        summary_parts.append(
            "Experiência em gestão de pessoas, RH generalista e estratégico."
        )

    if "dp" in active_groups:
        summary_parts.append(
            "Atuação sólida em Departamento Pessoal, "
            "administração de pessoal, folha, ponto e rotinas trabalhistas."
        )

    if "recrutamento" in active_groups:
        summary_parts.append(
            "Experiência em recrutamento e seleção, "
            "incluindo operações de alto volume."
        )

    if "td" in active_groups:
        summary_parts.append(
            "Experiência em treinamento, desenvolvimento "
            "e gestão de desempenho."
        )

    if "dados" in active_groups:
        summary_parts.append(
            "Utilização de Power BI, dashboards e indicadores "
            "para apoio à tomada de decisão."
        )

    if "gestao" in active_groups:
        summary_parts.append(
            "Experiência em liderança, coordenação e supervisão de equipes."
        )

    if "custos" in active_groups:
        summary_parts.append(
            "Histórico de otimização de processos e redução de custos."
        )

    if "trabalhista" in active_groups:
        summary_parts.append(
            "Experiência em legislação trabalhista, "
            "e-Social e relações trabalhistas."
        )

    tailored_summary = " ".join(
        summary_parts
    )

    # -----------------------------------------------
    # SCORE DE PERSONALIZAÇÃO
    # -----------------------------------------------

    experience_score = min(
        50,
        sum(
            item["relevance_score"]
            for item in ranked_experiences
        ) * 5,
    )

    skill_score = min(
        30,
        len(prioritized_skills) * 5,
    )

    keyword_score = min(
        20,
        len(active_groups) * 3,
    )

    personalization_score = min(
        100,
        experience_score
        + skill_score
        + keyword_score,
    )

    # -----------------------------------------------
    # RETORNO
    # -----------------------------------------------

    return {
        "job_title": job_title,

        "personalization_score":
            personalization_score,

        "active_areas":
            active_groups,

        "tailored_summary":
            tailored_summary,

        "prioritized_experiences":
            ranked_experiences,

        "prioritized_skills":
            prioritized_skills,

        "evidence":
            evidences,

        "next_action":
            "GERAR_CURRICULO",
    }
