# O Editor — instruções permanentes

- Leia `docs/O_EDITOR_PROJECT_SPEC.md` antes de qualquer alteração relevante.
- A timeline original é imutável. Aplicações reais exigem cópia criada e verificada.
- Não invente métodos da API do DaVinci Resolve. Use primeiro a documentação e os exemplos instalados da mesma versão.
- Toda capacidade real deve ser classificada como `SUPPORTED`, `UNSUPPORTED`, `UNVERIFIED` ou `FAILED`. Introspecção isolada não prova suporte.
- Backends reais só podem ser habilitados quando todas as operações necessárias foram executadas e verificadas pelo capability probe.
- Não edite o banco interno do Resolve e não use automação de mouse/teclado como backend padrão.
- O domínio não importa Resolve, PySide6, FFmpeg nem Whisper.
- Frames são a unidade editorial interna.
- Identificadores no código são em inglês; interface e mensagens ao usuário são em Português do Brasil.
- O modo `dry-run` é o padrão. Nunca declare uma operação aplicada sem verificação.
- Não baixe modelos de IA no startup nem sem clique explícito do usuário no botão de download, não versione modelos/mídia/cache/segredos e não registre transcrições completas por padrão.
- Use type hints nas APIs públicas; valide com `ruff check .`, `ruff format --check .`, `mypy src` e `pytest`.
- Quando o Resolve não estiver acessível, teste com mocks e registre hardware/API real como não executado.
- Antes de concluir alterações, execute `.venv/Scripts/python.exe scripts/run_regression.py`; o gate deve passar sem skips. Consulte `docs/REGRESSION_TESTS.md`. API real e hardware exigem validação separada.

- Leis canônicas e regressões: leia `qa/regressoes/README.md` e os três documentos externos referenciados antes de alterar; consulte `qa/regressoes/REGISTRO.md`.

- As três leis têm cópias integrais verificadas em `leis/` (manifesto SHA-256). A matriz de aplicação e os limites da auditoria estão em `docs/AUDITORIA_LEIS_2026-10-19.md`.
