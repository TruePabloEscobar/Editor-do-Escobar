# Limpeza de microfones e retorno

Na etapa **Prévia e cortes**, a opção **Limpar microfones sem fala / retorno**
começa ligada e lembra a escolha local (runtime/ui-preferences.ini). Desligar
invalida a prévia e mantém os estados originais dos clipes na próxima cópia.
Planos/API anteriores, sem a opção explícita, conservam o comportamento anterior.

A análise usa a transcrição e energia medidas por microfone. Durante uma fala,
clipes de microfones selecionados sem fala ou atividade própria são desativados
por trecho. Fora das falas, as faixas mantêm o estado original. Música e faixas
não selecionadas para voz não recebem esta limpeza. Cortes globais continuam
seguindo as regras de silêncio/texto existentes.

- Frases diferentes sobrepostas: ambas ativas, mesmo com níveis diferentes.
- Texto idêntico após normalização, sobreposição >=50% e diferença >=6 dB:
  o mais fraco é tratado como provável retorno. É uma heurística conservadora.
- Sem prova de áudio idêntico, energia ausente ou níveis próximos: manter ambos.
- Risos e reações explícitos e atividade sem transcrição: preservar, conforme
  escolha do usuário. VAD não comprova intenção; ruído incerto pode permanecer.
- Análise antiga sem atividade por faixa: não inferir silêncio; só desativar
  retorno com evidência independente. Flags antigas de retorno são reavaliadas
  com a regra mais estrita, inclusive antes dos cortes globais.

Margens de 100 ms antes e 180 ms depois evitam desativação junto à voz. O plano
mostra intervalos e motivos. Toda decisão editorial interna continua em frames.
Limites são compartilhados com os irmãos nativos de áudio para preservar os
canais; desativar é diferente de remover tempo. A original é imutável.

A engine 2.4.0 exige GetClipEnabled igual ao plano para cada item reconstruído.
Se não conferir, a aplicação falha e retorna à original verificada. Não há
edição no banco do Resolve, automação de mouse ou render do Resolve neste fluxo.

## Proteções e limites

Tests: tests/unit/test_microphone_cleanup.py, tests/ui/test_microphone_controls.py
e tests/integration/test_lua_rough_cut.py. BUG-0014 registra a conferência de estado.
O comando obrigatório continua scripts/run_regression.py. API real, escuta e
qualidade de detecção em conversas reais são validações separadas. Não há novo
modelo baixado, upload de áudio ou mudança no Whisper.

## Interface grunge punk

Referência somente leitura: https://pabloescobardj.web.app/ e os estilos públicos
assets/grunge.css e assets/grunge-home.css, consultados em 2026-10-19.
Adaptação em ui/theme.py: papel/tinta, título condensado, etiquetas monoespaçadas,
recorte do cabeçalho desenhado em código, bordas retas, vermelho/verde/areia.
Tabelas e editores permanecem lisos. Sem downloads de fontes ou texturas.
Qt offscreen conferido em 1024x720 e 1280x820, navegação/revisão/prévia.
Screenshots em runtime/reports/punk-*.png. Site e referências não foram editados.

Evidências reais e gate estão nas seções abaixo. Sem commit/push nesta tarefa.

## Evidências desta entrega

Gate obrigatório final aprovado após o ajuste do instalador e do clipe curto.
Gate anterior: 306 aprovados, sem falhas/skips, 20261019T212133Z-8689b0ed.
Readback real ON: 84 operações/estados/posições/offsets conferidos, 24 itens
inativos, 56 irmãos nativos reutilizados, zero setters de canal. Todos os
mapeamentos conferem com a origem. Original conferida intacta antes/depois da
aplicação, antes da troca de volta à original.

A execução técnica tentou ON e OFF e restauração no mesmo script. ON terminou
SUCCESS e gravou resultado/layout, mas a API não retornou da troca de timeline;
o Resolve ficou sem responder, confirmado pelo processo e pelo usuário. O teste
OFF não foi executado. Não houve reenvio do plano, kill, autosave nem edição da
original. Recuperação/reabertura solicitada ao usuário; escuta e classificação
em gravação real continuam UNVERIFIED. Isto não é aprovação de áudio por escuta.

Arquivos: runtime/reports/microphones-native-ON.json,
microphones-real-readback-ON.json e microphones-probe-original.json.
A evidência usa mídia real e falas de teste sintéticas, sem inferência no modelo.

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
Recuperação do Resolve e reabertura da UI concluídas, conforme seção abaixo. O teste ON
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


## Retorno digital em volume igual — BUG-0020

PCM completo e alinhado exatamente idêntico entre faixas permite manter a primeira
faixa selecionada na ordem da timeline e desativar a cópia durante as falas, mesmo
em volume igual. O limiar de 6 dB da heurística de texto continua intacto para os
outros casos. A prévia usa o motivo RETORNO_AUDIO_IDENTICO.

Transcrições novas registram signal_fingerprint de PCM 16 bits mono completo,
incluindo taxa e quantidade de amostras. Silêncio digital não oferece prova de
duplicação. Sessões antigas podem conferir os WAVs em cache ao gerar a prévia,
sem repetir o Whisper, regravar a sessão ou modificar a mídia. A comparação usa
blocos e cache em memória invalidado pelos metadados dos arquivos.
Cache ausente, inválido, truncado ou de duração diferente mantém a decisão
conservadora. A identidade prova cópia exata; eco acústico, atrasos e reverberação
continuam sujeitos à heurística anterior e à revisão humana.

A marca de retorno de segmento inteiro exige que a fala da cópia esteja contida
na fala de referência. Partes adicionais reconhecidas continuam protegendo o
tempo editorial. A desativação local usa a região com referência; risos e reações
explícitas continuam protegidos. Desligar a opção preserva os estados anteriores.

BUG-0020 registra reprodução RED e testes de PCM, vozes distintas, caudas,
reações e cache inválido. Conferência real da decisão:
runtime/reports/digital-return-real-plan.json. Planejamento em memória com o
cache da sessão do usuário; sem aplicação ao Resolve.


BUG-0026: uma faixa omitida ou desativada não pode servir de referência para
silenciar a cópia audível. O roteamento de evidências considera as políticas
da nova timeline; não altera a sessão salva nem reativa as faixas originais.
