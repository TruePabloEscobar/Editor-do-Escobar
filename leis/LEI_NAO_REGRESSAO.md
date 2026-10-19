# LEI 01 — NÃO REGRESSÃO

> **Identificador:** `LEI-01`  
> **Versão:** `1.0`  
> **Apelido:** `Lei de Não Regressão`  
> **Aplicação:** agentes de desenvolvimento de software, independentemente de fornecedor ou modelo (Codex, Claude, Hermes e equivalentes).  
> **Objetivo:** impedir que defeitos já corrigidos reapareçam sem serem detectados, mantendo memória técnica verificável dos problemas encontrados.

## 1. Mandamento central

**Nenhum bug deve ser considerado definitivamente resolvido apenas porque o comportamento parece ter sido corrigido.** Para cada defeito confirmado, registre sua ocorrência, reproduza-o sempre que possível e acrescente uma verificação persistente capaz de detectar seu retorno em alterações futuras.

Esta lei institui o **BugBunty Interno**, nome dado neste projeto ao *registro de defeitos e sistema de testes de regressão*. Não se trata de um programa público de recompensas por vulnerabilidades (*bug bounty*). Seu propósito é evitar a repetição de erros e preservar o conhecimento adquirido durante o desenvolvimento.

Uma correção acompanhada somente de uma explicação escrita **não constitui proteção automatizada contra regressão**.

## 2. Quando esta lei entra em vigor

Ao receber instruções como **"Aplique a Lei 01"**, **"Ative a Lei de Não Regressão"** ou ao ter este arquivo explicitamente carregado no contexto de desenvolvimento:

1. Leia este documento integralmente.
2. Identifique a raiz do projeto e verifique como ele é construído, executado, testado e versionado.
3. Se for a primeira ativação no projeto, execute a **instalação** descrita na seção 3.
4. A partir daí, aplique o **procedimento permanente** das seções 4 a 10 em toda correção de defeito e em mudanças com risco de regressão.
5. Informe objetivamente o que foi instalado, testado, aprovado, não executado ou deixado pendente.

**Escopo recomendado:** aplicações com múltiplos módulos, estado persistente, banco de dados, autenticação, integrações, processamento de arquivos, interfaces complexas, jogos, plugins ou manutenção continuada. Em projetos simples, reduza a estrutura ao mínimo necessário. A lei não exige instalar ferramentas desproporcionais ao projeto.

A lei se aplica **enquanto o agente estiver trabalhando** e por meio dos testes configurados na automação do projeto. O arquivo Markdown, sozinho, não cria um processo autônomo de monitoramento em segundo plano. **Não altere ou enfraqueça o texto desta lei sem autorização explícita do responsável pelo projeto.**

## 3. Instalação obrigatória no projeto

### 3.1. Inspeção inicial

Antes de alterar a estrutura, identifique:

- Linguagens, frameworks, gerenciador de pacotes e sistemas operacionais suportados.
- Suíte de testes existente, comandos para executá-la, cobertura relevante e limites de tempo.
- Configuração de CI, scripts de build, verificação estática e ambientes de teste.
- Partes críticas do sistema, dependências externas e riscos de perda de dados.
- Problemas já documentados e falhas existentes na suíte, se houver evidências disponíveis.

Execute uma verificação inicial apropriada, **quando for seguro e viável**, e registre o resultado. Diferencie falhas anteriores à sua intervenção das que surgirem depois. Não afirme que a suíte passou quando não foi executada.

### 3.2. Estrutura mínima

Crie ou adapte a seguinte estrutura **sem duplicar mecanismos equivalentes já existentes**:

```text
<raiz-do-projeto>/
├── leis/
│   └── LEI_01_NAO_REGRESSAO.md       # Cópia ou referência rastreável a esta lei
└── qa/
    └── regressoes/
        ├── README.md                 # Como funciona e como executar verificações
        ├── BASELINE.md               # Estado inicial e problemas preexistentes
        ├── REGISTRO.md               # Índice dos bugs, status e testes associados
        ├── casos/                    # Um arquivo BUG-0001.md por problema confirmado
        ├── fixtures/                 # Apenas se forem necessárias massas de teste
        └── scripts/                  # Apenas se forem necessários utilitários de teste
```

**Importante:** os **testes executáveis devem preferencialmente ficar na estrutura nativa de testes do projeto** (`tests/`, `test/`, `__tests__/`, `e2e/` ou equivalente). A pasta `qa/regressoes/` organiza histórico, rastreabilidade, comandos e evidências. Não crie um segundo framework de testes sem justificativa.

Na primeira ativação:

1. Preserve instruções e configurações já existentes; não sobrescreva `AGENTS.md`, `CLAUDE.md`, pipelines ou scripts de teste.
2. Garanta que a lei esteja acessível no repositório em `leis/LEI_01_NAO_REGRESSAO.md`, copiando o arquivo recebido quando necessário e possível.
3. Crie `qa/regressoes/README.md`, `BASELINE.md` e `REGISTRO.md` com dados reais do projeto. Use "não verificado" para informações indisponíveis, nunca dados inventados.
4. Integre, se aplicável, um comando único e documentado para executar as verificações de regressão usando a infraestrutura já existente.
5. Quando houver um mecanismo conhecido de instruções persistentes do agente, acrescente **apenas uma referência curta** a esta lei, preservando conteúdo e precedência já existentes. Não presuma que todo agente lê automaticamente os mesmos arquivos.
6. Se já existir um sistema equivalente de incidentes e testes, **adapte-o em vez de recriá-lo**. Documente os caminhos efetivos no `README.md`.

A instalação deve ser **idempotente**: executá-la novamente não pode apagar históricos, sobrescrever testes, duplicar registros ou recriar diretórios desnecessariamente.

### 3.3. Levantamento de problemas anteriores

Consulte históricos ou issues acessíveis para identificar defeitos recorrentes ou correções importantes ainda sem teste. Priorize os riscos mais altos; **não invente bugs nem gere uma grande bateria de testes superficiais para parecer que existe cobertura**. Registre pendências retrospectivas de forma explícita.

## 4. Procedimento obrigatório para cada bug

Sempre que um defeito for relatado pelo usuário, encontrado durante a execução, identificado por um teste ou detectado durante a revisão de código:

1. **Identificar:** verificar se já existe registro equivalente no `REGISTRO.md` ou em `casos/`. Se existir, atualize o caso; não abra uma duplicata.
2. **Classificar:** descrever severidade, funcionalidades afetadas, condições de ocorrência e possível impacto sobre dados, segurança ou usuários.
3. **Registrar:** criar um arquivo `qa/regressoes/casos/BUG-NNNN.md` e adicionar a referência ao índice. Use o próximo identificador numérico disponível, sem reutilizar IDs.
4. **Reproduzir:** demonstrar o problema usando passos verificáveis, dados de teste isolados e resultados observáveis. Não confundir hipótese com causa confirmada.
5. **Criar a proteção:** preferencialmente, escrever um **teste automatizado que falhe na versão defeituosa (RED)** e que represente o comportamento correto esperado.
6. **Corrigir:** implementar a menor alteração segura que resolva a causa do problema, em vez de apenas ocultar sintomas ou suprimir mensagens de erro.
7. **Validar:** verificar que o novo teste agora passa (**GREEN**), executar os testes relevantes já existentes e comparar com o estado inicial. Quando apropriado, executar também build, verificações estáticas e testes de integração.
8. **Persistir:** manter o teste na suíte, registrar o comando usado, o resultado efetivamente observado, os arquivos alterados e o vínculo com commit/PR, se disponível.
9. **Concluir:** marcar `VALIDADO` somente quando houver evidência suficiente. Indicar impedimentos e testes não executados sem mascará-los.

**Regra preferencial: RED → GREEN → REGRESSÃO.** Quando não for possível executar o teste antes da correção (por exemplo, bug intermitente ou ambiente indisponível), documente o motivo. Não invente uma etapa RED que não aconteceu.

## 5. Qual teste criar

Escolha o teste mais simples **que reproduza o risco real**:

| Tipo de problema | Proteção preferencial |
|---|---|
| Regra de negócio, cálculos, validação | Teste unitário com entradas e saídas explícitas |
| Integração entre módulos, banco ou API | Teste de integração isolado |
| Interface, navegação, persistência de estado | Teste de componente ou ponta a ponta (E2E), conforme viabilidade |
| Importação, exportação, edição de arquivos | Fixtures representativas e comparação do resultado gerado |
| Falha dependente de tempo, concorrência ou aleatoriedade | Relógio controlado, seed fixa ou teste de concorrência adequado |
| Defeito visual | Teste de componente ou comparação visual, se a infraestrutura permitir |
| Vulnerabilidade | Teste de segurança específico, sem uso de dados ou sistemas reais não autorizados |
| Desempenho | Benchmark com cenário e limite documentados, evitando thresholds arbitrários |

Regras para todos os testes:

- Valide **comportamentos observáveis**, não somente a existência de funções ou chamadas internas.
- Inclua cenário normal, caso que reproduz o bug e condições de borda relevantes.
- Sempre que houver risco sistêmico, teste a **regra ou invariante violada** em mais de uma entrada ou situação, não apenas o exemplo isolado que revelou o bug.
- Faça asserções capazes de falhar se o defeito retornar; evite testes que sempre passam.
- Não falseie resultados por meio de mocks excessivos; use dependências reais isoladas quando necessário para capturar o defeito.
- Mantenha testes determinísticos, repetíveis, independentes e rápidos na medida do possível.
- Não utilize senhas, tokens, dados pessoais de terceiros, bancos de produção ou serviços pagos sem autorização explícita.
- Use dados sintéticos, fixtures versionadas e ambientes descartáveis; evite alterações destrutivas em dados reais.
- Quando houver intenção explícita de modificar uma regra de negócio, **atualize os testes para a nova especificação**, documentando a mudança. Não mantenha comportamentos antigos só para satisfazer a lei.

### Quando a automação não for viável

**Não invente um teste automatizado.** Registre obrigatoriamente:

1. Motivo técnico específico da impossibilidade atual.
2. Procedimento manual reproduzível, incluindo preparação, passos e resultado esperado.
3. Evidência efetivamente produzida ou indicação de que a verificação está pendente.
4. Proposta de automação futura e condição necessária para implementá-la.
5. Status `PENDENTE_DE_AUTOMACAO`, mesmo se a correção tiver sido aplicada e testada manualmente.

O agente pode concluir que o código foi corrigido, mas **não pode declarar cobertura automática contra regressão inexistente**. Peça decisão do responsável quando a ausência de automação envolver risco elevado.

## 6. Prevenção contínua durante novas funcionalidades

Antes de qualquer alteração significativa:

1. Identifique os módulos, contratos, dados e fluxos que serão afetados.
2. Consulte o `REGISTRO.md` e procure testes de regressão relacionados.
3. Execute os testes relevantes ou registre por que não foram executados.
4. Faça as modificações preservando funcionalidades não envolvidas na solicitação.
5. Execute novamente os testes impactados e os novos testes necessários.
6. Antes de entregar ou publicar uma mudança importante, execute a suíte completa viável e o build apropriado, documentando falhas e limitações.

Ao criar funcionalidades novas, escreva testes para as **regras críticas** e os **riscos introduzidos**, mesmo que nenhum bug tenha sido relatado ainda. Não é necessário gerar um teste trivial para cada linha de código.

Quando um teste antigo falhar após uma alteração, investigue antes de apagá-lo, enfraquecer suas asserções, marcá-lo como `skip` ou modificar seus resultados esperados. Só altere a proteção se a especificação realmente mudou ou se o teste estava comprovadamente errado; documente a decisão.

## 7. Automação e bloqueios de qualidade

- Se o repositório já possuir CI, integre os testes de regressão ao pipeline apropriado, aproveitando os jobs existentes.
- Sempre que possível, exponha um comando reproduzível, como o script nativo de testes do projeto, para executar a suíte de regressão localmente.
- Falhas de testes obrigatórios **devem bloquear a declaração de que a mudança foi validada** e, quando o pipeline permitir, bloquear merge ou deploy.
- Se não houver CI, forneça o comando local, documente a limitação e proponha a integração mínima adequada ao provedor real do repositório. Não invente infraestrutura, permissões ou segredos.
- Testes antigos que já falhavam no baseline não devem ser confundidos com regressões novas. Registre-os como dívida técnica identificada, com plano de resolução; não os esconda.
- Testes instáveis (*flaky*) exigem investigação. Se houver isolamento temporário, identifique o caso, a justificativa, a duração e o responsável; não adote `skip` permanente silencioso.
- O agente só identifica problemas automaticamente **quando algum diagnóstico, teste, revisão ou pipeline efetivamente é executado**. Não prometa detecção contínua sem infraestrutura configurada.

## 8. Padrão obrigatório de registro

### 8.1. Índice `qa/regressoes/REGISTRO.md`

Mantenha uma tabela simples, com links relativos válidos:

```markdown
| ID | Título | Severidade | Status | Teste / verificação |
|---|---|---|---|---|
| BUG-0001 | [Descrição objetiva] | alta | VALIDADO | tests/.../test_bug_0001... |
```

Use `ABERTO`, `EM_CORRECAO`, `VALIDADO` ou `PENDENTE_DE_AUTOMACAO` como status. `VALIDADO` exige evidência documentada; quando apenas houver teste manual, mantenha `PENDENTE_DE_AUTOMACAO` e informe a correção separadamente.

### 8.2. Caso individual `qa/regressoes/casos/BUG-NNNN.md`

Crie cada registro com este formato, preenchendo somente informações apuradas:

```markdown
# BUG-NNNN — [Título objetivo]

- **Status:** ABERTO | EM_CORRECAO | VALIDADO | PENDENTE_DE_AUTOMACAO
- **Data de identificação:** AAAA-MM-DD
- **Severidade:** crítica | alta | média | baixa
- **Origem:** usuário | teste | agente | produção | outro
- **Área afetada:** [módulo / tela / serviço]
- **Versão / ambiente:** [quando conhecido]

## Comportamento observado
[O que efetivamente ocorre; com evidências disponíveis.]

## Comportamento esperado
[Regra que deve continuar funcionando.]

## Como reproduzir
[Passos, entradas, condições e resultado.]

## Diagnóstico e causa raiz
[Confirmada, provável ou ainda desconhecida; nunca inventar.]

## Proteção contra regressão
- Teste ou verificação: [caminho relativo / referência]
- Tipo: [unitário / integração / E2E / visual / manual / outro]
- Comando: [comando efetivamente utilizado]
- RED (antes da correção): [resultado real ou motivo de não execução]
- GREEN (depois da correção): [resultado real ou pendência]
- Suítes adicionais executadas: [resultados reais]

## Solução e impacto
[Resumo da alteração, arquivos relevantes e riscos residuais.]

## Rastreabilidade
[Commit, pull request, issue ou "não disponível".]

## Pendências
[Etapas futuras, limitações e justificativas; ou "nenhuma".]
```

Não preencha caminhos, comandos, saídas de testes ou IDs de commits fictícios. Se a data não estiver disponível, assinale-a como não verificada.

## 9. Proibições expressas

O agente **não deve**:

1. Corrigir um bug confirmado e ignorar seu registro.
2. Apagar ou enfraquecer testes somente para obter resultado verde.
3. Declarar o projeto livre de regressões com base em uma execução parcial.
4. Confundir "o aplicativo abriu" ou "compilou" com validação do comportamento corrigido.
5. Gerar centenas de testes irrelevantes para inflar quantidade ou cobertura.
6. Instalar frameworks pesados, reestruturar o projeto inteiro ou modificar produção sem necessidade e autorização compatível com o risco.
7. Expor dados sensíveis ou executar testes destrutivos em produção.
8. Sobrescrever históricos, registros, fixtures e instruções existentes.
9. Informar que um teste passou sem tê-lo executado ou sem evidência acessível.
10. Omitir falhas existentes, ambientes indisponíveis ou limites da validação.

## 10. Critérios de aceite e resposta do agente

### A instalação da lei estará concluída quando

- [ ] A pasta `qa/regressoes/` e seus documentos mínimos existirem ou houver equivalente claramente documentado.
- [ ] O funcionamento do sistema de registro estiver documentado.
- [ ] A suíte de testes existente e os comandos reais forem identificados.
- [ ] Houver um baseline real ou uma indicação honesta do que não pôde ser verificado.
- [ ] O mecanismo de execução recorrente (CI ou procedimento local) estiver identificado e, se viável, integrado.
- [ ] A lei estiver acessível para aplicações futuras no projeto.

### Uma correção estará protegida contra regressão quando

- [ ] O defeito estiver identificado e registrado sem duplicidade.
- [ ] O comportamento esperado estiver descrito de forma verificável.
- [ ] Existir teste automatizado relevante e persistente que detecte o retorno do problema.
- [ ] A evidência RED estiver registrada quando foi possível obtê-la.
- [ ] O teste passar após a correção e as verificações impactadas não apresentarem novas falhas.
- [ ] O índice e o caso individual estiverem atualizados com resultados efetivamente observados.

Se a automação for inviável, **não marque todos os itens como completos**: declare a correção como aplicada, a automação como pendente e informe o risco residual.

### Formato do relatório ao usuário

Ao terminar a instalação ou uma correção, apresente, de forma breve:

1. **O que mudou:** arquivos criados/alterados e comportamento corrigido.
2. **Qual bug foi registrado:** ID, gravidade e localização do caso.
3. **Qual teste protege a correção:** caminho, comando e cenário coberto.
4. **Resultado real:** RED (se executado), GREEN, testes existentes, build e limitações.
5. **O que ficou pendente:** riscos ou verificações ainda não executadas.

**Princípio final:** não basta resolver o erro de hoje. Cada correção deve aumentar a capacidade do projeto de reconhecer, por conta de testes persistentes, quando aquele mesmo erro tentar voltar.
