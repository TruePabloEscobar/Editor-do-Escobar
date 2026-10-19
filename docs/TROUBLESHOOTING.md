# Solução de problemas

## O item do menu parece não fazer nada

Consulte `%APPDATA%\O Editor\logs\<ação>.log`, depois verifique
`%APPDATA%\O Editor\requests`. Toda ação nova deve criar ambos. Reinstale se os
hashes divergirem:

```powershell
.\scripts\install_launcher.ps1
.\scripts\verify_launcher_installation.ps1
```

Reinicie o Resolve; o menu é enumerado no startup.

## Ainda aparece um item chamado apenas O Editor

Feche e reabra o Resolve. O instalador move
`Utility\O Editor.py` para `%APPDATA%\O Editor\legacy\O Editor.py`. O verificador
falha se o Python antigo continuar instalado.

## A interface não abre

Verifique:

- `%APPDATA%\O Editor\launcher.json`;
- `%APPDATA%\O Editor\launch-editor.cmd`;
- `%APPDATA%\O Editor\launcher-external.log`;
- `.venv\Scripts\python.exe`;
- o hash de `internal_common.lua`.

Execute:

```powershell
.\.venv\Scripts\python.exe -m o_editor --self-test
.\.venv\Scripts\python.exe -m o_editor.internal_actions.simulate menu_test
```

## Uma instância aberta não atualiza

O self-test IPC e as simulações devem terminar com `IPC: PASSED`. Requests
processadas deixam marcadores em `%APPDATA%\O Editor\requests\processed`.

## `Aplicar Plano` está bloqueado

É esperado sem plano aprovado, com projeto/timeline divergentes, sem readback do
fingerprint ou enquanto `duplicate_timeline` não for `SUPPORTED`. Execute antes
`O Editor - Capability Probe` para atualizar
`%APPDATA%\O Editor\internal-capabilities.json`; snapshots antigos, de outra
versão ou de outro contexto são recusados. O preflight sempre informa o motivo
e nunca altera a timeline original.

## Aviso `QFontDatabase`

O aviso vinha do plugin Qt `offscreen`, que procurava a antiga pasta
`PySide6\Lib\fonts`. O self-test e o simulador agora apontam
`QT_QPA_FONTDIR` para a pasta de fontes do Windows. Nenhuma fonte é copiada ou
versionada.

## Bridge FusionScript

`0xC0000005` pertence à bridge externa experimental. Ela continua desabilitada e
não participa dos comandos internos.

## As faixas de voz não aparecem

Reinstale os scripts `2.2.0`, reinicie o Resolve e execute `O Editor - Abrir`. Um contexto antigo
schema 1 não contém `audio_tracks`. Se a timeline mudar, abra novamente pelo menu para atualizar
a lista. Faixas removidas ou renomeadas geram aviso e não são selecionadas por índice inválido.

## Exportação automática das faixas indisponível

É o estado seguro enquanto as capabilities de seleção/render/restauração estiverem
`UNVERIFIED`. O Editor salva uma request de preflight em `%APPDATA%\O Editor\requests`, não
altera mute/solo e solicita um WAV da mesma timeline. O WAV permanece associado à seleção
enquanto existir e o fingerprint continuar compatível.

FFmpeg/FFprobe ausentes não afetam a seleção. A validação PCM interna continua disponível;
normalização ou inspeção adicional por FFmpeg só ocorre quando os executáveis forem fornecidos.

## O host persistente não responde

O Resolve enumera Workflow Integrations no startup. Instale o plugin, salve o projeto,
reinicie o Resolve e abra `Workspace > Workflow Integrations > O Editor - Host Interno`.
Depois execute `scripts\test_internal_host.ps1`. Um timeout mantém a capability `UNVERIFIED`;
não habilita render nem mutação.

## FFmpeg instalado, mas o doctor não encontra

Use `scripts\test_ffmpeg.ps1`. O Editor lê `ffmpeg.ffmpeg_path` e
`ffmpeg.ffprobe_path` de `%APPDATA%\O Editor\config.json`, além das variáveis e do `PATH`.
