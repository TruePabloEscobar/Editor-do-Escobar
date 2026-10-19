# LEI DA CONSISTÊNCIA VISUAL

**Versão:** 1.0  
**Natureza:** diretriz operacional reutilizável para agentes de desenvolvimento  
**Aplicação:** sites, aplicativos, jogos, editores, plugins de áudio (VST/AU), ferramentas internas e outros softwares com interface  
**Agentes:** Codex, Claude, Hermes e outros agentes capazes de ler este Markdown

## Finalidade

Preservar a identidade visual, a experiência de uso, a integridade das interfaces e os arquivos originais durante alterações de software. Impedir que uma melhoria localizada produza incoerências em outras telas, destrua componentes existentes ou modifique indevidamente projetos usados como referência.

**Princípio central:** modificar apenas o que foi autorizado, mantendo o restante funcional, visualmente coerente e recuperável. Uma referência serve para orientar a implementação, não é uma autorização para alterar sua origem.

Esta lei complementa a `LEI_BOAS_PRATICAS.md`, quando disponível, especialmente os princípios de não regressão, comprovação, reversibilidade e validação humana. Pode ser utilizada de forma independente.

---

## 1. Condições de ativação e interpretação

1. Aplique esta lei quando o usuário pedir uma criação ou alteração de interface, tema, design system, layout, navegação, elementos gráficos, animações, recursos visuais ou componentes interativos.
2. Ao ser instruído a **"aplicar a Lei da Consistência Visual"**, leia este documento e adapte seus procedimentos ao projeto atual. Não suponha que outro agente já tenha executado a instalação.
3. Identifique primeiro **qual é o projeto de destino** e **quais são as referências**: imagens, capturas, especificações, mockups, arquivos, projetos locais, aplicações publicadas ou repositórios externos.
4. Diferencie explicitamente três escopos: **destino editável**, **referência somente para consulta** e **materiais originais do próprio destino que devem ser preservados**.
5. Na ausência de instrução contrária, interprete alterações como **localizadas**: não redesenhe telas, componentes ou fluxos fora do escopo solicitado.
6. Se a tarefa tiver ambiguidades com impacto material, como substituir o tema inteiro ou copiar o comportamento de outro produto, solicite esclarecimento antes de executar mudanças irreversíveis.
7. Não trate exemplos, mockups ou capturas como prova de todas as regras funcionais de um sistema; investigue o funcionamento real quando houver acesso.

## 2. Preservação rigorosa de projetos de referência

**Regra obrigatória:** todo projeto externo ao destino, fornecido como referência visual, funcional ou estrutural, é **somente leitura por padrão**.

- Pode inspecionar arquivos, código, imagens, cenas, temas, animações e fluxos da referência, conforme o acesso legitimamente disponível.
- **Não pode** editar, renomear, formatar, reorganizar, executar migrações, limpar caches, instalar dependências ou executar comandos que modifiquem o projeto de referência.
- **Não pode** executar geradores, builds ou comandos de desenvolvimento que possam escrever no diretório de referência, a menos que exista autorização explícita e um ambiente isolado seguro.
- Não use o diretório da referência como destino de saída, cache, log, exportação, artefatos de build ou testes.
- Não altere configurações, arquivos de projeto, dependências, bancos de dados, assets ou metadados da referência para facilitar a inspeção.
- Para experimentar com uma implementação de referência, use, se necessário e autorizado, **uma cópia de trabalho isolada fora do original**. Registre a origem e não apresente essa cópia como o projeto original.
- Não sincronize mudanças no sentido inverso, do destino para a referência, sem uma solicitação explícita.
- Se o usuário autorizar especificamente modificar a referência, trate essa autorização como uma **nova tarefa com escopo próprio**; proteja o estado anterior antes de editar.

**Reutilização de materiais:** não copie automaticamente código, imagens, fontes, modelos 3D, áudio, marcas ou outros assets só porque a referência é acessível. Confirme a autorização de reutilização, a licença quando relevante e a compatibilidade técnica. Quando autorizado, copie para o **destino** preservando a referência intacta; registre origem, caminho e transformações. Se só foi solicitada inspiração, reproduza princípios de design e comportamentos, sem pressupor que é permitido copiar ativos ou código proprietários.

### Matriz mínima de origem

Antes de alterar um projeto a partir de outro, identifique, ao menos internamente:

| Item | Informação necessária |
| --- | --- |
| Projeto de destino | Diretório/repositório efetivamente editável |
| Referência(s) | Caminho, URL, screenshot ou documento utilizado |
| Permissão | Leitura; reutilização expressamente autorizada; edição, se houver autorização expressa |
| Elementos a aproveitar | Ex.: hierarquia visual, navegação, cores, animações ou componente específico |
| Elementos intocáveis | Originais, funcionalidades e telas fora do escopo |
| Limitações | O que não pôde ser inspecionado ou validado |

Não invente acesso a diretórios, arquivos ou URLs indisponíveis. Informe a limitação e prossiga apenas com o que puder ser verificado.

## 3. Preservação dos originais dentro do projeto de destino

1. Preserve os arquivos-fonte originais e sua rastreabilidade. Antes de substituições extensas ou operações destrutivas, confirme a existência de versionamento, backup ou mecanismo viável de reversão.
2. Não sobrescreva imagens, ilustrações, fontes, arquivos de design, cenas, presets, mídia ou assets originais para criar versões derivadas, a menos que isso seja expressamente necessário e autorizado.
3. Prefira gerar variantes e recursos processados em locais próprios do destino, com nomes claros, preservando os arquivos originais.
4. Ao converter recursos, mantenha propriedades importantes: proporção, transparência, resolução apropriada, perfis de cor quando aplicáveis, nomes/referências e características exigidas pelo usuário.
5. Evite substituições automáticas por recursos visuais genéricos, especialmente quando o projeto já possui identidade definida.
6. Não elimine componentes aparentemente obsoletos sem investigar consumidores, rotas, cenas, templates, geradores, importadores ou modos alternativos que ainda possam utilizá-los.
7. Nunca afirme que um original permaneceu intacto se não tiver como verificar sua integridade. Diferencie preservação planejada, conferida e não verificável.

## 4. Inspeção inicial e definição da fonte da verdade

Antes de implementar qualquer alteração relevante:

1. Identifique a arquitetura de interface: páginas, componentes reutilizáveis, cenas, estilos, temas, assets, estados de UI, editor interno e geração/exportação.
2. Localize a **fonte da verdade**. A edição deve ocorrer no arquivo, componente, template ou configuração que efetivamente origina a interface. Não trate um artefato gerado como fonte principal quando ele será sobrescrito na próxima geração.
3. Inspecione convenções existentes: paleta, tipografia, espaçamento, tamanhos, bordas, sombras, texturas, ícones, efeitos, animações e padrões de interação.
4. Identifique componentes e tokens compartilhados antes de replicar CSS, estilos, scripts, materiais ou configurações em múltiplos pontos.
5. Mapeie os estados necessários: padrão, hover, foco, ativo, selecionado, carregando, vazio, erro, sucesso, desabilitado, modal aberto e outros relevantes.
6. Descubra quais telas e fluxos dependem do elemento que será modificado.
7. Registre a aparência de referência, preferencialmente com capturas e condições de reprodução, quando as ferramentas permitirem.

**Regra para sistemas com geradores ou editores:** se uma interface é produzida por um editor, gerador, template ou pipeline, a alteração deverá considerar **a interface final, a interface de edição e a fonte que gera ambas**, conforme o escopo. Não se considera a tarefa completa se a próxima regeneração desfizer a mudança ou se o editor deixar de editar corretamente o resultado.

## 5. Identidade visual e linguagem consistente

1. Respeite a linguagem visual expressamente aprovada pelo usuário. Não substitua temas existentes por estéticas populares, tendências ou preferências do agente.
2. Preserve coerência de cores, hierarquia tipográfica, escala, alinhamentos, espaçamentos, ícones, texturas, animações e feedbacks de interação.
3. Reaproveite tokens, temas, variáveis e componentes já existentes. Se precisar criar um novo padrão, justifique por que os atuais são insuficientes.
4. Evite componentes visualmente desconectados do restante do produto, mesmo quando funcionam isoladamente.
5. Não padronize à força componentes cuja diferença é intencional, como telas de jogo, interfaces diegéticas, editores ou ferramentas técnicas.
6. Preserve as características específicas de uma referência quando o pedido exigir fidelidade, como proporção, disposição, materiais, cores ou forma de interação.
7. Diferencie três metas possíveis: **inspirar-se** na referência, **adaptar** sua linguagem ao projeto, ou **reproduzir fielmente** um elemento autorizado. Não converta uma meta em outra por conta própria.
8. Em uma mudança global de identidade, audite telas secundárias, painéis administrativos, modais, widgets, telas de configuração, editor, estados alternativos e conteúdo gerado. Não considere apenas a home ou a tela inicial.

## 6. Consistência funcional e preservação da experiência

**Aparência e funcionalidade têm o mesmo grau de importância.** Uma alteração estética não autoriza eliminar recursos ou reduzir a usabilidade.

- Preserve ações, eventos, navegação, atalhos, pesquisa, filtros, formulários, importação/exportação, controles de mídia, estados salvos e integrações existentes.
- Não transforme elementos interativos em imagens estáticas, nem acrescente botões sem função real.
- Preserve comportamento de teclado, mouse, toque, controles de jogo e outras formas de entrada aplicáveis.
- Verifique carregamento, erros, ausência de dados, listas extensas e conteúdo real, não apenas dados de demonstração.
- Não esconda informações ou controles necessários para fazer um layout parecer mais limpo, salvo quando o usuário autorizar a mudança de fluxo.
- Ao alterar navegação ou hierarquia, preserve a capacidade de encontrar e executar as funções anteriores.
- Para mudanças funcionais necessárias à nova interface, exponha os efeitos colaterais e valide-os como parte da tarefa.

## 7. Escala, responsividade e legibilidade

1. Teste as dimensões e densidades de tela realmente suportadas pelo projeto. Para web, considere desktop e mobile quando pertinentes; para desktop, janelas redimensionadas e escala de DPI; para jogos, resoluções e proporções previstas; para VSTs, tamanhos de janela suportados pelo host.
2. Verifique alinhamento, quebra de linha, texto longo, localização, diferenças entre fontes, zoom e redimensionamento.
3. Evite truncamento de informações essenciais, botões inacessíveis, sobreposição de elementos e scrolls conflitantes.
4. Preserve contraste, foco visível, áreas de clique adequadas e legibilidade. Use critérios de acessibilidade aplicáveis à plataforma; não invente aprovação formal se não houve auditoria.
5. Em interfaces de aparência deliberadamente experimental, preserve a identidade sem sacrificar ações críticas e informações essenciais.
6. Priorize layouts que se adaptem a conteúdo real, em vez de depender exclusivamente de posições rígidas que só funcionam em uma captura.

## 8. Adaptação segura de interfaces entre tecnologias

Quando usar um projeto como referência para outro feito em tecnologia diferente:

1. Extraia os **princípios transferíveis**: hierarquia, organização, interações, semântica, paleta e estados.
2. Reimplemente-os com os componentes idiomáticos do destino. Não force uma arquitetura incompatível apenas para copiar a estrutura interna da referência.
3. Em Godot, considere cenas, temas, nós, ancoragem, containers, foco, escala e inputs. Em plugins de áudio, considere o framework de UI, as restrições da thread de áudio e as particularidades dos hosts. Em web, considere componentes, roteamento, CSS, acessibilidade e responsividade.
4. Preserve a identidade e o comportamento esperados, ainda que a implementação técnica seja diferente.
5. Se uma interação ou efeito não puder ser reproduzido de maneira equivalente, documente a limitação e proponha um substituto apenas com aprovação para mudanças relevantes.

## 9. Execução incremental e limites de alteração

1. Delimite arquivos e módulos afetados. Prefira alterações pequenas e rastreáveis a substituições integrais sem necessidade.
2. Implemente primeiro um caso representativo quando a mudança atingir muitos componentes; valide antes de replicar.
3. Evite alterações oportunistas em páginas, sistemas ou componentes não relacionados à tarefa.
4. Se uma refatoração estrutural for necessária para o visual solicitado, explique a necessidade, o impacto e a verificação planejada.
5. Não altere deliberadamente a identidade de elementos fora do escopo. Entretanto, corrija inconsistências diretamente produzidas pela própria alteração.
6. Mantenha uma estratégia de reversão para intervenções amplas ou arriscadas.
7. Não declare que o projeto de referência foi atualizado. A entrega deve afetar somente o projeto de destino autorizado.

## 10. Validação visual e regressão

Após a implementação, use a combinação de verificações compatível com o projeto:

- **Comparação visual:** confrontar estados anteriores, referência e resultado. Usar screenshots ou diffs de imagem quando disponíveis, com atenção a variações legítimas de renderização.
- **Cobertura de estados:** abrir e verificar telas, modais, menus, mensagens, formulários e fluxos afetados, incluindo estados de erro e dados extensos.
- **Cobertura de tamanhos:** conferir resoluções, escalas e dimensões de janela pertinentes.
- **Cobertura funcional:** executar testes automatizados existentes e adicionar novos testes para comportamentos quebrados ou bugs confirmados, em consonância com a Lei de Boas Práticas.
- **Cobertura da fonte da verdade:** regenerar ou compilar, quando apropriado, e confirmar que o resultado persiste e que o editor ou gerador continua funcional.
- **Integridade dos originais:** inspecionar o diff do destino e verificar que nenhuma referência externa foi modificada. Se houver acesso de somente leitura sem forma de auditoria completa, reportar essa limitação.
- **Acessibilidade e legibilidade:** testar o que for automatizável e indicar claramente verificações humanas pendentes.

**Não invente screenshots, testes, comparações nem resultados.** Sem ambiente gráfico ou host disponível, execute as verificações possíveis e relate explicitamente o que permaneceu sem validação. Um build bem-sucedido, sozinho, não prova fidelidade visual nem qualidade de experiência.

Quando um problema for encontrado, registre um teste de regressão adequado se for tecnicamente viável. Para defeitos visuais, priorize testes reproduzíveis (componentes, snapshots, screenshots ou asserts de layout) quando proporcionais; quando não for possível, registre roteiro manual detalhado com condição, resultado esperado e evidência disponível.

## 11. Entregáveis e relatório obrigatório

Ao encerrar uma alteração visual, informe sucintamente:

1. **Escopo executado:** quais telas, componentes e fluxos foram alterados.
2. **Referências utilizadas:** quais materiais foram consultados e o que foi adaptado deles.
3. **Preservação:** confirmação fundamentada de que referências e arquivos originais permaneceram intocados, ou ressalvas quando não puder comprovar.
4. **Funcionalidades preservadas:** quais comportamentos críticos foram verificados e como.
5. **Validações:** builds, testes, comparações visuais e dispositivos/resoluções efetivamente examinados, com resultados.
6. **Limitações e pendências:** o que ainda precisa de verificação humana, ferramenta específica ou autorização.

Nunca relatar como concluída uma verificação não executada.

## 12. Modo de instalação e aplicação contínua

### Ao ativar esta lei em um projeto novo ou existente

1. Inspecione as instruções e a estrutura do projeto. Respeite convenções existentes.
2. Identifique o tema, as fontes de verdade, os componentes centrais e os fluxos cuja apresentação precisa permanecer coerente.
3. Registre essas convenções no lugar de documentação já adotado pelo projeto. Se não houver, **e somente se houver ganho real**, crie documentação enxuta como `docs/CONSISTENCIA_VISUAL.md`. Não crie estruturas vazias ou duplicadas.
4. Determine como serão verificadas mudanças de UI: testes já existentes, testes novos quando necessários, comparações visuais e roteiros manuais.
5. Não altere a interface apenas para "instalar" a lei. Instalar significa estabelecer práticas, não realizar um redesign por iniciativa própria.

### Em toda tarefa visual posterior

Siga o ciclo: **identificar destino e referências → inspecionar fonte da verdade → delimitar escopo → preservar originais → implementar incrementalmente → testar apresentação e funcionamento → registrar evidências e pendências**.

### Regras de prioridade

- Instruções explícitas e atuais do usuário sobre o escopo têm prioridade sobre preferências estéticas inferidas pelo agente.
- A integridade dos projetos de referência é obrigatória, exceto com autorização explícita para editá-los.
- Em caso de conflito entre fidelidade visual e preservação funcional, não destrua funções silenciosamente. Busque uma solução compatível ou apresente o conflito ao usuário.
- Esta lei não concede permissões adicionais de sistema, de acesso a arquivos, de distribuição de assets nem de modificação de projetos.

---

## Critério de cumprimento

Uma intervenção respeita a **Lei da Consistência Visual** quando: (a) ocorreu apenas no destino autorizado; (b) preservou referências e originais conforme o escopo; (c) respeitou a linguagem visual e os comportamentos existentes, salvo alterações solicitadas; (d) foi aplicada à fonte efetiva da interface, inclusive geradores e editores quando relevantes; e (e) apresentou validações reais e identificou claramente o que não pôde ser verificado.

**Falhar em qualquer condição não significa automaticamente descartar a implementação:** significa registrar a não conformidade, corrigir quando possível ou obter decisão explícita do usuário antes de declarar a tarefa completamente validada.
