# Relatório — transcrição por faixa, TXT e Rough Cut

Data: 17/10/2026 · Resolve instalado: Studio 21.1 (docs de 31/08/2026) · Versão dos scripts: 2.3.0

## 1. O que já existia (reaproveitado)

- Host Lua interno funcionando no Resolve real, com relatórios gravados em
  `%APPDATA%\O Editor\reports`: lia projeto, timeline, FPS, frames, TC inicial e as
  faixas de áudio (nome, tipo, estado).
- App PySide6 com instância única via IPC, workers com cancelamento, seleção de faixas
  de voz persistida por timeline, cache, FFmpeg 8.1.2 configurado e provider
  faster-whisper com modelo `large-v3-turbo` local.
- Fluxo de sugestões de zoom/texto (mantido intacto, agora em uma aba própria).

## 2. O que estava incompleto ou quebrado

| Item | Situação encontrada | Resolução |
|---|---|---|
| Clipes da timeline | não eram lidos | captura completa e somente leitura (layout schema 3) |
| Áudio por faixa | export bloqueado (sem chave de render por track) | reconstrução por FFmpeg a partir das mídias originais |
| Ponte Python externa | access violation | continua desligada (não é necessária) |
| Workflow Integration | `SetAPITimeout` chamado antes de `Initialize` | ordem corrigida (não é usado no fluxo) |
| CUDA | `cublas64_12.dll` ausente → CPU | registro automático das DLLs `nvidia-*`; instalação documentada |
| config.json do `%APPDATA%` | ignorado sem `O_EDITOR_CONFIG` | usado como fallback |
| TXT, importação, cortes, silêncio | inexistentes | implementados |

Fato decisivo da API 21.1: **não existe função de lâmina/split**. Por isso não é possível
cortar dentro de um clipe numa cópia. A estratégia escolhida é `DuplicateTimeline` →
limpar somente a cópia → reconstruir com `AppendToTimeline`, conferindo cada item.

## 3. O que foi implementado

- `domain/timeline_layout.py`: tracks e clipes, lacunas, validação e fingerprint.
- `domain/source_timing.py`: ponto de entrada na mídia aceito somente com leituras concordantes.
- `infrastructure/audio/track_renderer.py`: WAV 16 kHz por faixa, alinhado por amostra, com mapeamento de canais.
- `infrastructure/audio/signal.py`: níveis RMS, atividade adaptativa e nível por trecho.
- `infrastructure/transcription/track.py`: faster-whisper (VAD, modelo carregado uma vez, fallback em CPU) e mock por sinal.
- `domain/speech.py`: trechos com participante, IDs estáveis, sobreposição, vazamento e sessão.
- `application/transcribe_tracks.py`: orquestração, cache e descarte de alucinações.
- `domain/transcript_document.py` e `application/transcript_exchange.py`: TXT, parser tolerante, revisão com bloqueios e trechos ausentes.
- `domain/intervals.py` e `domain/rough_cut.py`: plano global, silêncio e operações de reconstrução.
- `application/rough_cut.py`: prévia e plano para o Resolve.
- `launcher/internal_common.lua` e `launcher/O Editor - Aplicar Rough Cut.lua`: motor de aplicação com calibração e readback.
- `ui/transcript_panel.py`: aba "Transcrição e Rough Cut".

## 4. Testes

`pytest`: **178 passaram, 11 ignorados** (os ignorados exigem PowerShell/Windows). `ruff`
está limpo. O `mypy` mantém os mesmos 3 apontamentos que já existiam antes (dependentes
do ambiente).

| Teste | Resultado | Como foi testado |
|---|---|---|
| A — 4 tracks → 4 transcrições | PASSOU | mídia sintética + render real por FFmpeg + mock por sinal |
| B — fala no minuto 15 com tempo absoluto | PASSOU | clipe em 14:50 com in-point de 30 s → 15:00:00 (±1 frame) |
| C — export/import sem alteração | PASSOU | nenhum CUT, ausência ou correção |
| D — CUT → intervalo exato | PASSOU | intervalo removido = intervalo do trecho |
| E — silêncio | PASSOU | pausa longa removida com margens; fala intacta |
| F — falas simultâneas | PASSOU | parte do CUT sobreposta à fala de outra pessoa é preservada |
| G — sincronização | PASSOU | mesmo deslocamento em todas as tracks; câmera = duração final |
| H — original intacta | PASSOU (simulado) | Lua real contra Resolve simulado: a original só serviu de origem para `DuplicateTimeline` |

**Não testado no Resolve real** (depende de execução manual): leitura dos clipes pela API
21.1, comportamento real de `AppendToTimeline`, `SetSourceAudioChannelMapping`, cópia de
propriedades, marcadores, transcrição real com o modelo `large-v3-turbo` em CUDA e o
desempenho em timelines longas.

## 5. Limitações conhecidas

- A nova timeline não recebe grades de cor, composições Fusion, transições, keyframes
  nem efeitos de track; legendas ficam vazias.
- Clipes com velocidade diferente de 100% não são reconstruídos: em faixas de áudio isso
  bloqueia o plano, em vídeo gera aviso.
- A limpeza de silêncio considera somente as faixas transcritas. Música em "Cortar
  junto" é cortada nos mesmos pontos; use "Omitir" para recolocá-la depois.
- Uma operação de `AppendToTimeline` por item (timelines muito longas podem levar alguns
  minutos; o Resolve fica ocupado durante a aplicação).
- O vazamento entre microfones exige diferença de nível de pelo menos 6 dB; casos
  ambíguos são mantidos e apontados.
- A aplicação é acionada pelo menu do Resolve (dois passos), porque a ponte externa
  continua instável.

## 6. O que falta para o fluxo funcionar de ponta a ponta

1. Rodar `O Editor - Instalar no DaVinci.cmd` (instala `Aplicar Rough Cut.lua` e o novo
   `internal_common.lua`) e **reiniciar o Resolve**.
2. (GPU) `.\.venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"`.
3. Executar o teste manual de `docs/TRANSCRIPT_ROUGH_CUT.md` §7 em uma timeline de
   teste e registrar o resultado. A calibração detecta as convenções de
   `AppendToTimeline`; se algo divergir, a cópia fica como `_FALHOU` e o log indica a operação.
4. Opcional: avaliar `ResolvePython.exe` (21.1) para acionar o rough cut direto do app,
   sem o passo pelo menu.
