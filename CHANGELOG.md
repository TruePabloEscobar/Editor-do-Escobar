# Changelog

## Não publicado — 2026-10-22

- Crédito fixo, centralizado no rodapé da janela: "Desenvolvido por: Pablo Escobar",
  com link para o site do desenvolvedor (tests/ui/test_developer_credit.py).
- Zoom por take (etapa Zoom, opcional): um take a cada N com zoom fixo; zoom e
  frequência fixos ou em faixa com sorteio reproduzível; zoom de 1% a 10000% (abaixo
  de 100% diminui); ponto do zoom no centro por padrão e ajustável em X/Y; escolha de
  faixas de vídeo. Aplica junto com o Rough Cut ou depois, só em timelines criadas
  pelo O Editor, com conferência por leitura, reversão em falha e Desfazer (Ctrl+Z)
  em vários níveis. Scripts 2.5.0. Detalhes em docs/TAKE_ZOOM.md.
- A etapa Zoom deixou de mostrar as sugestões heurísticas de zoom (mudança pedida);
  Legendas mantém a lista de sugestões de texto.
- Inicialização: o script do menu deixou de abrir um cmd.exe por linha de log e por
  arquivo (28 → 1 processo por abertura na simulação; BUG-0029). Scripts 2.4.1.
- Sessões indexadas: abrir uma timeline não desserializa mais todas as sessões
  (BUG-0030). Verificação do FFmpeg fora da thread da interface (BUG-0031).
- Tempos de inicialização registrados como `startup_timing` em o-editor.log;
  benchmark reproduzível em scripts/benchmark_startup.py.
- Prévia: Frames antes de Tempo e selecionado por padrão; limpeza de
  microfones/retorno passou para a aba Silêncios.

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
