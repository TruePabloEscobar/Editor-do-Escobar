# Editor Do Escobar — EDE

Desenvolvido por [Pablo Escobar](https://pabloescobardj.web.app/Wikipedia-Pablo-Escobar.html).

Para instalar o plugin via script no Windows, baixe o ZIP da release, extraia e execute
**Instalar EDE.bat**. Requer Python 3.11 x64, FFmpeg/ffprobe no PATH e DaVinci Resolve
Studio 21. Na engrenagem, use **Baixar modelo…** e consulte **Sobre** para o tutorial.
[Distribuição, instalação e limites](docs/DISTRIBUICAO.md).

Assistente local de edição para DaVinci Resolve Studio 21.x. O Editor transcreve
cada faixa de áudio da timeline separadamente, exporta e importa transcrições em TXT
(editáveis por pessoas ou por IA), planeja cortes e silêncios na timeline global e
gera um rough cut em uma **nova** timeline. Também sugere zooms e textos.
A timeline original é imutável: aplicação real só pode ocorrer depois de uma
duplicação criada e verificada.

Estado operacional:

- aplicativo, mock, análise e exportação de plano funcionam offline;
- um launcher público O EDITOR abre a interface; os auxiliares produzem relatórios fora do menu;
- o probe persiste um snapshot canônico de capabilities validado por versão e contexto;
- requests internas são entregues à instância única por IPC local Qt;
- a bridge Python/FusionScript externa permanece isolada e desabilitada;
- `Aplicar Plano` (zoom/texto) é somente preflight e não executa mutações;
- `Aplicar Rough Cut` cria uma nova timeline verificada; a original nunca é alterada;
- FFmpeg e Whisper não são requisitos dos comandos internos.

## Abrir por duplo clique

O atalho **O EDITOR** abre o aplicativo pela Área de Trabalho ou pelo menu Iniciar.
Para recriar os atalhos, execute `scripts/install_shortcuts.ps1`.
A interface segue Faixas → Transcrição → Revisão → Prévia e cortes.
O contexto da timeline é carregado por `O EDITOR` dentro do Resolve.


- `O Editor.cmd`: modo offline;
- `O Editor - Mock.cmd`: dados simulados;
- `O Editor - Validar.cmd`: validação completa somente leitura;
- `O Editor - Instalar no DaVinci.cmd`: instala e verifica os scripts;
- `O Editor - Preparar e Testar.cmd`: dependências, launcher e testes.

Todos usam `.venv\Scripts\python.exe` com Python 3.11 x64.

## Instalar no DaVinci Resolve

```powershell
.\scripts\install_launcher.ps1
.\scripts\verify_launcher_installation.ps1
```

O menu contém somente **O EDITOR**. Os seis auxiliares Lua ficam em
`%APPDATA%\O Editor\internal-scripts`, fora da árvore de menus do Resolve.
O Host Interno técnico não fica listado nas Integrações de Fluxo de Trabalho.

`O Editor.py` não é instalado. Uma cópia antiga encontrada no Utility é movida
para `%APPDATA%\O Editor\legacy\O Editor.py`. Reinicie o Resolve depois de cada
instalação porque o menu pode permanecer em cache.

Cada ação grava uma request em `%APPDATA%\O Editor\requests` e chama:

```text
python -m o_editor --internal-action-request PATH
```

Se O Editor já estiver aberto, a request é entregue por `QLocalSocket`, a janela
recebe foco e nenhuma segunda instância permanece aberta.

## Desenvolvimento e validação

Execute `O Editor - Testes.cmd` antes de cada commit. O gate local roda qualidade,
testes Python/Lua/JavaScript, cobertura e IPC em dados isolados, sem acessar o Resolve.
Pré-requisitos e relatórios: [Testes de regressão](docs/REGRESSION_TESTS.md).

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m o_editor --mock --headless
.\.venv\Scripts\python.exe -m o_editor --self-test
.\scripts\validate_all.ps1 -SkipResolve
```

Simulações sem Resolve:

```powershell
.\.venv\Scripts\python.exe -m o_editor.internal_actions.simulate menu_test
.\.venv\Scripts\python.exe -m o_editor.internal_actions.simulate diagnostic
.\.venv\Scripts\python.exe -m o_editor.internal_actions.simulate capability_probe
.\.venv\Scripts\python.exe -m o_editor.internal_actions.simulate apply_plan
```

## Transcrição e Rough Cut

Guia completo: [Transcrição por faixa, TXT e Rough Cut](docs/TRANSCRIPT_ROUGH_CUT.md).

1. No Resolve: `O EDITOR` (captura os clipes de todas as tracks).
2. Aba **Transcrição e Rough Cut**: marque as faixas de voz e clique em
   **Transcrever faixas selecionadas**.
3. **Exportar transcrição** → um TXT por participante + `*_Completo.txt`.
4. Edite o TXT (manualmente ou com uma IA) e use **Importar transcrição editada**.
5. Ajuste a limpeza de silêncios, clique em **Gerar prévia** e depois em
   **Aplicar Rough Cut**.
6. O EDE tenta executar o helper automaticamente; se o Resolve recusar, use o menu `O EDITOR` conforme o aviso.

GPU: `.\.venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"`.

## Áudio e Whisper

`Selecionar WAV` permanece disponível offline. A exportação automática pelo
Resolve fica bloqueada até sua capability ser comprovada. O download de modelo
nunca ocorre no startup.

## Logs e relatórios

- `%APPDATA%\O Editor\logs`;
- `%APPDATA%\O Editor\requests`;
- `%APPDATA%\O Editor\reports`;
- `runtime\reports\AUTOMATED_VALIDATION_REPORT.md`;
- `runtime\reports\INTERNAL_ACTIONS_FIX_REPORT.md`;
- `runtime\reports\INTERNAL_ACTION_HYPOTHESES.md`.

O bundle de suporte é criado por:

```powershell
.\scripts\collect_internal_action_debug.ps1
```

Consulte [Ações internas do Resolve](docs/RESOLVE_INTERNAL_ACTIONS.md),
[Exportação automática de voz](docs/AUTOMATIC_VOICE_EXPORT.md),
[Instalação no Windows](docs/INSTALL_WINDOWS.md),
[Arquitetura](docs/ARCHITECTURE.md) e
[Solução de problemas](docs/TROUBLESHOOTING.md).

## Faixas usadas para voz

O launch-context interno schema 2 transporta todas as faixas de áudio disponíveis. A tela
principal permite confirmar uma ou várias faixas, mostra faixas mutadas, vazias e bloqueadas
e oferece `Ambos`, `Esquerdo`, `Direito` e `Converter para mono` quando o tipo estéreo foi
confirmado. A seleção é salva por projeto/timeline e participa do fingerprint e do cache.

Nomes como voz, diálogo, lapela, boom, host e convidado aparecem apenas como sugestão
visual. Música, efeitos, ambiente, master e mix recebem penalidade. No Resolve real nenhuma
faixa é marcada silenciosamente; no mock A2 e A3 formam a seleção demonstrativa.

A exportação automática real permanece bloqueada enquanto seleção de tracks, render WAV,
restauração e validação do arquivo não estiverem `SUPPORTED`. Nesse estado, `Analisar
timeline` cria uma request `export_voice_audio`, informa o gate e mantém `Selecionar WAV`
como fallback associado à mesma timeline e seleção. Nenhum estado de mute/solo é alterado.


O menu único abre a interface atual. Depois de confirmar Validar/Aplicar no app,
o EDE tenta despachar automaticamente o helper. Se precisar do fallback manual,
execute O EDITOR em até cinco minutos: ele consome a solicitação uma única vez.
Um plano salvo sozinho não dispara alterações ao abrir. Reinicie o Resolve depois
da atualização para limpar os itens de menu em cache.
