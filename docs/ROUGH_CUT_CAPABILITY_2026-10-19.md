# Probe de Rough Cut — 19/10/2026

Escopo: Resolve Studio 21.1.1.10 no Windows; dois MOV OBS, 23.976 fps,
V1 + quatro pistas de áudio, projeto test editor. Original conferida por ID e layout.
A mutação do probe ocorreu somente em cópia identificada OE_TEST.

| Capacidade | Status neste cenário | Evidência |
|---|---|---|
| DuplicateTimeline + ativação por ID | SUPPORTED | ID distinto e cópia verificada |
| Limpeza apenas da cópia | SUPPORTED | 10 itens removidos, original conferida |
| AppendToTimeline e readback | SUPPORTED | 45 de 45 itens, posição/duração conferidas |
| Detecção de itens extras não retornados | SUPPORTED | 54 extras identificados e removidos |
| Desvinculação, cópia de propriedades/canais e revinculação | SUPPORTED | 9 grupos; 540 propriedades, zero falhas; 36 mapeamentos lidos sem divergência |
| Conferência de origem a 23.976 | SUPPORTED | 5 getters truncados conferidos por tempo + offset |
| Resultado por arquivo + IPC responsivo | SUPPORTED | resposta real recebida sem launcher; 3 chamadas posteriores responderam |
| Preservação de grades, Fusion, transições e efeitos Fairlight | UNSUPPORTED | Não copiados por esta engine |
| Outros formatos, FPS e aprovação de áudio/sincronia por escuta | UNVERIFIED | Não executados nesta rodada |

Relatórios locais: runtime/probe-roughcut-fixed.json,
runtime/roughcut-channel-readback.json, runtime/roughcut-ipc-real-validation-final.json.
Regressão final: runtime/regression/20261019T135356Z-3b735278/report.json — 223 testes.
As cópias de diagnóstico/falha foram mantidas; a timeline original não foi limpa.
A sessão de edição não foi salva automaticamente pelo agente.

## Retificação do áudio — BUG-0007

A classificação anterior de cópia de canais como SUPPORTED provava apenas o
retorno do setter e a leitura do JSON. O usuário confirmou áudio repetido; a
preservação efetiva da fonte naquela implementação fica FAILED neste cenário.

A nova engine conserva as pistas nativas criadas pelo Resolve. Probe separado
`runtime/probe-native-audio.json`: 45 itens, 36 áudios; 27 irmãos nativos reutilizados,
zero setters de canal e zero extras apagados. Original intacta. Preservação de
proveniência nativa e estrutura: SUPPORTED neste cenário. Aprovação por escuta e
renderização: UNVERIFIED. Outros cenários que necessitem remapeamento por setter:
UNVERIFIED quanto à reprodução, mesmo se o JSON conferir.

## Execução automática e fonte longa — auditoria posterior

Resolve Studio 21.1.1.10, MOV atual 23.976, V1 e A1–A4. Transporte
Fusion.Execute → dispatcher de uso único → helper → resultado durável: SUPPORTED
neste cenário. Não houve clique no menu durante VALIDATE/APPLY do probe.
Botões Qt com confirmação foram testados separadamente, com Resolve simulado.
O backend genérico externo de mutação permanece desabilitado.

O uso de FPS arredondado em fontes longas causou a recorrência BUG-0005;
a taxa racional correspondente agora é conferida sem relaxar a tolerância.
Getters truncados, slip/canais e falha após início têm testes persistentes.

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
