# Zoom por take

Etapa **opcional** (botão **Zoom** da barra de etapas). Dá dinâmica a vídeos só de
fala: um take a cada N recebe um zoom fixo durante todo o trecho. Desmarcada
("Usar zoom por take"), nada é aplicado.

## Conceitos

- **Take**: cada trecho entre cortes. No Rough Cut, cada trecho mantido é um take.
  Numa timeline já criada pelo O Editor, os takes são os pontos de corte salvos na
  criação; se a timeline foi editada depois e um corte não cai mais na borda de um
  clipe, cada clipe da faixa de vídeo de referência vira um take (a API não divide
  clipes).
- **Zoom** (intensidade): régua absoluta em %. 100% é o quadro normal do Resolve.
  Abaixo de 100% a imagem diminui (ex.: 50%). Sem teto artificial: vale de 1% até
  10000%, o limite do `ZoomX/ZoomY` do Resolve.
- **Frequência**: "1 a cada N takes". O primeiro zoom cai no take N.
- **Fixo ou Faixa**: zoom e frequência aceitam um valor fixo ou uma faixa
  (ex.: 100 a 150%, 1 a cada 2 a 4 takes). Na faixa, o zoom de cada take e o intervalo
  até o próximo são sorteados; o zoom é arredondado para % inteiro.
- **Sorteio reproduzível**: o mesmo número de sorteio gera sempre o mesmo resultado.
  "Sortear de novo" troca o número. Mudar só a faixa de zoom mantém os mesmos takes
  escolhidos.
- **Takes sem zoom**: recebem o tamanho indicado (100% por padrão) ou ficam como
  estão ("Manter como estão").
- **Ponto do zoom**: centro do quadro por padrão (X 0, Y 0). Pode ser movido em
  pixels, igual para todos os takes, quando o vídeo estiver torto ou fora do centro.
  Usa o `Anchor Point` do Inspector; com 100% o Anchor Point não desloca a imagem.
- **Faixas de vídeo**: escolha uma ou mais (V1 por padrão). Os takes seguem os cortes
  da faixa mais baixa marcada; todos os clipes das faixas marcadas que cobrem o take
  recebem o mesmo zoom. Faixas de áudio nunca são tocadas.

## Duas formas de aplicar

1. **Junto com o Rough Cut**: marque "Aplicar junto ao criar o Rough Cut (etapa 04)".
   O zoom entra no plano da prévia (aparece no fim do texto da prévia e na
   confirmação). Mudar o zoom atualiza a prévia existente sem refazê-la.
2. **Depois dos cortes**: abra no Resolve a timeline criada pelo O Editor
   (`..._OE_ROUGHCUT_NNN`), clique em **Ler timeline aberta** (somente leitura) e em
   **Aplicar zoom na timeline**. Timelines originais e cópias `_FALHOU` são recusadas
   pelo programa e de novo pelo script dentro do Resolve.

A tabela mostra cada take, início, duração e zoom. O pedido é enviado ao Resolve pelo
mesmo canal de uso único do Rough Cut (um pedido por vez; o outro botão aguarda).

## Segurança e verificação

Dentro do Resolve (`M.apply_take_zoom` em `internal_common.lua`):

- confere pedido confirmado, validade de 1 hora, projeto, nome e id da timeline e o
  padrão `_OE_ROUGHCUT_`;
- confere cada clipe (id, faixa, início e fim) antes de qualquer alteração;
- altera somente `ZoomX`, `ZoomY`, `AnchorPointX`, `AnchorPointY` e confere cada valor
  por leitura;
- se um valor não for confirmado ou a timeline ativa mudar, todos os clipes já
  alterados voltam ao valor anterior;
- um recibo em `plans/applied` impede repetir o mesmo pedido.

## Desfazer (Ctrl+Z)

Cada aplicação no Resolve (incluindo o zoom aplicado junto com o Rough Cut) entra no
histórico da timeline (`%APPDATA%\O Editor\plans\take-zoom-history.json`, até 50
níveis). **Desfazer (Ctrl+Z)** na etapa Zoom restaura os valores anteriores da última
aplicação. Antes, o Resolve confere que os clipes ainda têm os valores aplicados; se
alguém mudou o zoom à mão depois, o desfazer é cancelado sem alterar nada. Cada
Ctrl+Z desfaz um nível.

## Arquivos

- `src/o_editor/domain/take_zoom.py`: regras puras (sorteio, takes, valores).
- `src/o_editor/application/take_zoom.py`: prévia, pedidos, registro de timelines
  criadas (`oe-timelines.json`) e histórico.
- `src/o_editor/ui/take_zoom_panel.py`: etapa Zoom.
- `launcher/internal_common.lua`: `apply_take_zoom`, `run_take_zoom_action`, zoom
  dentro de `apply_rough_cut`, despacho `take_zoom` no menu único.

## Limites

- Comportamento real de `ZoomX/ZoomY/AnchorPoint` via `SetProperties` no Resolve 21.1:
  **UNVERIFIED** até o teste manual (os testes usam um Resolve simulado).
- Zoom fixo por take (sem animação/keyframes).
- A antiga análise heurística de zoom continua no código e no plano exportado, mas
  saiu da interface: a etapa Zoom agora é o zoom por take.

## Teste manual no Resolve

1. Reinstale os scripts (`O Editor - Instalar no DaVinci.cmd`) e reinicie o Resolve.
2. Crie um Rough Cut com "Aplicar junto" marcado (1 a cada 2, 130%). Confira no
   Inspector que os takes pares têm Zoom 1.300 e os ímpares 1.000.
3. Com a cópia aberta, clique em "Ler timeline aberta", mude para 50% e aplique.
4. Ctrl+Z duas vezes: volta para 130% e depois para os valores copiados da original.
5. Abra a timeline original e tente aplicar: o pedido deve ser recusado.
