CREATE TABLE IF NOT EXISTS vagas (
    id SERIAL PRIMARY KEY,
    id_externo VARCHAR(255) NOT NULL,
    origem VARCHAR(50) NOT NULL,
    titulo VARCHAR(255) NOT NULL,
    empresa VARCHAR(255),
    localidade VARCHAR(255),
    tipo_modalidade VARCHAR(50) NOT NULL DEFAULT 'Não informado',
    tipo_contrato VARCHAR(100),
    url_candidatura TEXT NOT NULL,
    data_publicacao VARCHAR(100),
    tags TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_vaga_origem_externo UNIQUE (origem, id_externo)
);

CREATE INDEX IF NOT EXISTS idx_vagas_titulo
    ON vagas USING gin (to_tsvector('portuguese', titulo));
CREATE INDEX IF NOT EXISTS idx_vagas_modalidade
    ON vagas (tipo_modalidade);
CREATE INDEX IF NOT EXISTS idx_vagas_updated_at
    ON vagas (updated_at DESC);

CREATE TABLE IF NOT EXISTS candidatos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL,
    telefone VARCHAR(50),
    cargo_interesse VARCHAR(200) NOT NULL,
    modalidade_preferida VARCHAR(50) NOT NULL DEFAULT 'Todas',
    notificacoes_ativas BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_candidatos_email UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS idx_candidatos_email
    ON candidatos (email);

CREATE TABLE IF NOT EXISTS historico_alertas (
    id SERIAL PRIMARY KEY,
    candidato_id INTEGER NOT NULL,
    vaga_id INTEGER NOT NULL,
    tipo_alerta VARCHAR(80) NOT NULL DEFAULT 'nova_vaga',
    status VARCHAR(30) NOT NULL DEFAULT 'pendente',
    enviado_em TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_historico_alertas_candidato
        FOREIGN KEY (candidato_id) REFERENCES candidatos (id) ON DELETE CASCADE,
    CONSTRAINT fk_historico_alertas_vaga
        FOREIGN KEY (vaga_id) REFERENCES vagas (id) ON DELETE CASCADE,
    CONSTRAINT uq_candidato_vaga UNIQUE (candidato_id, vaga_id)
);

CREATE INDEX IF NOT EXISTS idx_historico_alertas_candidato
    ON historico_alertas (candidato_id);
CREATE INDEX IF NOT EXISTS idx_historico_alertas_vaga
    ON historico_alertas (vaga_id);
CREATE INDEX IF NOT EXISTS idx_historico_alertas_status
    ON historico_alertas (status);

-- These tables are server-managed; keep them protected from the public Data API.
ALTER TABLE IF EXISTS vagas ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS candidatos ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS historico_alertas ENABLE ROW LEVEL SECURITY;
