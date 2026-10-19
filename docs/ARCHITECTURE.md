# Arquitetura

## Fluxo principal

```text
DaVinci Resolve
  -> script Lua interno
  -> internal_common.run_internal_action (xpcall)
  -> resultado JSON + relatório Markdown + log
  -> request-UUID.json
  -> launch-editor.cmd --internal-action-request
  -> QLocalSocket
  -> instância única PySide6
  -> painel visível e foco da janela
```

O host Lua não importa `DaVinciResolveScript`, `fusionscript.dll`, PySide6,
FFmpeg ou Whisper. A UI não usa a bridge externa para processar as ações
internas.

## Limites de processo

- `domain`: regras puras em frames;
- `application`: análise, plano e relatório;
- `infrastructure`: arquivos, áudio e integrações;
- `internal_actions`: schema de request e IPC local;
- `ui`: revisão e feedback visível.

## Instância única

O nome do `QLocalServer` deriva do caminho normalizado do projeto. Invocações
subsequentes enviam uma mensagem JSON local e terminam. A instância ativa
processa requests em sequência, reconhece duplicatas e traz a janela para
frente.

## Segurança

1. Timeline original imutável.
2. Dry-run padrão.
3. Preflight de aplicação sem mutações.
4. `UNVERIFIED` nunca habilita backend.
5. Sem mouse/teclado e sem edição do banco interno.
6. Sem bridge FusionScript externa no fluxo interno.
7. Sem download silencioso de modelo ou FFmpeg.

## Seleção e áudio de voz

```text
launch-context schema 2
  -> AudioTrackSnapshot[]
  -> VoiceTrackSelector
  -> SelectedVoiceTrack[]
  -> VoiceTrackSettingsStore
  -> chave de cache (timeline + faixas + canal + backend + versão)
  -> InternalVoiceAudioExporter ou ManualAudioExporter
  -> transcrição
  -> sugestões
```

`domain.voice_tracks` contém contratos e scoring puros. A persistência e o cache pertencem à
infraestrutura. A UI apenas confirma seleção e canal. O exporter interno grava uma request de
preflight, mas recusa render enquanto todas as capabilities não forem comprovadas. O fallback
manual usa o mesmo cache e a mesma proveniência.

A estratégia temporária de enable/mute é uma possibilidade documentada, porém permanece
desabilitada. Ela só poderá ser implementada em projeto descartável, com snapshot, restauração
em `finally` e readback integral.

## Host persistente de requests

O host automático usa um Workflow Integration Plugin Electron oficial. O aplicativo externo
grava requests atômicas em `%APPDATA%\O Editor\resolve-internal-host`; o plugin faz polling,
executa apenas ações permitidas e grava resposta correlacionada. Ao fechar, interrompe o timer,
desregistra `ResolveQuit` e chama `WorkflowIntegration.CleanUp`.

Enquanto o ping real estiver `UNVERIFIED`, `export_voice_audio` permanece `UNSUPPORTED` e
nenhum render é iniciado.
