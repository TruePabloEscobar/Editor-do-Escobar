# Editor Do Escobar — interface por etapas

A interface usa a paleta de Pablo: #272425, #2B2B2B, #4B372C, #AF8E77,
#1C5427, #B9322D e #FCF5F1. A textura discreta é desenhada no cabeçalho;
áreas de leitura e edição ficam lisas. Não depende de fontes ou texturas baixadas.

1. Faixas de voz: seleção dos microfones e canais, com nomes legíveis.
2. Transcrição: processamento local e acesso à revisão depois de existir uma sessão.
3. Revisão: tabela com busca, filtros e TXT. A opção Detalhes mostra as colunas técnicas.
4. Prévia e cortes: silêncios, política por faixa, prévia, validação e aplicação confirmada.

As etapas ficam numa barra horizontal, seguidas por **Zoom** e **Legendas**, nessa
ordem. A engrenagem abre **Transcrição** (modelo local e GPU) e **Diagnóstico**
([configurações](EDE_SETTINGS.md)). Nome centralizado, sem slogans no cabeçalho.
A navegação não recria
a sessão nem descarta textos, seleções ou plano de cortes. As mesmas regras de
confirmação, original imutável e capacidade da API continuam em vigor.

O atalho O EDITOR abre o aplicativo diretamente. A captura do contexto da timeline
usa o capturador Lua documentado via processo nativo isolado, sem habilitar
o backend externo de aplicação de planos.

Validação visual: renderizar a janela com fontes do Windows em 1280x820 e 1024x720.
Validação funcional: executar `scripts/run_regression.py` (inclui testes de navegação,
preservação de edições/plano, aplicação bloqueada sem dados e alvo dos atalhos).


O menu único abre a interface atual. Validar/Aplicar inicia o script automaticamente.
Se a conexão falhar antes do consumo, O EDITOR permite executar o pedido ainda
válido em até cinco minutos; cada solicitação é consumida uma única vez.
Um plano salvo sozinho não dispara alterações ao abrir. Reinicie o Resolve depois
da atualização para limpar os itens de menu em cache.

## Prévia e solicitação ao Resolve

Validar/Aplicar prepara o pedido e inicia o host interno do Resolve automaticamente.
`Área de Trabalho > Scripts > O EDITOR` permanece como recuperação quando a UI
informa que o pedido ainda não foi consumido.
Enquanto aguarda resposta, o aviso e Cancelar solicitação ficam visíveis. Gerar
prévia, editar e reenviar ficam protegidos para preservar o plano confirmado.
Cancelar arquiva somente o pedido ainda não consumido; uma execução já recebida
pelo Resolve deve terminar e retornar seu resultado. Pedidos cancelados não são
reproduzidos pelo menu. Alterar opções de silêncio/faixas exige gerar nova prévia.

Proteção: tests/ui/test_rough_cut_lifecycle.py; histórico: BUG-0006.

## Atualizar a timeline carregada

Após mudar de timeline ou trocar clipes no Resolve, clique em **Atualizar timeline**
no cabeçalho do O Editor. Projeto, nome, duração, FPS e faixas são lidos novamente;
a interface volta à seleção de vozes. Se os clipes mudaram, a prévia anterior é
invalidada e a transcrição antiga fica identificada como desatualizada. Transcreva
novamente antes de gerar cortes. A atualização não altera a timeline do Resolve.

O botão fica bloqueado durante operações em andamento ou enquanto o menu aguarda
um pedido de Validar/Aplicar. Em falha de conexão, a janela informa o erro e conserva
os dados anteriores. Leitura isolada tem timeout; não habilita backends de mutação.

## Knobs de limpeza de silêncios

Silêncio mínimo e margens antes/depois da fala têm um knob e um valor editável abaixo,
sincronizados. Tempo mostra milissegundos abaixo de 1 s e segundos a partir de 1 s
(por exemplo, 250 ms e 1,2 s). O campo aceita vírgula ou ponto e unidades explícitas.

A alternância Tempo / Frames usa o FPS da timeline carregada; Frames só fica
disponível após o carregamento. Em Frames, knob, digitação e setas usam quadros
inteiros. Alternar unidades ou atualizar o FPS apenas muda a representação, sem
alterar a duração; editar um valor invalida a prévia e escolhe Personalizada.
Os limites e presets anteriores permanecem. A configuração continua serializada
em ms e o planejador a converte em quadros com o mesmo arredondamento da exibição.
Controles ficam bloqueados enquanto Validar/Aplicar aguarda resposta. Arraste o knob
para cima/baixo; Shift permite ajuste fino, setas e roda também funcionam. Duplo
clique restaura o valor padrão do controle. A antiga propriedade técnica `slider`
é um alias do knob para compatibilidade das verificações existentes.

Silêncios, Microfones/retorno e Faixas na cópia ficam em abas no topo da prévia;
o plano ocupa toda a largura abaixo. Campos editáveis e controles de aplicação
foram conferidos em 1000x680 e 1280x820. As funções continuam disponíveis sem
a coluna lateral. Aprovação estética e usabilidade pelo usuário continuam pendentes.

Proteção: tests/ui/test_duration_control.py, com FPS inteiros e fracionários,
edição por teclado, sincronização, alternância sem perda e invalidação da prévia.

## Confirmar e executar sem voltar ao menu

Validar no Resolve e Aplicar Rough Cut acionam o script automaticamente. Aplicar
mantém a confirmação de criação de cópia. Aguarde a conferência final na própria
janela; o ACK de início não significa que os cortes foram aplicados. O programa
não reenvia pedidos que possam estar em execução. Ao falhar, volta à original
conferida e deixa a cópia com sufixo _FALHOU para inspeção.

O pedido só pode ser cancelado antes do consumo. Falha de conexão mostra instrução
de recuperação; uma execução já iniciada não é reaplicada pelo menu sozinho.

## Microfones e visual de impressão

Limpeza opcional por trecho e referência grunge punk: docs/MICROPHONE_CLEANUP.md.
O controle fica na aba Microfones/retorno, no topo da Prévia e cortes, e lembra a escolha.
Mudá-lo exige nova prévia. Risos e sons intencionais são preservados.


## Zoom, Legendas e diagnóstico

Zoom e Legendas compartilham os resultados da análise, mas cada seção mostra seus
próprios controles e sugestões. Aprovar/rejeitar todos, exportar e aplicar afetam
somente o tipo da seção aberta; as aprovações da outra seção são mantidas.
Legendas corresponde às sugestões de texto/Text+ existentes no painel anterior.

Diagnóstico, capacidades, relatório e log ficam nas configurações. A janela é
reutilizada sem apagar relatórios. A abertura não bloqueia o ACK de mensagens IPC;
a edição da configuração fica indisponível durante operações em andamento.
Proteção: tests/ui/test_tools_navigation.py, em 1000 e 1280 pixels de largura.
