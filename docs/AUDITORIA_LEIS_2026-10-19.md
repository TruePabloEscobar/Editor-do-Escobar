# Auditoria das três leis — O Editor, 2026-10-19

Escopo: checkout completo T:/O editor APP, preservando alterações pré-existentes,
mídias, sessões e históricos. Leitura integral dos documentos canônicos concluída.
Referências rastreáveis em leis/manifest.json, cópias byte a byte iguais aos originais.
Esta instalação não altera os documentos canônicos e não cria serviço em segundo plano.

## Controles integrados em todo o projeto

| Área | Controle executável / evidência | Limite |
|---|---|---|
| Domínio, frames, plano, transcrição editável | pytest unitários/golden e cobertura domain/application | Inferência real de IA separada |
| Fronteira do domínio | test_architecture_boundaries.py impede Qt/Resolve/FFmpeg/Whisper/infra no domínio | Inspeção estática dos imports diretos |
| Áudio/FFmpeg/cache | testes com mídia sintética e streams; source_timing | Escuta humana não substituída por metadados |
| Interface PySide6 | botões reais Qt, navegação, IPC, réguas, unidades, atualização, pedidos | Qt offscreen; mouse nativo separado |
| Integração Lua | engine e helper reais contra fake Resolve, guardas e original imutável | Mock não habilita capacidades reais |
| Plugin Electron | testes JS de inicialização e instalação | Host técnico fora do menu público |
| Launcher/instaladores | testes em diretórios isolados; hashes na instalação real | Sem pacote executável novo ou CI remoto |
| Qualidade global | ruff, format, mypy src, pip check, pytest sem skips, mock e self-test | Comando local scripts/run_regression.py |
| Histórico de bugs | qa/regressoes/REGISTRO.md e casos individuais com RED/GREEN | Sem inventar defeitos históricos |
| API real | probes nomeados OE_TEST, original conferida antes/depois | Capacidade e arquivo/FPS específicos |

A identidade visual continua em ui/theme.py e docs/UI_WORKFLOW.md, com a paleta
aprovada. Referências e screenshots são somente leitura. Esta revisão não redesenha
telas nem troca dependências. Leis aplicam-se também a mudanças futuras via AGENTS.md.

## Defeitos confirmados nesta revisão

- BUG-0005, recorrência: taxa 23.976 arredondada acumula erro no in-point longo.
  Resolve interrompeu OP_00056, 55/250 operações, mantendo cópia incompleta.
- BUG-0009: início do plano vinha do getter truncado apesar do offset/tempo concordarem.
- BUG-0010: falha deixava a cópia incompleta ativa e alegava preservação sem conferência final.
- BUG-0011: slip e troca de canais não invalidavam o plano, com posição/ID iguais.
- BUG-0012: falha ao gravar recibo perdia correlação e a UI esperava indefinidamente.
- BUG-0013: janela fechada podia consumir replies em outro ciclo do mesmo QApplication.

RED e GREEN estão em runtime/reports/audit-*.xml. Caminhos e detalhes nos casos.
O arquivo da captura do usuário foi substituído no projeto durante o atendimento;
o plano/sessão/relatório anteriores foram preservados para diagnóstico. Probes
finais usam a mídia atualmente carregada, sem alterar a timeline original.

## Execução automática após confirmação

O botão Aplicar mantém confirmação explícita. Depois, publica plano e pedido de uso
único, e um worker descartável aciona a API Fusion para chamar o mesmo dispatcher
Lua. O dispatcher confere plan_id, modo, idade e confirmação antes de executar.
O pedido é consumido atomicamente uma única vez. Não existe retry automático em
resultado desconhecido, e resultado editorial só vem da conferência final da engine.
O ACK prova início, não conclusão. Cancelamento só vale antes de o pedido ser consumido.

Validar usa o mesmo caminho sem mutações. Em instalação/conexão indisponível, a UI
explica a falha; o menu único existente permanece como recuperação quando o pedido
ainda não foi consumido. Nenhum segundo menu ou automação de mouse foi criado.

## Pendências e prova de conclusão

Gate final PASSED e probe real concluídos; evidências abaixo. Não se afirma ausência
universal de bugs. Zoom/Fusion, textos, renderização, grades, transições, outros
formatos e aprovação sonora não foram validados por esta rodada. Cópias falhas
pré-existentes e arquivos originais permanecem preservados. Sem commit/push/deploy.

## Validação desta revisão — 2026-10-19

Proteções executadas: `runtime/reports/audit-focused-final.xml`, 76 aprovados.
Gate completo PASSED: 289 testes, zero falhas, erros e skips;
`runtime/regression/20261019T161142Z-8392628b/report.json`.
Ruff, formatação, mypy, dependências, mock e self-test também aprovados.
API real testada separadamente: execução automática VALIDATE sem mutações e
APPLY somente em `OE_TEST_AUDIT_AUTO`, 15/15 itens, vídeo + quatro áudios.
Leitura independente conferiu posições, duração, offset e canais distintos;
layout completo capturado da original idêntico antes/depois.
Evidências: `runtime/reports/audit-real-auto-validate.json`,
`audit-real-auto-apply.json`, `audit-real-readback.json` e
`audit-real-original-verified.json`.
Os cenários de erro injetado foram reproduzidos em testes automáticos, sem
provocar falhas deliberadas na timeline do usuário. Escuta/render: UNVERIFIED.
O MP4 da captura anterior já não estava no Media Pool; o probe real usou o MOV
atualmente disponível, 23.976 fps, com in-points longos. Sem commit/PR/push.

Instalação real conferida por SHA-256: um único menu público O EDITOR.
Janela atual reaberta pela integração privada e IPC activate respondeu ok=true.
