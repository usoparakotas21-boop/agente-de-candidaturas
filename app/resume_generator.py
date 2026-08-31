from typing import Any


def generate_resume(
    candidate: dict[str, Any],
    personalization: dict[str, Any],
) -> dict[str, Any]:

    name = candidate.get(
        "name",
        "Candidato",
    )

    contact = candidate.get(
        "contact",
        {},
    )

    summary = personalization.get(
        "tailored_summary",
        "",
    )

    prioritized_experiences = personalization.get(
        "prioritized_experiences",
        [],
    )

    prioritized_skills = personalization.get(
        "prioritized_skills",
        [],
    )

    # -------------------------------------------------
    # COMPETÊNCIAS
    # -------------------------------------------------

    skills = [
        item.get("skill", "")
        for item in prioritized_skills
        if item.get("skill")
    ]

    # Remove duplicidades preservando a ordem
    skills = list(dict.fromkeys(skills))
    if not skills:
        skills = list(dict.fromkeys(candidate.get("skills", [])))

    # -------------------------------------------------
    # EXPERIÊNCIAS
    # -------------------------------------------------

    experiences = []

    for experience in prioritized_experiences:

        experiences.append(
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
                "relevance_score": experience.get(
                    "relevance_score",
                    0,
                ),
            }
        )

    # -------------------------------------------------
    # OBJETIVO
    # -------------------------------------------------

    objective = candidate.get(
    "target",
    "Recursos Humanos",
)

    # -------------------------------------------------
    # CURRÍCULO
    # -------------------------------------------------

    resume = {
        "candidate": {
            "name": name,
            "phone": contact.get(
                "phone",
                "",
            ),
            "email": contact.get(
                "email",
                "",
            ),
            "linkedin": contact.get(
                "linkedin",
                "",
            ),
            "location": contact.get(
                "location",
                "",
            ),
        },

        "target": objective,

        "headline": candidate.get("headline") or "Perfil profissional",

        "summary": summary,

        "skills": skills,

        "experiences": experiences,

        "education": candidate.get("education", []),

        "languages": candidate.get("languages", []),

        "personalization": {
            "score": personalization.get(
                "personalization_score",
                0,
            ),
            "areas": personalization.get(
                "active_areas",
                [],
            ),
        },

        "next_action": "GERAR_DOCUMENTO",
    }

    return resume
