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
    domain = _validated_hostname(url)
    if domain is None:
        return False, None

    for ats_domain, ats_name in ATS_DOMAINS.items():
        if _hostname_matches_domain(domain, ats_domain):
            return True, ats_name

    return False, None


def is_redirect_domain(url: str) -> bool:
    """Verifica se a URL é de um serviço de encurtamento."""
    domain = _validated_hostname(url)
    return domain is not None and any(
        _hostname_matches_domain(domain, redirect_domain)
        for redirect_domain in REDIRECT_DOMAINS
    )


def _validated_hostname(url: str) -> str | None:
    """Return a safe normalized hostname from an absolute HTTP(S) URL."""
    from urllib.parse import urlparse

    if not isinstance(url, str) or not url or url != url.strip():
        return None
    # Browsers and HTTP clients can interpret backslashes and control
    # characters differently from urllib.parse, so reject ambiguous URLs.
    if "\\" in url or any(ord(char) < 0x20 or ord(char) == 0x7F for char in url):
        return None

    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return None
        # Never accept credentials, even if the hostname itself looks trusted.
        if "@" in parsed.netloc or parsed.username is not None or parsed.password is not None:
            return None
        hostname = parsed.hostname
        if not hostname:
            return None
        # Registry entries are ASCII DNS names. Reject Unicode separators and
        # lookalike labels instead of normalizing them into trusted domains.
        if not hostname.isascii():
            return None
        hostname = hostname.encode("idna").decode("ascii").lower()
        if hostname.endswith("."):
            hostname = hostname[:-1]
        if not hostname or any(not label for label in hostname.split(".")):
            return None
        # Force validation of malformed ports (e.g. :abc or out-of-range ports).
        _ = parsed.port
        return hostname
    except (UnicodeError, ValueError):
        return None


def _hostname_matches_domain(hostname: str, trusted_domain: str) -> bool:
    """Match only the trusted hostname itself or a true subdomain."""
    return hostname == trusted_domain or hostname.endswith("." + trusted_domain)


def is_confidential_company(company: str) -> bool:
    """Verifica se a empresa parece ser confidencial."""
    if not company:
        return True
    
    company_lower = company.lower().strip()
    for pattern in CONFIDENTIAL_PATTERNS:
        if pattern in company_lower:
            return True
    return False
