# Changelog

## 0.2.0 — 2026-10-19

- Editor Do Escobar (EDE): navegação horizontal, knobs Tempo/Frames, modelo local
  e seleção CPU/GPU; Diagnóstico nas configurações, Zoom e Legendas separados.
- Download de modelo por clique explícito, cancelável e sem enviar mídia. Sobre
  com tutorial e créditos de Pablo Escobar.
- Limpeza opcional de microfones/retorno com proteção de falas simultâneas e
  reações; prova de cópias digitais e preservação da voz ao omitir a referência.
- Planejamento de mute indexado por faixa, com benchmark e mesmas decisões.
- ZIP Windows via script do Resolve, instalação versionada, SHA-256 e publicação
  em rascunho no GitHub; CI com o mesmo gate. Modelos/mídias/cache não incluídos.
- Pisos corrigidos de ferramentas de instalação/QA e regressões BUG-0021 a 0027.
- Limites: Zoom/texto permanecem em preflight; BUG-0017 do executor técnico real
  continua pendente. Esta rodada não aplicou Rough Cut nem realizou escuta.


Todas as mudanças relevantes deste projeto serão registradas aqui.

## [Unreleased]

- Captura somente leitura dos clipes de todas as tracks (layout schema 3) pelo host Lua.
- Reconstrução do áudio isolado de cada faixa a partir das mídias originais (FFmpeg),
  com validação do ponto de entrada e do mapeamento de canais.
- Transcrição individual por faixa (faster-whisper com VAD), detecção de fala
  simultânea e de vazamento entre microfones, descarte de alucinações sobre silêncio.
- Sessões de transcrição persistidas com IDs estáveis e revisões.
- Exportação e importação de TXT editável com validação e bloqueios.
- Planejamento global de cortes e limpeza de silêncios com prévia.
- `O Editor - Aplicar Rough Cut`: nova timeline por `DuplicateTimeline` +
  `AppendToTimeline`, com calibração e readback de cada operação.
- Aba "Transcrição e Rough Cut" na interface.
- Correções: config.json do `%APPDATA%` usado sem `O_EDITOR_CONFIG`; DLLs CUDA dos
  pacotes `nvidia-*`; ordem `Initialize`/`SetAPITimeout` do plugin Workflow Integration.

- Base Python com layout `src`, configuração, logging e CLI.
- Contratos tipados, serialização, fingerprint e timecode.
- Adapter mock e fluxo offline completo com cache.
- Providers de áudio e transcrição local sem download automático de modelos.
- Analisador heurístico determinístico e golden tests.
- Loader, capability probe e relatório real de capacidades.
- Planejador imutável, duplicação segura, aplicação verificada e relatórios.
- Interface PySide6 com revisão, edição, aprovação, cancelamento e dry-run.
- Launcher e scripts de instalação/diagnóstico para Windows.
