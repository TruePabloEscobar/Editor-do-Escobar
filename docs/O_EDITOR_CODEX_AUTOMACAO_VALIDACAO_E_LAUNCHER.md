# O Editor — automação de validação, execução e instalação no DaVinci

Trabalhe no repositório existente. Antes de alterar arquivos, leia `AGENTS.md`, `docs/O_EDITOR_PROJECT_SPEC.md`, `README.md`, `docs/INSTALL_WINDOWS.md`, `docs/RESOLVE_API_NOTES.md` e `docs/RESOLVE_CAPABILITY_REPORT.md`. Execute `git status` e preserve alterações do usuário.

## Ambiente confirmado

- Projeto: `M:\J0ker\Codex Use\O editor APP`
- Python: `.venv\Scripts\python.exe`
- Runtime: Python 3.11.9, 64 bits
- Resolve: `C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe`
- API: `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules\DaVinciResolveScript.py`
- Biblioteca: `C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll`
- Documentação: `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\README.txt`

O probe atual termina sem mostrar saída:

```powershell
.\.venv\Scripts\python.exe -m o_editor.infrastructure.resolve.capabilities --root .
```

## Objetivo

Criar um fluxo de um clique que:

1. valide ambiente, lint, tipos e testes;
2. execute mock e integração read-only;
3. gere relatório consolidado;
4. instale o launcher no DaVinci;
5. crie arquivos `.cmd` para abrir, testar e instalar O Editor;
6. nunca execute mutações sem autorização explícita.

## Regras

- Não inventar métodos da API.
- Não usar automação de mouse/teclado.
- Não editar banco interno do Resolve.
- Não alterar a timeline original.
- Usar sempre `.venv\Scripts\python.exe`, nunca o Python global.
- `read-only` deve ser o padrão.
- Não afirmar sucesso sem verificar resultado.
- Não baixar FFmpeg ou modelos Whisper silenciosamente.
- Fazer commits pequenos.

## 1. Corrigir o probe silencioso

Revise `src/o_editor/infrastructure/resolve/capabilities.py`.

Garanta:

- função `main()`;
- bloco `if __name__ == "__main__":`;
- argparse funcional;
- stdout legível;
- logs;
- JSON e Markdown realmente gravados;
- exit code coerente.

Adicionar opções:

```text
--root PATH
--read-only
--allow-temporary-mutations
--json-output PATH
--markdown-output PATH
--verbose
--no-color
```

`--read-only` é o padrão. Mutações exigem flag explícita, projeto descartável e confirmação adicional.

O CLI deve sempre imprimir Python, Resolve, projeto, timeline, contagens `SUPPORTED`, `UNSUPPORTED`, `UNVERIFIED`, `FAILED`, caminhos dos relatórios e exit code.

Exit codes:

```text
0 sucesso
1 configuração/argumentos
2 falha de conexão
3 projeto ausente
4 timeline ausente
5 capability falhou
6 erro interno
```

## 2. Teste mínimo de conexão

Criar:

```text
src/o_editor/infrastructure/resolve/connection_test.py
scripts/test_resolve_connection.ps1
```

Validar em etapas:

1. Python 3.11 x64;
2. processo Resolve;
3. paths da API e DLL;
4. import de `DaVinciResolveScript`;
5. `scriptapp("Resolve")`;
6. versão;
7. project manager;
8. projeto ativo;
9. timeline ativa.

Configurar `RESOLVE_SCRIPT_API`, `RESOLVE_SCRIPT_LIB` e `PYTHONPATH` apenas para o processo atual.

Gerar:

```text
runtime/reports/resolve_connection_test.json
runtime/reports/RESOLVE_CONNECTION_TEST.md
```

Diferenciar claramente:

- Resolve fechado;
- módulo ausente;
- DLL não carregável;
- `scriptapp` retornando `None`;
- projeto ausente;
- timeline ausente.

## 3. Validação consolidada

Criar:

```text
scripts/validate_all.ps1
```

Parâmetros:

```text
-Mock
-SkipUnitTests
-SkipQuality
-SkipResolve
-ReadOnlyProbe
-AllowTemporaryMutations
-Verbose
```

Fluxo padrão:

1. validar `.venv`;
2. `ruff check .`;
3. `ruff format --check .`;
4. `mypy src`;
5. `pytest`;
6. `doctor.ps1`;
7. mock headless;
8. se Resolve estiver aberto, connection test e probe read-only;
9. se Resolve estiver fechado, marcar integração como `SKIPPED`;
10. gerar:

```text
runtime/reports/AUTOMATED_VALIDATION_REPORT.md
runtime/reports/automated_validation_report.json
```

Incluir commit, branch, working tree, Python, testes, cobertura, lint, mypy, mock, Resolve, connection test, capabilities, FFmpeg, Whisper, launcher, durações e próximos passos.

## 4. Arquivos de duplo clique

Criar na raiz:

```text
O Editor.cmd
O Editor - Mock.cmd
O Editor - Validar.cmd
O Editor - Instalar no DaVinci.cmd
```

### `O Editor.cmd`

- localizar a própria pasta;
- executar `.venv\Scripts\python.exe -m o_editor`;
- aceitar argumentos adicionais;
- registrar logs;
- manter mensagem legível em caso de falha.

### `O Editor - Mock.cmd`

Executar modo mock.

### `O Editor - Validar.cmd`

Executar `scripts\validate_all.ps1` e manter a janela aberta no final.

### `O Editor - Instalar no DaVinci.cmd`

Executar o instalador do launcher e mostrar o caminho instalado.

## 5. Instalador do launcher

Revisar ou substituir:

```text
scripts/install_launcher.ps1
```

Destino prioritário por usuário:

```text
%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility
```

Mas detectar caminhos e aceitar `-Destination`.

Instalar `O Editor.py` e criar:

```text
%APPDATA%\O Editor\launcher.json
```

Com:

```json
{
  "project_root": "M:\\J0ker\\Codex Use\\O editor APP",
  "python_executable": "M:\\J0ker\\Codex Use\\O editor APP\\.venv\\Scripts\\python.exe",
  "module": "o_editor",
  "schema_version": 1
}
```

O launcher deve usar somente stdlib, ler a configuração, validar caminhos, iniciar o app externo, impedir duplicação desnecessária, registrar `%APPDATA%\O Editor\launcher.log` e nunca importar PySide6 ou Whisper dentro do Resolve.

Criar:

```text
scripts/verify_launcher_installation.ps1
```

Verificar arquivo, configuração, Python, projeto e capacidade de iniciar o processo externo.

Documentar confirmação manual em:

```text
Workspace > Scripts > Utility > O Editor
```

Não afirmar que o menu apareceu sem verificação.

## 6. Contexto de lançamento pelo Resolve

Ao executar pelo menu:

1. ler versão, projeto e timeline quando disponíveis;
2. gravar `%TEMP%\o-editor\launch-context-{uuid}.json`;
3. iniciar:

```text
.venv\Scripts\python.exe -m o_editor --launch-context PATH
```

4. o app externo reconecta ao Resolve, compara contexto e mostra projeto/timeline;
5. não inicia análise automaticamente;
6. remove o arquivo temporário com segurança.

## 7. Self-test

Adicionar:

```text
o-editor --self-test
o-editor --self-test --resolve
```

O primeiro valida importações, config, cache, escrita, mock e UI básica. O segundo também valida conexão, projeto, timeline e leitura, sem mutações.

## 8. Orquestrador

Criar:

```text
scripts/bootstrap_validate_install.ps1
```

Parâmetros:

```text
-PythonPath
-RecreateVenv
-InstallDependencies
-InstallLauncher
-RunValidation
-StartResolve
-StartEditor
-Mock
```

Não recriar `.venv` ou instalar dependências sem flags explícitas.

## 9. Testes

Cobrir:

- CLI e exit codes;
- probe antes silencioso;
- relatórios;
- conexão mock;
- caminhos com espaços;
- arquivos `.cmd`;
- launcher stdlib-only;
- ausência de Resolve, projeto e timeline;
- DLL não carregável;
- `scriptapp` retornando `None`;
- contexto temporário;
- self-test;
- instalação e verificação do launcher.

## 10. Execução automática segura

Depois de implementar, execute:

1. lint;
2. format check;
3. mypy;
4. pytest;
5. mock headless;
6. doctor;
7. connection test, se Resolve estiver aberto;
8. probe read-only;
9. instalação do launcher;
10. verificação do launcher;
11. self-test;
12. relatório consolidado.

Não execute mutações no Resolve sem autorização explícita.

## 11. Documentação

Atualizar README, INSTALL_WINDOWS, RESOLVE_API_NOTES e TROUBLESHOOTING com um “Teste rápido”:

```text
1. Abra o Resolve.
2. Abra um projeto e uma timeline descartável.
3. Execute "O Editor - Validar.cmd".
4. Execute "O Editor - Instalar no DaVinci.cmd".
5. Reabra o Resolve se necessário.
6. Acesse Workspace > Scripts > Utility > O Editor.
7. Confirme projeto e timeline.
8. Use dry-run primeiro.
```

## Commits

```text
fix: make capability probe observable
feat: add automated Resolve connection test
feat: add consolidated validation workflow
feat: add double-click launchers
feat: harden DaVinci launcher installation
feat: add integrated launch context
feat: add application self-test
test: cover validation and launcher workflows
docs: document one-click testing workflow
```

## Entrega final

Informe arquivos criados/modificados, comandos executados, testes, relatório, conexão, probe, caminho instalado, como abrir pelo Resolve e por duplo clique, dependências pendentes, capabilities bloqueadas e commits.

Não finalize apenas escrevendo código: execute todas as verificações seguras disponíveis e mostre resultados reais.
