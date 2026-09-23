const fs = require('fs');
const puppeteer = require('puppeteer');
const marked = require('marked');
const path = require('path');

const markdownPath = path.join(__dirname, '..', 'livro_disc_hackeado.md');
const outDir = path.join(__dirname, '..', 'output_pdfs');

if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir);
}

const markdownContent = fs.readFileSync(markdownPath, 'utf8');
const htmlContent = marked.parse(markdownContent);

const css = `
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');

    :root {
        --bg-color: #0f1115;
        --text-color: #e2e8f0;
        --accent-color: #f59e0b; /* Amarelo/Laranja Hacker */
        --secondary-bg: #1e293b;
        --border-color: #334155;
    }

    body {
        font-family: 'Inter', sans-serif;
        background-color: var(--bg-color);
        color: var(--text-color);
        line-height: 1.6;
        margin: 0;
        padding: 40px;
        font-size: 14pt;
    }

    h1, h2, h3, h4 {
        color: var(--accent-color);
        font-weight: 800;
        margin-top: 1.5em;
        margin-bottom: 0.5em;
        line-height: 1.2;
    }

    h1 {
        font-size: 28pt;
        border-bottom: 2px solid var(--border-color);
        padding-bottom: 10px;
        page-break-before: always;
    }

    /* O primeiro h1 (Sumário) não precisa de quebra de página antes */
    h1:first-of-type {
        page-break-before: avoid;
    }

    h2 {
        font-size: 22pt;
    }

    h3 {
        font-size: 18pt;
    }

    p {
        margin-bottom: 1em;
    }

    strong {
        color: #fff;
        font-weight: 600;
    }

    ul, ol {
        margin-bottom: 1em;
        padding-left: 20px;
    }

    li {
        margin-bottom: 0.5em;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        margin: 2em 0;
        background-color: var(--secondary-bg);
        border-radius: 8px;
        overflow: hidden;
    }

    th, td {
        border: 1px solid var(--border-color);
        padding: 12px 15px;
        text-align: left;
    }

    th {
        background-color: #000;
        color: var(--accent-color);
        font-weight: 600;
    }

    blockquote {
        margin: 2em 0;
        padding: 1em 20px;
        border-left: 4px solid var(--accent-color);
        background-color: var(--secondary-bg);
        font-style: italic;
        border-radius: 0 8px 8px 0;
    }

    code {
        font-family: 'JetBrains Mono', monospace;
        background-color: var(--secondary-bg);
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.9em;
        color: #38bdf8;
    }

    hr {
        border: 0;
        height: 1px;
        background: var(--border-color);
        margin: 2em 0;
    }

    /* Cover Page Styles */
    .cover-page {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        height: 100vh;
        text-align: center;
        page-break-after: always;
        background-color: #000;
        color: #fff;
    }

    .cover-title {
        font-size: 48pt;
        color: var(--accent-color);
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-bottom: 20px;
        font-weight: 800;
    }

    .cover-subtitle {
        font-size: 20pt;
        color: #94a3b8;
        font-weight: 300;
        max-width: 80%;
    }

    .cover-author {
        margin-top: auto;
        margin-bottom: 50px;
        font-size: 16pt;
        font-weight: 600;
        letter-spacing: 1px;
    }

    /* Card de Bolso / Cheat Sheet Styles */
    .pocket-card {
        page-break-before: always;
        background-color: #000;
        padding: 30px;
        border: 2px solid var(--accent-color);
        border-radius: 12px;
        color: #fff;
    }

    .pocket-card h1 {
        text-align: center;
        font-size: 24pt;
        border-bottom: none;
        page-break-before: avoid;
    }

    .pocket-card-content {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 20px;
        font-size: 11pt;
    }

    .pocket-section {
        background-color: var(--secondary-bg);
        padding: 15px;
        border-radius: 8px;
        border-left: 3px solid var(--accent-color);
    }
    
    .pocket-section h3 {
        margin-top: 0;
        font-size: 14pt;
        border-bottom: 1px solid var(--border-color);
        padding-bottom: 5px;
    }
`;

const coverHtml = `
    <div class="cover-page">
        <h1 class="cover-title">Hackeando<br>o DISC</h1>
        <div class="cover-subtitle">O manual confidencial que o RH não quer que você leia. Como passar em qualquer teste comportamental e ser contratado.</div>
        <div class="cover-author">O Código Revelado</div>
    </div>
`;

const pocketCardHtml = `
    <div class="pocket-card">
        <h1>O CÓDIGO DISC - CHEAT SHEET</h1>
        <div class="pocket-card-content">
            <div class="pocket-section">
                <h3>[D] DOMINÂNCIA (Executor)</h3>
                <p><strong>A Vaga pede:</strong> Liderança, resultado, agilidade, decisão.</p>
                <p><strong>Gatilhos:</strong> "Decisão", "Resultados", "Controle", "Vencer".</p>
                <p><strong>O que evitar:</strong> Harmonia, lentidão, excesso de planejamento.</p>
            </div>
            <div class="pocket-section">
                <h3>[I] INFLUÊNCIA (Comunicador)</h3>
                <p><strong>A Vaga pede:</strong> Comunicação, negociação, carisma, relacionamento.</p>
                <p><strong>Gatilhos:</strong> "Equipe", "Motivar", "Entusiasmo", "Pessoas".</p>
                <p><strong>O que evitar:</strong> Trabalho isolado, foco extremo em planilhas/dados.</p>
            </div>
            <div class="pocket-section">
                <h3>[S] ESTABILIDADE (Planejador)</h3>
                <p><strong>A Vaga pede:</strong> Trabalho em equipe, rotina, paciência, suporte.</p>
                <p><strong>Gatilhos:</strong> "Harmonia", "Confiança", "Processos constantes".</p>
                <p><strong>O que evitar:</strong> Mudanças bruscas, riscos altos, decisões impulsivas.</p>
            </div>
            <div class="pocket-section">
                <h3>[C] CONFORMIDADE (Analista)</h3>
                <p><strong>A Vaga pede:</strong> Precisão, análise, regras, atenção a detalhes.</p>
                <p><strong>Gatilhos:</strong> "Lógica", "Qualidade", "Análise", "Precisão".</p>
                <p><strong>O que evitar:</strong> Intuição, regras quebradas, improviso.</p>
            </div>
        </div>
        <div style="margin-top: 20px; text-align: center; font-size: 10pt; color: #94a3b8;">
            <strong>REGRA DE OURO:</strong> Aplique 70% das respostas no perfil desejado + 30% em respostas neutras para não parecer forçado.
        </div>
    </div>
`;

const baseHtml = (content) => `
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Hackeando o DISC</title>
    <style>${css}</style>
</head>
<body>
    ${content}
</body>
</html>
`;

async function generatePDF(html, filename, format = 'A4') {
    const browser = await puppeteer.launch();
    const page = await browser.newPage();
    await page.setContent(html, { waitUntil: 'networkidle0' });
    
    await page.pdf({
        path: path.join(outDir, filename),
        format: format,
        printBackground: true,
        margin: {
            top: '20px',
            right: '20px',
            bottom: '20px',
            left: '20px'
        }
    });

    await browser.close();
    console.log(`Generated ${filename}`);
}

async function main() {
    try {
        // 1. Livro Completo (A4)
        const bookOnlyHtml = baseHtml(coverHtml + htmlContent);
        await generatePDF(bookOnlyHtml, 'Hackeando_DISC_Livro.pdf', 'A4');

        // 2. Card de Bolso (Formato menor, ex: A5)
        const pocketOnlyHtml = baseHtml(pocketCardHtml);
        await generatePDF(pocketOnlyHtml, 'Hackeando_DISC_Card_Bolso.pdf', 'A5');

        // 3. Livro com Card no final (A4)
        const bookWithCardHtml = baseHtml(coverHtml + htmlContent + pocketCardHtml);
        await generatePDF(bookWithCardHtml, 'Hackeando_DISC_Livro_Completo_Com_Card.pdf', 'A4');

        console.log("Todos os PDFs foram gerados com sucesso!");
    } catch (err) {
        console.error("Erro ao gerar PDFs:", err);
    }
}

main();
