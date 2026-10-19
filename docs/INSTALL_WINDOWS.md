# Instalação no Windows

## Requisitos

- Windows 11;
- Python 3.11 x64 em `.venv\Scripts\python.exe`;
- DaVinci Resolve Studio 21.x para o host interno.

## Instalar e verificar

```powershell
.\scripts\install_launcher.ps1
.\scripts\verify_launcher_installation.ps1
```

Destino dos scripts:

```text
%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility
```

Arquivos instalados:

- `O EDITOR.lua` (único item visível).

Os auxiliares ficam em `%APPDATA%\O Editor\internal-scripts`.

Auxiliares:

```text
%APPDATA%\O Editor\internal_common.lua
%APPDATA%\O Editor\launch-editor.cmd
%APPDATA%\O Editor\launcher.json
%APPDATA%\O Editor\logs
%APPDATA%\O Editor\requests
%APPDATA%\O Editor\reports
%APPDATA%\O Editor\plans
```

O instalador valida UTF-8 sem BOM e SHA-256. `O Editor.py` não é instalado; uma
cópia antiga é movida para `%APPDATA%\O Editor\legacy\O Editor.py` antes de ser
removida do menu no próximo restart do Resolve.

## Testar

Reabra o Resolve e execute somente **Workspace > Scripts > O EDITOR**.
Confira o projeto, a timeline e a interface atual. Instalação e hash corretos
não provam a execução manual dentro do Resolve.

## Desinstalar

Use primeiro a prévia:

```powershell
.\scripts\uninstall_windows.ps1 -WhatIf
.\scripts\uninstall_windows.ps1
```

Faça backup de planos e relatórios antes de usar `-RemoveUserConfig`.

## Atualização para seleção de faixas

A versão interna `2.2.0` usa launch-context schema 2. Reinstale e reinicie o Resolve para
descartar módulos Lua antigos em cache:

```powershell
.\scripts\install_launcher.ps1
.\scripts\verify_launcher_installation.ps1
```

Depois execute `O EDITOR`. A seção **Faixas usadas para voz** deve listar A1, A2 etc.
Se a exportação automática estiver bloqueada, selecione as faixas, clique em analisar para o
preflight e use `Selecionar WAV` como fallback.

## Instalar o host persistente

```powershell
# Somente para desenvolvimento explícito: reativa um segundo item técnico.
.\scripts\install_workflow_integration.ps1
```

O instalador copia o código e o `WorkflowIntegration.node` oficial local para a pasta de
Workflow Integration Plugins em `%PROGRAMDATA%`. O binário não é versionado. Salve o projeto,
reinicie o Resolve, abra `Workspace > Workflow Integrations > O Editor - Host Interno` e rode
`.\scripts\test_internal_host.ps1`. Instalação e hashes não substituem o ping real.


## Atalho O EDITOR

Execute `scripts/install_shortcuts.ps1` para criar os atalhos na Área de Trabalho
e no menu Iniciar. Eles usam o Python da `.venv` sem janela de console e abrem
somente O Editor. Para carregar a timeline ativa, use `O EDITOR` no Resolve;
a instância única recebe o contexto. Após atualizar a interface, feche e reabra
apenas O Editor para carregar o novo visual.


O menu único abre a interface atual. Depois de confirmar Validar/Aplicar no app,
execute O EDITOR em até cinco minutos: ele consome essa solicitação uma única vez.
Um plano salvo sozinho não dispara alterações ao abrir. Reinicie o Resolve depois
da atualização para limpar os itens de menu em cache.
