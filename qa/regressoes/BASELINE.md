# Baseline — 2026-10-19

Checkout T:/O editor APP com alterações pré-existentes preservadas (81 entradas no status).
Antes da correção: gate `PASSED`, 205 testes; relatório `T:/O editor APP/runtime/regression/20261019T132445Z-e94a400c/report.json`.
Ruff, formatação, mypy, dependências, mock e self-test foram executados.

O gate anterior não cobria mídia MOV com múltiplos streams de áudio e cauda
menor que o vídeo. Falhas confirmadas nesta tarefa: BUG-0001 e BUG-0002.
Não houve reprodução humana pelo agente dentro do Resolve nem aplicação editorial.
Não foi executado instalador/pacote distribuído ou CI remoto.

## Atualização BUG-0007 — 2026-10-19

Gate completo: 240 testes, zero falhas/erros/skips. T:\O editor APP\runtime\regression\20261019T145210Z-ed2e9a49\report.json.
Probe real independente: OE_TEST_NATIVE_AUDIO, 45 itens e 27 áudios nativos reutilizados;
zero setters de canal e original intacta. Escuta humana e render: UNVERIFIED.

## Atualização BUG-0008 — 2026-10-19

Gate completo PASSED, 244 testes, zero falhas/erros/skips: `T:\O editor APP\runtime\regression\20261019T151842Z-b41bc211\report.json`.
Atualizar timeline testado via botão Qt e capturador real no Resolve, somente leitura.
Janela interativa reaberta e IPC respondendo com contexto novo recebido.

## Réguas Tempo / Frames — 2026-10-19

Nova funcionalidade solicitada: três réguas com valor editável, ms/s automáticos e
alternância em quadros do FPS carregado. Testes persistentes: tests/ui/test_duration_control.py.
Gate PASSED: 253 testes, zero falhas/erros/skips; `T:\O editor APP\runtime\regression\20261019T153224Z-e9acd47c\report.json`.
UI Qt offscreen conferida em 1024×720 e 1280×820, Tempo e Frames.
Leitura do FPS real 23.976: valores 1200/250/350 ms representam 29/6/8 frames,
sem mutações no Resolve. Evidências: runtime/reports/duration-real-fps.json e
runtime/reports/duration-1024-time.png, duration-1280-frames.png.
A janela interativa aberta anteriormente requer recarga para mostrar os controles.
Não houve aplicação de cortes, render ou escuta nesta tarefa. Sem commit/push.

Recarga concluída após fechamento confirmado pelo usuário: request de abertura
5bd48f7d-94d2-4b24-942a-03943ad0e830 processada; nova instância respondeu ao IPC activate.

## Auditoria das leis e aplicação automática

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

## Recorrência BUG-0001 em MOV longo

Gate PASSED: 297 testes, zero falhas/erros/skips;
runtime/regression/20261019T163249Z-51206c9e/report.json.
Dois casos RED confirmados antes do patch; GREEN dirigido com 22 aprovados.
Intervalo completo de cinco áudios reais validado e FFmpeg executado apenas nas
caudas de 48 frames, com padding conferido. Sem reconstrução/inferência integral,
render pelo Resolve ou escuta humana. Janela atualizada reaberta e IPC confirmado.
Detalhes e evidências no caso BUG-0001; mídia e timeline preservadas.

## Microfones e interface grunge punk

Baseline anterior: PASSED, runtime/regression/20261019T211256Z-69d5c1a5/report.json.

## Gate final — 2026-10-19

PASSED: 308 testes, zero falhas, erros ou skips. Ruff, formatação, mypy,
dependências, mock e self-test também aprovados.
Relatório: runtime/regression/20261019T213124Z-42e31210/report.json.
Instalação 2.4.0 conferida por SHA-256, um menu público e seis helpers privados.
GREEN dirigido: microphones-engine-green.xml (54), microphones-ui-green.xml (8),
microphones-installer-green.xml (13), microphones-short-clip-green.xml (33).
A instalação lê versão/build da fonte e valida o conjunto antes da cópia.
As falhas intermediárias de versão estática e importação foram corrigidas;
nenhuma asserção de segurança foi removida. Leis canônicas permanecem intactas.
A recuperação do Resolve e a reabertura da UI aguardam o usuário. O teste ON
real está concluído; OFF foi validado automaticamente, com API real UNVERIFIED.
Não há aprovação por escuta, inferência nova nem commit/push nesta tarefa.

## Recuperação concluída

O usuário reabriu o Resolve. Nova instância responsiva; seleção da original por ID
em chamada separada concluída em 370 ms. Captura independente após o reinício:
mesmo ID, 18 clipes e layout completo exatamente igual ao capturado antes do teste.
Evidência: runtime/reports/microphones-recovered-original.json.
A cópia de teste foi preservada como OE_TEST_MICROFONES_ON_INTERROMPIDO; o estado
após o reinício não substitui o readback ON gravado antes do travamento.
Interface atual reaberta pela integração privada; IPC activate ok=true:
runtime/reports/microphones-ui-reloaded.json. O probe OFF real não foi repetido.
O travamento do executor de teste é rastreado em BUG-0017 com automação pendente.


## EDE — configurações e interface horizontal (2026-10-19)

Baseline anterior às alterações: PASSED, 308 testes, sem falhas, erros ou skips;
`runtime/regression/20261019T215539Z-901afc3c/report.json`.
Gate final: **PASSED, 324 testes, zero falhas/erros/skips**;
`runtime/regression/20261019T220825Z-616ca251/report.json`.
Ruff, formatação, mypy, dependências, mock e self-test aprovados.
A primeira execução completa desta tarefa passou no pytest, mas o self-test
recusou o novo nome porque ainda esperava O Editor. A expectativa foi atualizada
para Editor Do Escobar — EDE; a verificação continuou obrigatória e passou no gate.

BUG-0018: RED confirmado para colisão de cache entre modelos; GREEN por faixa,
análise de WAV e substituição de pesos. BUG-0019: RED de sobreposição da seleção
em 1000x680; GREEN nesse tamanho e em 1280x820. Testes reais de Qt conferem salvar,
reler, cancelar, modelo inválido, GPU ausente, preservação de configuração/sessão,
navegação horizontal, centro do título e knobs com valor abaixo e teclado.

Capturas Qt em runtime/ede-visual/: seis etapas em 1000x680 e 1280x820;
1000-0-fixed.png e settings-final.png incluem as correções finais inspecionadas.
GPU real: RTX 4090, índice 0, descoberta no diálogo e carregamento/inferência do
large-v3-turbo local com um segundo de silêncio sintético; sem download.
Evidências: runtime/reports/ede-gpu-discovery.json e ede-gpu-smoke.json.
Isso não prova qualidade de reconhecimento nem uma segunda GPU/modelo real.

Janela EDE reaberta pelo helper privado de abertura, cujos hashes conferem com
a fonte. Título do processo confirmado e IPC activate ok=true;
runtime/reports/ede-ui-reloaded.json. Nenhum Rough Cut foi solicitado nesta tarefa.
O gate permanece sem API/hardware; as verificações reais descritas acima são
separadas. BUG-0017 continua pendente, sem novo teste de mutação no Resolve.
Aprovação estética e uso editorial humano pendentes. Sem novo commit/push.


## Retorno digital e ferramentas separadas (2026-10-19)

Baseline anterior: 324 testes aprovados. Gate final: **PASSED, 336 testes,
zero falhas/erros/skips**; runtime/regression/20261019T224141Z-f4fcc83e/report.json.
Ruff, formatação, mypy, dependências, mock e self-test aprovados.

BUG-0020: RED confirmou a cópia digital ativa em mesmo volume; oito testes de
integração cobrem identidade PCM, voz diferente, função desligada, risos,
cauda de fala e caches ausentes, corrompidos ou truncados. Replanejamento real
sobre áudio em cache confirmou A3 desativada em cinco pontos, mantendo A1.
A sessão original não foi regravada e nenhum corte real foi aplicado.
Evidência: runtime/reports/digital-return-real-plan.json.

Quatro testes de navegação verificam Zoom antes de Legendas, aprovação/exportação/
aplicação restritas à ferramenta atual, diagnóstico nas configurações, relatório
preservado ao reabrir e resposta IPC sem diálogo bloqueante. Capturas Qt reais
em runtime/return-ui-visual/ foram inspecionadas em 1000 e 1280 px, incluindo
configurações. O mínimo de largura final dos dois botões também é testado.
Legendas mantém a funcionalidade existente de sugestões de texto; não inclui
novo mecanismo de legendagem completa.

EDE reaberto pelo helper privado, título Editor Do Escobar — EDE e resposta IPC
activate ok=true: runtime/reports/return-ui-reloaded.json. Não foi executado o
menu público nem consumido um pedido de Rough Cut. Validação humana de áudio e
aplicação real desta correção permanecem separadas. BUG-0017 continua pendente.
Sem novo commit/push. Documentos canônicos das leis permaneceram inalterados.


## Preparação de distribuição 0.2.0 (2026-10-19)

Pedido executado na ordem: funcionalidades/instalador primeiro; validação depois.
Baseline anterior completo: 336 testes, gate 20261019T224141Z-f4fcc83e.
Novos casos BUG-0021 a BUG-0026 estão vinculados aos testes e evidências RED/GREEN.
A suíte completa intermediária aprovou 355 testes mas recusou cobertura duplicada;
na repetição a cobertura foi 86%, restando uma formatação HTML posteriormente
corrigida. Não foram reduzidos thresholds nem adicionados skips.

A publicação final exige novo gate completo, versões exatas de runtime, zero
skips e fontes inalteradas durante a execução. O resultado final é incluído no
asset .validation.json; relatórios detalhados em runtime/regression/latest.json.
Instalação real isolada e autodiagnóstico passaram, download tiny real e inferência
CPU em silêncio sintético passaram. Escuta e novas mutações no Resolve não foram
executadas. As leis canônicas foram conferidas por SHA-256 e permanecem intactas.
