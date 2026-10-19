# Ações internas do DaVinci Resolve

## Escopo

Os cinco comandos instalados em `Workspace > Scripts > Utility` usam Lua no
processo do Resolve e encaminham resultados para o aplicativo PySide6 externo:

- `O Editor - Abrir`;
- `O Editor - Teste de Menu`;
- `O Editor - Diagnóstico`;
- `O Editor - Capability Probe`;
- `O Editor - Aplicar Plano`;
- `O Editor - Aplicar Rough Cut` (única ação com mutações; atua somente na cópia).

O launcher Python antigo não faz parte do menu. Se encontrado, o instalador o
move para `%APPDATA%\O Editor\legacy\O Editor.py`.

## Contrato de execução

Cada Lua cria o log mínimo antes de carregar o helper. Depois,
`internal_common.run_internal_action`:

1. registra versão, build, script, diretório de trabalho, `APPDATA` e `TEMP`;
2. obtém o objeto interno do Resolve sem importar `DaVinciResolveScript`;
3. executa a ação dentro de `xpcall`;
4. grava JSON e Markdown em `%APPDATA%\O Editor\reports`;
5. grava `request-{uuid}.json` em `%APPDATA%\O Editor\requests`;
6. chama o mesmo `%APPDATA%\O Editor\launch-editor.cmd`;
7. passa `--internal-action-request "<arquivo>"`.

Os estados da request são `SUCCESS`, `BLOCKED`, `FAILED`, `CANCELLED` e
`UNSUPPORTED`. Resultados do capability probe usam `SUPPORTED`, `UNSUPPORTED`,
`UNVERIFIED` e `FAILED`.

O probe também substitui atomicamente o snapshot canônico
`%APPDATA%\O Editor\internal-capabilities.json`. Diagnóstico e preflight só
aceitam esse arquivo quando schema, modo `READ_ONLY`, ausência de mutações,
versão, build e contexto correspondem à execução atual. Um snapshot antigo ou
incompatível não habilita backend.

## Objeto Resolve interno

A versão instalada da documentação oficial (`Developer\Scripting\README.txt`,
atualizada em 15 de julho de 2026) e os exemplos Lua usam `Resolve()`. O helper
inspeciona e verifica, nesta ordem:

1. objeto global `resolve`;
2. objeto global `app`, quando ele próprio é compatível com Resolve;
3. `app.GetResolve`, somente se o host realmente expuser o membro;
4. função global documentada `Resolve()`.

Cada candidato só é aceito depois de `GetProjectManager` retornar um objeto. O
helper registra a origem escolhida. Não existe fallback para a bridge externa,
`scriptapp` ou `fusionscript.dll`.

## Instância única e IPC

O aplicativo usa `QLocalServer` e `QLocalSocket`, sem rede externa. Uma segunda
invocação encaminha a mensagem à instância existente e termina. Mesmo se
`launcher.json` estiver ausente ou inválido, o helper registra o problema e
reutiliza o `launch-editor.cmd` instalado para apresentar a falha na interface.
A instância
ativa:

- atualiza projeto, timeline e frame rate;
- exibe o resultado;
- restaura e traz a janela para frente;
- grava um marcador em `requests\processed`;
- reconhece requests repetidas sem executar novamente o resultado.

O protocolo aceita `launch_context`, `internal_action_request`, `show_report`,
`show_message`, `diagnostic_result`, `capability_result` e `apply_result`.

## Aplicar Plano

`O Editor - Aplicar Plano` é apenas um preflight. Ele valida o que está
disponível no plano e nas capabilities internas, mas nunca chama métodos de
mutação. Sem plano, sem duplicação `SUPPORTED`, com contexto divergente ou sem
readback do fingerprint, o status é bloqueado e a UI explica o motivo.

## Aplicar Rough Cut

Lê `plans\rough-cut-pending.json` (gerado pela aba Transcrição e Rough Cut), valida a
timeline ativa clipe a clipe e, somente no modo APPLY confirmado, cria a nova timeline
com `DuplicateTimeline`, limpa apenas a cópia e a reconstrói com `AppendToTimeline`,
conferindo cada item. Detalhes em [TRANSCRIPT_ROUGH_CUT.md](TRANSCRIPT_ROUGH_CUT.md).

## Simulação sem Resolve

```powershell
.\.venv\Scripts\python.exe -m o_editor.internal_actions.simulate menu_test
.\.venv\Scripts\python.exe -m o_editor.internal_actions.simulate diagnostic
.\.venv\Scripts\python.exe -m o_editor.internal_actions.simulate capability_probe
.\.venv\Scripts\python.exe -m o_editor.internal_actions.simulate apply_plan
```

Cada comando cria uma request compatível, entrega-a por IPC a um receptor
offscreen, confirma o resultado e encerra o receptor. Nenhuma timeline é
necessária ou alterada.

## Cache do menu

O Resolve enumera os scripts no startup. Depois de instalar, reinicie o Resolve
antes do teste manual. O instalador nunca encerra o Resolve automaticamente e
não declara que o código novo foi executado apenas porque os hashes coincidem.

## Teste manual final

1. Feche completamente o DaVinci Resolve.
2. Abra novamente.
3. Abra um projeto e timeline.
4. Execute `Workspace > Scripts > Utility > O Editor - Teste de Menu`.
5. Confirme que O Editor abre ou recebe foco e exibe `Teste de menu concluído`.
6. Execute `O Editor - Diagnóstico` e confirme o diagnóstico interno.
7. Execute `O Editor - Capability Probe` e confirme a tabela somente leitura.
8. Execute `O Editor - Aplicar Plano` e confirme o bloqueio visível esperado.
9. Execute `O Editor - Abrir` e confirme que a janela existente recebe foco.

Esse teste permanece não aprovado até a confirmação manual do usuário.
