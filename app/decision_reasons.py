"""
Dicionario de motivos de decisao em linguagem legivel para o usuario.
Fonte unica de traducao entre codigos internos e texto exibido.
"""

REASON_LABELS = {
    # Captura e qualidade
    "CONFIANCA_CAPTURA_BAIXA": "Nao consegui ler a vaga com seguranca",
    "CONFIANCA_AUSENTE": "Nao foi possivel medir a qualidade da captura",
    
    # Campos obrigatorios
    "MODALIDADE_AUSENTE": "A vaga nao informa se e presencial, hibrida ou remota",
    "LOCALIZACAO_AUSENTE": "A vaga nao informa a localizacao",
    
    # Score e autorizacao
    "SCORE_ABAIXO_MINIMO": "Aderencia ao seu perfil abaixo do minimo definido",
    "SEM_AUTORIZACAO": "Envio automatico nao autorizado para esta origem",
    
    # Duplicidade
    "DUPLICADA": "Voce ja tem esta vaga cadastrada",
    "PENDENCIA_ABERTA": "Ha uma pendencia a resolver antes de cadastrar",
    
    # Saude da vaga (0.24.0)
    "SAUDE_SUSPEITA": "Este anuncio tem sinais de vaga falsa ou golpe",
    "SAUDE_DUVIDOSA": "Este anuncio tem informacoes incompletas ou suspeitas",
    "VAGA_FANTASMA": "Este anuncio esta sendo republicado ha muito tempo",
    "BANCO_DE_TALENTOS": "Isto e um cadastro de reserva, nao uma vaga aberta",
    
    # Historico
    "MIGRACAO_HISTORICA": "Migrado do historico do sistema",
}


def get_reason_label(reason_code: str) -> str:
    """Retorna o texto legivel para um codigo de motivo."""
    return REASON_LABELS.get(reason_code, reason_code)


def get_reason_labels(reason_codes: list[str]) -> list[str]:
    """Retorna lista de textos legiveis para uma lista de codigos."""
    return [get_reason_label(code) for code in reason_codes]