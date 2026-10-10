# Candidatura Certa · vídeo institucional

Composição Remotion em 1920×1080, 30 FPS e 3.600 frames exatos (120 segundos).

## Executar

```bash
cd motion-video
npm install
npm run start
npm run build-video
```

O render completo gera `candidatura_certa_apresentacao.mp4`. A composição `CandidaturaCerta` já contém as sete cenas na timeline solicitada.

## Organização

- `src/scenes/`: uma cena por bloco narrativo.
- `src/components/`: moldura de navegador, cards glass, logo, cursor e camada de transição.
- `src/audio/sfxMarkers.ts`: marcadores de clique, transição e sucesso em frames absolutos. A camada `SfxMarkers` os exibe durante a revisão; arquivos de áudio reais podem ser associados depois sem alterar a timeline.
- `src/Root.tsx`: composição de 3.600 frames e sequência das cenas.

Os mockups são desenhados em React para manter o vídeo reproduzível sem depender de uma sessão autenticada do site em produção.
