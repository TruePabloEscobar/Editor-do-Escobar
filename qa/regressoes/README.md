# Registro de regressões

Referências canônicas lidas em 2026-10-19 (somente leitura):
- `T:\Skills & Mds\LEIS (Mds de cding)\LEI_BOAS_PRATICAS.md`
- `T:\Skills & Mds\LEIS (Mds de cding)\LEI_CONSISTENCIA_VISUAL.md`
- `T:\Skills & Mds\LEIS (Mds de cding)\LEI_NAO_REGRESSAO.md`

A suíte continua em `tests/`, sem duplicação de framework. Execute
`.venv/Scripts/python.exe scripts/run_regression.py`; detalhes em
`docs/REGRESSION_TESTS.md`. Os relatórios JSON, JUnit e cobertura ficam em
`runtime/regression`. Este registro não instala serviços ou CI.

Para cada bug confirmado: caso → teste RED → correção mínima → GREEN → gate.
Mídia real, API do Resolve e validação humana devem ser identificadas separadamente.
A identidade visual continua documentada em `docs/UI_WORKFLOW.md`.

Cópias rastreáveis das três leis: `leis/`, com SHA-256 do conteúdo canônico.
A matriz do projeto completo está em `docs/AUDITORIA_LEIS_2026-10-19.md`.
