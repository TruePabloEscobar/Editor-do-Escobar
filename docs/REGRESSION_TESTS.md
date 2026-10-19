# Testes de regressão locais

Execute `O Editor - Testes.cmd` na raiz ou, no terminal:

```powershell
.\.venv\Scripts\python.exe scripts/run_regression.py
```

Rode antes de cada commit e depois de mudanças de domínio, interface, scripts Lua,
plugin ou instalação. O processo retorna 0 somente quando todas as etapas passam
sem testes pulados. Uma dependência ausente ou um skip torna a execução FAILED.
Não instala dependências nem baixa modelos automaticamente.

## Preparação

Python 3.11 x64 na `.venv`, Node.js e FFmpeg/FFprobe no PATH e Windows PowerShell.
Instale as dependências de desenvolvimento explicitamente quando necessário:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

O extra dev inclui Lupa com Lua 5.1, permitindo executar os mesmos fixtures Lua
sem precisar de um executável Lua no PATH. A aplicação não depende de Lupa.

## Etapas obrigatórias

- `ruff check .`, `ruff format --check .`, `mypy src` e `pip check`.
- Pytest com cobertura mínima de 75% de domínio/application e JUnit.
- JavaScript real do plugin com API/Electron simulados: ordem de inicialização,
  inicialização recusada e ausência de objeto Resolve.
- Instalador em pastas sintéticas: hashes de JavaScript e módulo oficial divergentes,
  cópia íntegra e recusa de upgrade com módulo em uso antes de copiar arquivos.
- Lua real contra fake Resolve: leitura, sincronização, original imutável,
  validação sem mutação, bloqueios e convenções de inserção.
- Fluxo mock headless e self-test da interface e IPC.

APPDATA, LOCALAPPDATA e TEMP/TMP são isolados por execução dentro de
`runtime/regression`. O PSModulePath usado pelos subprocessos aponta para os módulos
do Windows PowerShell. A execução não instala plugins, não abre nem reinicia o
Resolve, não usa mídia do usuário e não aplica planos. O arquivo de cobertura também
fica no diretório da execução.

## Evidência

`runtime/regression/latest.json` aponta os resultados da última execução.
Cada execução tem `report.json`, `junit.xml`, `coverage.xml` e logs por etapa.
Os arquivos permanecem ignorados pelo Git.

A rotina é local e acionada pelo comando; não instala tarefas agendadas nem hooks.
Os testes marcados `resolve` ficam fora deste gate e precisam de uma rodada real
separada. API real e inferência em hardware são UNVERIFIED nesta rotina. Testes com
mocks não habilitam backends reais. Para verificar um plugin já instalado, execute
`scripts/install_workflow_integration.ps1 -VerifyOnly`. Para testar o host aberto
no Resolve, execute `scripts/test_internal_host.ps1`; esse teste é somente leitura.

## Regressões confirmadas e mídia OBS

O histórico rastreável, a baseline e as referências às leis estão em
`qa/regressoes/README.md`. A suíte inclui MOV gerado com FFmpeg real: duração
de áudio menor que vídeo, preservação de posição e silêncio na cauda, seleção
de canais em streams diferentes e bloqueio de trechos fora da mídia.
Arquivos reais do usuário e inferência CUDA são validações separadas do gate.

O caso BUG-0007 compara proveniência nativa de áudio separada do JSON de canais
na engine Lua simulada, com mídia compartilhada A1–A4 e faixa omitida. Isso impede
que uma leitura de metadados correta esconda a reinserção da primeira pista.
A escuta no Resolve continua sendo uma validação separada.

A recorrência longa de BUG-0001 está em tests/unit/test_speech_and_timing.py:
fontes de quase quatro horas, FPS fracionários, confirmação independente do relógio
no EOF e bloqueios para perda real, EOF ausente e tempo incompatível. O teste
preserva duração/posições e não depende de um arquivo longo ou do Whisper.
