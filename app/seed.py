from .database import Base, SessionLocal, engine
from .models import Candidate, Experience, Skill


def seed():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        existing = db.query(Candidate).filter(
            Candidate.email == "henriqueoliveirarh93@gmail.com"
        ).first()

        if existing:
            print("Perfil já cadastrado.")
            return

        candidate = Candidate(
            name="Paulo Henrique Santos Oliveira",
            location="Salvador/BA",
            email="henriqueoliveirarh93@gmail.com",
            phone="(71) 99349-4443",
            linkedin="https://www.linkedin.com/in/paulo-oliveira-933a9254/",
            target_roles=(
                "Coordenador de RH, Coordenador de DP, "
                "Coordenador Administrativo, Supervisor de RH, "
                "Supervisor de DP, Supervisor Administrativo, "
                "Gerente de RH, Gerente de DP, Gente & Gestão, "
                "Relações Trabalhistas, Analista de RH/DP Sênior "
                "e cargos correlatos."
            ),
            summary=(
                "Especialista em Recursos Humanos Generalista e Estratégico, "
                "com mais de 10 anos de experiência em Coordenação de RH, "
                "Administração de Pessoal, R&S, T&D, Gestão Trabalhista, "
                "implantação de estruturas de RH, indicadores, Power BI, "
                "gestão de custos e conformidade."
            ),
        )

        db.add(candidate)
        db.flush()

        experiences = [
            Experience(
                candidate_id=candidate.id,
                company="Logic Soluções Logísticas",
                role="Coordenador de Departamento Pessoal",
                start_date="09/2025",
                end_date="Presente",
                description=(
                    "Liderança da migração da folha da contabilidade externa "
                    "para operação interna; parametrização de eventos; "
                    "revisão de encargos; integração contábil; governança; "
                    "controle de ponto; premiação; gestão de horas extras; "
                    "provisões; rateios por centro de custo; dashboards em Power BI. "
                    "Resultados: redução estimada de 18% nos custos administrativos, "
                    "35% nas inconsistências de ponto/folha, 12% no absenteísmo, "
                    "20% no custo mensal de horas extras e 15% nas variações de provisões."
                ),
            ),
            Experience(
                candidate_id=candidate.id,
                company="TPC Logística",
                role="Supervisor de Recursos Humanos",
                start_date="07/2022",
                end_date="08/2024",
                description=(
                    "Liderança da implantação de Centro de Distribuição da Avon, "
                    "com recrutamento e seleção de 400 colaboradores em dois meses. "
                    "Gestão de horas extras via Power BI, com redução de 25% e "
                    "economia estimada superior a R$ 8.000/mês. "
                    "Gestão de Gente & Gestão, T&D de liderança, avaliação de "
                    "performance e apresentações executivas de KPIs."
                ),
            ),
            Experience(
                candidate_id=candidate.id,
                company="Inovar Telecom",
                role="Supervisor Administrativo e Contratual",
                start_date="10/2024",
                end_date="09/2025",
                description=(
                    "Criação e implementação de dashboards gerenciais em Power BI, "
                    "incluindo indicadores de RH. Desenvolvimento de controles em "
                    "Excel e Visual Basic/macros, com redução de 30% no tempo de "
                    "rotinas documentais. Gestão contratual, documental e relatórios. "
                    "Otimização de rotas com redução de 12% nos custos logísticos."
                ),
            ),
            Experience(
                candidate_id=candidate.id,
                company="Luandre Temporários",
                role="Analista de Administração de Pessoal Pleno",
                start_date="12/2021",
                end_date="06/2022",
                description=(
                    "Administração de Pessoal de clientes de grande porte, "
                    "incluindo Mercado Livre, Amazon e Sephora. Alto volume de "
                    "admissões e demissões. Promoção a Analista Pleno após um mês "
                    "como Focal Point, com otimização de 35% no tempo de resposta. "
                    "Execução de processos de DP utilizando RM TOTVS."
                ),
            ),
            Experience(
                candidate_id=candidate.id,
                company="ASM - Associação Saúde em Movimento",
                role="Analista em Recursos Humanos",
                start_date="08/2020",
                end_date="10/2021",
                description=(
                    "Implantação de RH em novos contratos hospitalares em RJ, SP, "
                    "DF, TO e BA. Integração da folha de pagamento com e-Social. "
                    "Atuação como preposto em demandas trabalhistas e parceria "
                    "com jurídico para cálculos de acordos."
                ),
            ),
            Experience(
                candidate_id=candidate.id,
                company="Souza e Filhos",
                role="Coordenador de Recursos Humanos",
                start_date="01/2019",
                end_date="08/2020",
                description=(
                    "Implantação e adequação de parâmetros ISO 9001. "
                    "Redução de 27% no turnover e redução de 15% nos custos "
                    "operacionais por meio de indicadores de RH. "
                    "Internalização da folha no sistema Domínio e implantação "
                    "de programas de Trainee, Estágio, Jovem Aprendiz e PNE."
                ),
            ),
        ]

        skills = [
            ("Power BI", "Dados", "Avançado"),
            ("Dashboards e KPIs", "Dados", "Avançado"),
            ("Data Analytics", "Dados", "Avançado"),
            ("Excel", "Dados", "Avançado"),
            ("Visual Basic / Macros", "Dados", "Avançado"),
            ("RM TOTVS / Protheus", "Sistemas", "Avançado"),
            ("RM Labore", "Sistemas", "Avançado"),
            ("SAP", "Sistemas", "Experiência"),
            ("Domínio", "Sistemas", "Experiência"),
            ("Administração de Pessoal", "RH", "Avançado"),
            ("Folha de Pagamento", "RH", "Avançado"),
            ("Recrutamento e Seleção", "RH", "Avançado"),
            ("Treinamento e Desenvolvimento", "RH", "Avançado"),
            ("Avaliação de Desempenho", "RH", "Experiência"),
            ("Gestão de Equipes", "Gestão", "Avançado"),
            ("e-Social", "Compliance", "Experiência"),
            ("Legislação Trabalhista", "Compliance", "Experiência"),
            ("Atuação como Preposto", "Compliance", "Experiência"),
            ("ISO 9001", "Compliance", "Experiência"),
            ("Inglês", "Idiomas", "Leitura/Escrita Médio; Fala Iniciante"),
            ("Espanhol", "Idiomas", "Leitura Avançado; Escrita/Fala Médio"),
            ("Mandarim", "Idiomas", "Básico - em andamento"),
        ]

        for experience in experiences:
            db.add(experience)

        for name, category, proficiency in skills:
            db.add(
                Skill(
                    candidate_id=candidate.id,
                    name=name,
                    category=category,
                    proficiency=proficiency,
                )
            )

        db.commit()

        print("Perfil cadastrado com sucesso.")
        print(f"Candidate ID: {candidate.id}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()