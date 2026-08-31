"""
Registro de domínios de ATS (Applicant Tracking Systems) conhecidos.
Usado pelo módulo de saúde da vaga para identificar fontes confiáveis.
"""

# Domínios de ATS brasileiros e internacionais
ATS_DOMAINS = {
    # Brasileiros
    "gupy.io": "Gupy",
    "solides.com": "Solides",
    "vagas.com.br": "Vagas.com",
    "kenoby.com": "Kenoby",
    "taqe.com.br": "Taqe",
    "abler.com.br": "Abler",
    "inhire.app": "Inhire",
    "revelo.com.br": "Revelo",
    "empregos.com.br": "Empregos.com.br",
    "infojobs.com.br": "InfoJobs",
    "catho.com.br": "Catho",
    "bebee.com.br": "Bebee",
    "trabalhabrasil.com.br": "Trabalha Brasil",
    "curriculum.com.br": "Curriculum",
    "apinfo.com.br": "Apinfo",
    
    # Internacionais
    "linkedin.com": "LinkedIn",
    "indeed.com": "Indeed",
    "glassdoor.com": "Glassdoor",
    "monster.com": "Monster",
    "careerbuilder.com": "CareerBuilder",
    "ziprecruiter.com": "ZipRecruiter",
    "simplyhired.com": "SimplyHired",
    "dice.com": "Dice",
    "wellfound.com": "Wellfound (AngelList)",
    "remotive.io": "Remotive",
    "weworkremotely.com": "WeWorkRemotely",
    "remoteok.io": "RemoteOK",
    "flexjobs.com": "FlexJobs",
}

# Domínios de redirecionamento (menos confiáveis)
REDIRECT_DOMAINS = {
    "bit.ly",
    "tinyurl.com",
    "goo.gl",
    "ow.ly",
    "buff.ly",
    "short.link",
    "lnkd.in",
}

# Padrões de empresas confidenciais
CONFIDENTIAL_PATTERNS = [
    "confidencial",
    "grande empresa",
    "empresa de grande porte",
    "empresa do setor",
    "não divulgado",
    "a definir",
    "não informada",
]


def is_ats_domain(url: str) -> tuple[bool, str | None]:
    """
    Verifica se a URL é de um domínio ATS conhecido.
    Retorna (é_ats, nome_do_ats)
    """
    if not url:
        return False, None
    
    import re
    from urllib.parse import urlparse
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove www.
        if domain.startswith("www."):
            domain = domain[4:]
        
        for ats_domain, ats_name in ATS_DOMAINS.items():
            if ats_domain in domain:
                return True, ats_name
    except Exception:
        pass
    
    return False, None


def is_redirect_domain(url: str) -> bool:
    """Verifica se a URL é de um serviço de encurtamento."""
    if not url:
        return False
    
    from urllib.parse import urlparse
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain in REDIRECT_DOMAINS
    except Exception:
        return False


def is_confidential_company(company: str) -> bool:
    """Verifica se a empresa parece ser confidencial."""
    if not company:
        return True
    
    company_lower = company.lower().strip()
    for pattern in CONFIDENTIAL_PATTERNS:
        if pattern in company_lower:
            return True
    return False