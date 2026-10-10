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
    raw_data JSONB NOT NULL DEFAULT '{}'::JSONB,
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
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    owner_id VARCHAR(36),
    nome VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL,
    telefone VARCHAR(50),
    cargo_interesse VARCHAR(200) NOT NULL,
    localidade VARCHAR(200),
    modalidades TEXT[] NOT NULL DEFAULT '{}',
    termos_derivados TEXT[] NOT NULL DEFAULT '{}',
    plano VARCHAR(40) NOT NULL DEFAULT 'essencial',
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
    notas TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
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

-- Fase 1: contratos adicionais de integrações, candidaturas e observabilidade.
-- A migração idempotente em migrations/001_phase1_database_rls.sql também
-- cria as políticas granulares, índices compostos e triggers para instalações
-- já existentes.
CREATE TABLE IF NOT EXISTS integracoes_email (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    provedor VARCHAR(30) NOT NULL,
    email_conectado VARCHAR(320) NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(40) NOT NULL DEFAULT 'connected',
    ultima_sincronizacao TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_integracoes_email_user_provider UNIQUE (user_id, provedor)
);

CREATE TABLE IF NOT EXISTS candidaturas (
    id SERIAL PRIMARY KEY,
    candidato_id INTEGER NOT NULL REFERENCES candidatos(id) ON DELETE CASCADE,
    vaga_id INTEGER NOT NULL REFERENCES vagas(id) ON DELETE CASCADE,
    status VARCHAR(40) NOT NULL DEFAULT 'identificada',
    enviado_em TIMESTAMP WITH TIME ZONE,
    notas TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_candidatura_candidato_vaga UNIQUE (candidato_id, vaga_id)
);

CREATE TABLE IF NOT EXISTS logs_coleta (
    id SERIAL PRIMARY KEY,
    fonte VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_bruto INTEGER NOT NULL DEFAULT 0,
    total_salvo INTEGER NOT NULL DEFAULT 0,
    erro_detalhe TEXT,
    executado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metricas_sistema (
    id SERIAL PRIMARY KEY,
    fonte VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_bruto INTEGER NOT NULL DEFAULT 0,
    total_salvo INTEGER NOT NULL DEFAULT 0,
    erro_detalhe TEXT,
    executado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- These tables are server-managed; keep them protected from the public Data API.
ALTER TABLE IF EXISTS vagas ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS candidatos ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS historico_alertas ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS integracoes_email ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS candidaturas ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS logs_coleta ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS metricas_sistema ENABLE ROW LEVEL SECURITY;
