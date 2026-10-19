# Exportação automática de voz

## Estado atual

O protocolo persistente foi implementado como **Workflow Integration Plugin**, a rota
oficial documentada para um processo Electron carregado pelo Resolve Studio. O plugin:

- usa o `WorkflowIntegration.node` copiado da instalação local do Resolve;
- inicializa por `WorkflowIntegration.Initialize` e obtém o Resolve por `GetResolve`;
- processa requests JSON locais por polling de 500 ms;
- publica estados e respostas correlacionadas;
- registra `ResolveQuit`, interrompe o polling e chama `CleanUp`;
- não importa PySide6, FFmpeg ou Whisper;
- não usa internet, bridge FusionScript externa nem automação de GUI;
- responde `UNSUPPORTED` a `export_voice_audio` enquanto o probe mutável não existir.

O plugin instalado só é enumerado no startup do Resolve. A instalação e o hash do módulo
oficial foram verificados, mas o ping real permaneceu `UNVERIFIED` porque o Resolve já estava
aberto. Isso é um gate: nenhum render automático foi implementado ou executado.

## Protocolo local

```text
%APPDATA%\O Editor\resolve-internal-host
  requests\host-request-<uuid>.json
  jobs\host-job-<uuid>.json
  responses\host-response-<uuid>.json
  logs\workflow-integration.log
  host-status.json
```

Estados: `PENDING -> RUNNING -> SUCCEEDED | FAILED | CANCELLED | UNSUPPORTED`.

`SUPPORTED` para o host só é emitido quando o aplicativo grava um ping, o plugin ativo o
consome e devolve `pong=true` junto ao contexto lido da API oficial.

## Gate de render

| Estratégia | Estado | Motivo |
|---|---|---|
| Seleção direta de tracks | `UNSUPPORTED` | Não há chave documentada em `SetRenderSettings`. |
| Seleção por bus | `UNVERIFIED` | Nenhuma API aplicável foi provada. |
| Timeline temporária duplicada | `UNVERIFIED` | `DuplicateTimeline` é mutável e não foi executado. |
| Enable/disable temporário | `UNVERIFIED` | Exige snapshot, restauração e readback mutáveis. |
| WAV manual | `SUPPORTED` offline | Validação PCM, duração, cache e proveniência possuem testes. |

O primeiro teste mutável deverá ocorrer somente em projeto e timeline iniciados por
`OE_TEST_`, com confirmação humana, snapshot completo, `finally`, restauração e readback.

## Dependências locais

- FFmpeg/FFprobe 8.1.2: pacote `Gyan.FFmpeg` do winget, caminhos explícitos no
  `config.json`, fixture temporária validada e removida.
- faster-whisper 1.2.1: modelo local `large-v3-turbo`, `local_files_only=True`; inferência
  local passou no fallback CPU, mas CUDA falhou por ausência de `cublas64_12.dll`.
- cache real: `%APPDATA%\O Editor\cache`; mock: `runtime\cache`.

## Comandos

```powershell
.\scripts\install_workflow_integration.ps1
.\scripts\test_internal_host.ps1
.\scripts\test_ffmpeg.ps1
.\scripts\test_whisper.ps1
.\scripts\test_voice_export_mock.ps1
.\scripts\collect_voice_export_debug.ps1
```
