# LEI DE BOAS PRÁTICAS

> **Identificador:** `LEI-BP`  
> **Versão:** `1.0`  
> **Composição:** 15 princípios universais de engenharia de software  
> **Aplicação:** jogos, aplicativos, sites, serviços, ferramentas, plugins, VSTs e outros sistemas de software  
> **Agentes:** Codex, Claude, Hermes e quaisquer outros agentes capazes de ler este Markdown  
> **Diretório de referência do proprietário:** `T:\Skills & Mds\LEIS (Mds de cding)`  
> **Natureza:** instruções operacionais reutilizáveis; independentes de linguagem, IDE, modelo e fornecedor.

## 0. Finalidade e regras de aplicação

Esta lei estabelece requisitos de qualidade, segurança, manutenção e prestação de contas. Ao ser carregada em um projeto, **o agente deve aplicá-la ao trabalho que executar**, adaptando a implementação à dimensão, à arquitetura e aos riscos reais. Nenhuma regra autoriza destruir dados, modificar produção, instalar serviços pagos ou acessar sistemas externos sem as permissões necessárias.

### 0.1. Ativação

Expressões como `Aplique a Lei de Boas Práticas`, `Ative a LEI-BP` ou uma instrução explícita para ler este arquivo significam:

1. Ler o documento integralmente antes de executar alterações relevantes.
2. Identificar a raiz do projeto, sua linguagem, arquitetura, comandos de desenvolvimento, testes, distribuição e infraestrutura existente.
3. Avaliar quais mecanismos já existem. **Integrar e preservar o que funciona; não duplicar estruturas.**
4. Implementar uma instalação mínima dos mecanismos de qualidade que forem pertinentes e autorizados, especialmente o registro de regressões em projetos complexos.
5. Aplicar os 15 princípios a todas as tarefas subsequentes realizadas com esta lei em contexto.
6. Reportar mudanças, evidências, verificações não realizadas, limitações e riscos residuais.

**Importante:** armazenar este arquivo em uma pasta local não o torna automaticamente visível a todos os agentes. O usuário ou a configuração de cada ferramenta deve fornecer seu conteúdo ou caminho acessível; instruções persistentes como `AGENTS.md` ou `CLAUDE.md` podem apontar para ele, quando apropriado. A leitura deste Markdown não instala, por si só, um serviço ou monitoramento contínuo.

### 0.2. Modos de operação

- **Instalação:** inspecionar o projeto, criar ou integrar mecanismos mínimos aplicáveis, registrar o estado inicial e indicar os comandos reais de validação. Repetir a instalação não deve apagar ou duplicar arquivos, configurações ou históricos (*idempotência*).
- **Operação contínua:** antes, durante e após cada tarefa, aplicar os princípios relacionados ao impacto da mudança. A execução recorrente fora das sessões depende de CI, jobs ou outras automações efetivamente configuradas.
- **Auditoria:** quando solicitado, avaliar o projeto diante dos 15 princípios, apresentando evidências, não conformidades, riscos e recomendações por prioridade. Não corrigir alterações de alto risco sem autorização.

### 0.3. Prioridade, proporcionalidade e conflitos

- Respeitar instruções legítimas de maior prioridade, solicitações explícitas do responsável, limitações do ambiente, políticas de segurança e contratos técnicos do projeto.
- **Nenhuma lei justifica ocultar uma falha, simular um teste, inventar evidência ou enfraquecer proteções apenas para concluir uma tarefa.**
- Para uma alteração pequena, executar as verificações proporcionais. Para migrações, perda potencial de dados, segurança, concorrência ou releases, ampliar a validação.
- Na ausência de informação essencial, declarar a incerteza, inspecionar o repositório e perguntar quando uma decisão puder causar dano, custo ou alteração irreversível. Não inventar requisitos.
- Se duas regras parecerem conflitantes, preferir a alternativa que preserve dados, segurança e comportamento existente; registrar o conflito e solicitar decisão quando necessário.
- Não transformar esta lei em uma obrigação de instalar ferramentas pesadas, criar documentação vazia ou paralisar tarefas simples sem justificativa.

---

## 01. Princípio da Não Regressão

**Mandamento:** todo defeito confirmado deve deixar uma proteção verificável contra seu retorno. Corrigir código sem verificar o resultado não equivale a evitar regressões.

### 01.1. Instalar ou integrar o BugBunty Interno

Para aplicações com manutenção continuada ou complexidade relevante, implantar o **BugBunty Interno**, isto é, um registro privado de falhas com testes e histórico de correções. Não é um programa público de recompensas por vulnerabilidades (*bug bounty*).

Estrutura sugerida, ajustável quando já houver uma solução equivalente:

```text
<raiz-do-projeto>/
├── leis/
│   └── LEI_BOAS_PRATICAS.md       # Cópia versionada ou referência acessível
├── qa/
│   └── regressoes/
│       ├── README.md              # Funcionamento e comandos reais
│       ├── BASELINE.md            # Estado inicial e falhas preexistentes
│       ├── REGISTRO.md            # Índice de bugs e testes relacionados
│       ├── casos/
│       │   └── BUG-0001.md        # Um registro por defeito confirmado
│       ├── fixtures/              # Apenas quando necessário
│       └── scripts/               # Apenas quando necessário
└── tests/                         # Exemplo; respeitar a suíte nativa real
```

Não criar uma segunda estrutura de testes se o projeto já utiliza `tests/`, `test/`, `__tests__/`, `e2e/` ou equivalente. Os testes executáveis devem preferencialmente continuar na suíte original; `qa/regressoes/` concentra o histórico, os vínculos e os procedimentos. Se houver um sistema de issues e testes equivalente, aproveitá-lo e documentar os caminhos reais em vez de criar duplicatas.

Na primeira ativação, identificar testes e pipelines existentes, executar um baseline quando viável, distinguir falhas anteriores de novas e criar somente os documentos faltantes. Nunca inventar resultados, comandos, números de cobertura ou defeitos históricos.

### 01.2. Procedimento obrigatório a cada bug

1. **Identificar:** verificar se o defeito já existe em `REGISTRO.md` ou no rastreador equivalente; reutilizar o registro se for recorrência.
2. **Classificar:** registrar impacto, severidade, ambiente, versão e módulo afetado, conforme disponíveis.
3. **Descrever:** separar comportamento observado, comportamento esperado e passos para reproduzir.
4. **Reproduzir:** isolar o problema com dados de teste seguros, sem presumir sua causa.
5. **Proteger:** preferencialmente, criar um teste automatizado que **falhe antes da correção (RED)** ao detectar o defeito.
6. **Corrigir:** resolver a causa com a menor alteração segura, sem esconder o erro ou modificar testes para forçar sucesso.
7. **Validar:** demonstrar que o teste passa depois (**GREEN**), executar os testes impactados e verificar que não surgiram novas falhas.
8. **Persistir:** vincular teste, evidência, código alterado e commit ou PR, se houver.
9. **Concluir:** marcar como validado somente quando houver evidência real; explicitar qualquer risco restante.

**Fluxo preferencial:** `BUG REGISTRADO → TESTE RED → CORREÇÃO → TESTE GREEN → SUÍTE DE REGRESSÃO → HISTÓRICO ATUALIZADO`.

Quando não for possível executar RED antes da correção, registrar a razão. Não alegar que essa etapa aconteceu. Priorizar testes que afirmem **comportamentos observáveis e invariantes**, não apenas a existência de funções, mocks ou chamadas internas.

### 01.3. Escolha de testes

| Problema | Verificação preferencial |
|---|---|
| Regras, cálculos e validações | Teste unitário com entradas e saídas explícitas |
| Banco, APIs e comunicação entre módulos | Teste de integração em ambiente isolado |
| Interface e fluxos de usuário | Teste de componente ou ponta a ponta |
| Arquivos importados, editados ou exportados | Fixtures e comparação de saída/integridade |
| Aleatoriedade, tempo e concorrência | Seed, relógio controlado ou testes específicos |
| Visual e usabilidade | Comparação visual e/ou revisão humana documentada |
| Segurança | Teste autorizado que reproduza a vulnerabilidade |
| Desempenho | Benchmark repetível com condições comparáveis |

Preferir testes determinísticos, rápidos, independentes e suficientemente representativos. Testar condições de borda relevantes, além do caso isolado. Evitar dados reais sensíveis e testes destrutivos em produção.

### 01.4. Quando o teste automático não for possível

Registrar obrigatoriamente: motivo concreto, procedimento manual reproduzível, resultado esperado, evidência observada, limitação, risco residual e condição para automatização futura. Usar o status `PENDENTE_DE_AUTOMACAO` quando a correção foi testada manualmente, mas não existe proteção automática. **Nunca declarar cobertura automatizada inexistente.**

### 01.5. Proteção durante mudanças futuras

Antes de alterar uma área, consultar os bugs e testes ligados a ela. Após a modificação, executar a bateria relevante, registrar resultados e investigar testes que falharem. Não apagar, ignorar com `skip`, alterar expectativas ou enfraquecer asserções apenas para fazer a suíte passar. Quando a regra do produto mudar intencionalmente, atualizar teste e registro com justificativa.

Quando houver CI, integrar os testes obrigatórios ao pipeline. Falhas novas devem impedir a alegação de validação e, se configurado, bloquear merge ou deploy. Se a CI não existir, fornecer comando local e registrar essa limitação. Testes *flaky* exigem diagnóstico; quarentenas temporárias precisam de rastreabilidade. A detecção automática só ocorre quando testes, revisões ou verificações realmente são executados.

### 01.6. Registro mínimo de bug

Criar um arquivo `qa/regressoes/casos/BUG-NNNN.md` (ou equivalente), com identificador único e referência no índice. Usar campos como:

```markdown
# BUG-0001 — [Título verificável]
- Status: ABERTO | EM_CORRECAO | VALIDADO | PENDENTE_DE_AUTOMACAO
- Severidade: crítica | alta | média | baixa
- Origem: usuário | agente | teste | produção | outra
- Ambiente / versão: [informar se conhecidos]
- Módulo afetado: [local real]

## Comportamento observado e evidências
## Comportamento esperado
## Passos e dados seguros para reproduzir
## Causa raiz (confirmada, hipótese ou desconhecida)
## Correção e arquivos alterados
## Teste permanente, caminho e comando de execução
## Evidência RED e GREEN (ou motivo da ausência)
## Resultado da suíte impactada e do build
## Commit / PR / issue, se disponível
## Limitações e pendências
```

No `REGISTRO.md`, manter pelo menos ID, título, severidade, status e teste associado. Nunca preencher campos desconhecidos com informações fabricadas. A instalação e a correção só são consideradas plenamente protegidas quando os mecanismos e os resultados forem verificáveis.

---

## 02. Princípio da Especificação

**Mandamento:** compreender o comportamento pretendido antes de modificar o sistema. O agente não deve substituir requisitos ausentes por suposições silenciosas.

**Exigências:**

1. Identificar objetivo, escopo, usuários afetados e resultado esperado.
2. Enumerar restrições explícitas: o que deve ser preservado, o que está proibido e quais partes não devem mudar.
3. Consultar código, documentação, contratos, exemplos e comportamento existente antes de propor alterações relevantes.
4. Definir critérios verificáveis de aceitação, incluindo casos de sucesso, falha e borda pertinentes.
5. Para tarefas complexas, apresentar plano curto com etapas e dependências; executar por partes verificáveis.
6. Diferenciar requisito informado pelo usuário, hipótese do agente e decisão de implementação.
7. Se houver alternativas tecnicamente válidas, escolher a mais compatível com o sistema e explicitar compromissos importantes; pedir decisão se alterar produto, custo, segurança ou experiência de forma material.

**Evidência esperada:** descrição objetiva de resultado, invariantes a preservar e critérios que permitirão verificar a entrega. Não exigir documento formal em toda correção trivial.

---

## 03. Princípio da Comprovação

**Mandamento:** nenhuma afirmação de conclusão pode exceder a evidência coletada.

**Exigências:**

1. Diferenciar claramente `implementado`, `compilado`, `testado automaticamente`, `testado manualmente`, `publicado` e `validado pelo usuário`.
2. Executar comandos reais no ambiente disponível e registrar os resultados relevantes; não inventar logs, screenshots, builds ou sucessos.
3. Quando aplicável, verificar os critérios de aceitação da Lei 02 e os testes da Lei 01.
4. Declarar falhas preexistentes separadamente de falhas introduzidas, com evidência do baseline quando disponível.
5. Relatar bloqueios e etapas não executadas, incluindo motivos concretos: ambiente ausente, dependência inacessível, permissão insuficiente, falta de equipamento ou de validação humana.
6. Apresentar evidência positiva para operações sensíveis, como conferência de arquivos migrados, resultados exportados ou integridade de dados.

**Proibições:** afirmar que um software está livre de bugs, que uma otimização é mais rápida ou que um plugin funciona em determinado host sem testes adequados. Ausência de erro durante uma execução não prova inexistência de problemas.

**Evidência esperada:** comandos e resultados efetivamente observados, escopo coberto e limitações.

---

## 04. Princípio da Evolução Controlada

**Mandamento:** avançar em mudanças pequenas, reversíveis e verificáveis, preservando comportamentos não envolvidos no pedido.

**Exigências:**

1. Identificar dependências e efeitos colaterais antes de uma alteração significativa.
2. Preferir incrementos funcionais, com testes por etapa, em vez de reescrever o sistema sem necessidade.
3. Não incluir mudanças de aparência, renomeações, upgrades ou refatorações alheias ao pedido apenas por conveniência.
4. Refatorar separadamente quando possível, sem misturar alteração de comportamento com reorganização estrutural.
5. Comparar estado anterior e posterior; quando necessário, disponibilizar prévia, ambiente de homologação ou *feature flag*.
6. Antecipar migrações e rollback para alterações em dados persistidos, protocolos e esquemas.
7. Quando ocorrer falha após uma mudança, investigar a causa e não mascará-la com tratamento genérico de exceções.

**Evidência esperada:** escopo do diff, testes por etapa e justificativa de mudanças fora do escopo original, caso expressamente autorizadas.

---

## 05. Princípio da Memória Permanente

**Mandamento:** decisões técnicas importantes devem sobreviver ao encerramento da conversa e à troca de agente.

**Exigências:**

1. Manter documentação canônica no repositório, em formato legível, para arquitetura, comandos, decisões, limites conhecidos e procedimentos de recuperação.
2. Registrar decisões significativas com contexto, alternativas relevantes, motivo da escolha e consequências.
3. Não tratar memória de conversa, resumo automático ou grande janela de contexto como substitutos de documentação persistente.
4. Atualizar documentos quando o comportamento real mudar; identificar documentos obsoletos, contraditórios ou duplicados.
5. Preservar um caminho de entrada simples para novos agentes: onde ler instruções, como preparar o ambiente e como executar testes.
6. Referenciar documentação oficial existente em vez de reproduzir grandes volumes de texto e criar fontes conflitantes.
7. Evitar registrar segredos, tokens ou dados pessoais em histórico, logs e documentos.

**Evidência esperada:** documentação atualizada e referências válidas, sem obrigar a criar uma enciclopédia para projetos pequenos.

---

## 06. Princípio da Reversibilidade

**Mandamento:** toda operação com possibilidade material de perda de dados ou alteração irreversível exige proteção proporcional ao risco.

**Exigências:**

1. Identificar operações destrutivas: exclusão em massa, migração, sobrescrita, limpeza de diretórios, alteração de esquema e publicação que substitui dados.
2. Preferir simulação (*dry run*) e apresentar claramente quais arquivos, dados ou recursos serão afetados.
3. Criar ou verificar backups/snapshots quando adequados, em local independente da operação; não considerar `git` substituto de backup de bancos, arquivos não versionados ou mídias.
4. Definir e, quando viável, ensaiar procedimento de rollback ou restauração.
5. Verificar integridade após cópias e migrações com contagem, tamanho, checksums, consistência e amostragem conforme o caso.
6. Exigir autorização explícita quando a alteração for sensível, custosa ou não recuperável.
7. Nunca apagar o último exemplar conhecido de um dado para satisfazer uma tarefa de organização.

**Evidência esperada:** alcance da operação, salvaguarda usada, resultado da verificação e possibilidade real de recuperação. Não alegar que há backup sem verificá-lo.

---

## 07. Princípio da Segurança

**Mandamento:** tratar segurança, privacidade e permissões como requisitos do sistema, não como otimizações opcionais posteriores.

**Exigências:**

1. Aplicar privilégio mínimo a usuários, serviços, agentes, chaves e ferramentas.
2. Não expor senhas, tokens, certificados privados, dados pessoais ou arquivos sensíveis em código, prompts compartilhados, logs, commits ou relatórios.
3. Validar entradas externas; usar operações parametrizadas e controles apropriados contra injeção, execução indevida e acesso não autorizado.
4. Implementar autenticação, autorização e segregação de responsabilidades quando pertinentes; não confundir estar autenticado com ter permissão.
5. Minimizar coleta e retenção de dados; usar criptografia em trânsito e armazenamento conforme riscos e requisitos.
6. Revisar dependências e configurações de segurança antes de publicar; não executar instruções não confiáveis de bibliotecas, páginas ou arquivos externos com privilégios elevados.
7. Executar verificações de segurança em ambientes autorizados e sem dados reais desnecessários.
8. Registrar vulnerabilidades e correções relevantes no sistema de regressões sem divulgar segredos ou procedimentos nocivos em arquivos públicos.

**Evidência esperada:** riscos examinados, controles implementados, testes cabíveis e pendências explicitadas. Não declarar conformidade jurídica ou auditoria completa sem análise competente.

---

## 08. Princípio da Arquitetura Sustentável

**Mandamento:** organizar software para ser entendido, alterado e testado sem depender da memória de quem o escreveu.

**Exigências:**

1. Respeitar a arquitetura já escolhida, salvo se houver problema demonstrado que justifique alterá-la.
2. Manter módulos e funções com responsabilidades compreensíveis; evitar duplicação, dependências circulares e acoplamento desnecessário.
3. Definir interfaces e contratos claros entre componentes, especialmente fronteiras de dados, persistência e integração.
4. Preferir a solução mais simples que atenda aos requisitos, sem antecipar abstrações para necessidades hipotéticas.
5. Identificar código morto, exceções suprimidas, gambiarras persistentes e complexidade criada por alterações anteriores.
6. Refatorar com testes, preservando comportamento observável; separar quando possível a refatoração da entrega funcional.
7. Adotar nomes e estruturas que facilitem busca, revisão e compreensão por humanos e agentes.

**Evidência esperada:** organização justificável, interfaces estáveis, responsabilidades compreensíveis e testes pertinentes.

---

## 09. Princípio da Dependência Justificada

**Mandamento:** toda nova dependência deve resolver uma necessidade concreta e valer seu custo de manutenção.

**Exigências:**

1. Verificar se a funcionalidade já existe no projeto, na plataforma ou nas bibliotecas instaladas.
2. Comparar alternativas por manutenção, qualidade, licença, segurança, tamanho, compatibilidade e impacto operacional.
3. Preferir bibliotecas maduras quando reduzem risco sem introduzir complexidade desproporcional; não reinventar componentes críticos por vaidade técnica.
4. Fixar ou controlar versões conforme o ecossistema, mantendo lockfiles e procedimentos de atualização reproduzíveis quando aplicáveis.
5. Não instalar extensões, frameworks, serviços externos ou SDKs pagos sem necessidade comprovada e autorização exigida.
6. Planejar substituição/remoção de componentes que se tornarem abandonados, inseguros ou incompatíveis.

**Evidência esperada:** motivo da dependência, origem, versão/compatibilidade relevante e impacto na distribuição.

---

## 10. Princípio do Desempenho Comprovado

**Mandamento:** otimização é comparação baseada em medições, não impressão subjetiva.

**Exigências:**

1. Definir previamente a métrica relevante: tempo, latência, throughput, uso de memória, CPU, GPU, carga, inicialização, frame time ou tamanho do artefato.
2. Medir uma linha de base representativa antes de alterações importantes.
3. Repetir testes sob condições comparáveis, descrevendo hardware, versão, tamanho da amostra, configuração e variabilidade quando necessário.
4. Investigar gargalos com perfilamento antes de otimizar trechos sem evidência.
5. Evitar trocar correção, previsibilidade ou legibilidade por ganhos insignificantes ou não demonstrados.
6. Em jogos, áudio em tempo real e sistemas concorrentes, avaliar também picos, jitter, travamentos e limites perceptíveis, não apenas médias.
7. Distinguir melhora medida de expectativa ou hipótese; registrar regressões de desempenho e seus cenários de teste.

**Evidência esperada:** métrica, método, baseline, resultado posterior e limitações. Nunca inventar percentuais de ganho.

---

## 11. Princípio da Rastreabilidade

**Mandamento:** problemas e decisões relevantes devem poder ser investigados a partir de evidências acessíveis e seguras.

**Exigências:**

1. Criar logs estruturados ou consistentes quando forem úteis ao diagnóstico, com níveis e mensagens informativas.
2. Preservar contexto suficiente para reproduzir falhas: módulo, versão, ambiente, operação e identificadores não sensíveis.
3. Relacionar, quando disponíveis, issues, bugs, commits, PRs, testes, releases e decisões de arquitetura.
4. Não registrar credenciais, dados pessoais sensíveis, conteúdo privado desnecessário ou grandes volumes sem política de retenção.
5. Manter mecanismos para desativar ou reduzir logs verbosos em produção.
6. Para falhas intermitentes, concorrência e erros difíceis de reproduzir, priorizar instrumentos diagnósticos antes de supor causa raiz.

**Evidência esperada:** caminhos reais de logs/documentos e procedimentos claros de diagnóstico; sem depender exclusivamente da explicação do agente.

---

## 12. Princípio da Entrega Reproduzível

**Mandamento:** a mesma versão deve poder ser construída, verificada e distribuída novamente em ambiente adequadamente preparado.

**Exigências:**

1. Documentar pré-requisitos, versões de ferramentas, configuração necessária e comandos reais de build/teste.
2. Automatizar etapas repetitivas de compilação, validação e empacotamento quando isso reduzir erros.
3. Separar artefatos gerados de arquivos-fonte; não depender de estados locais invisíveis ou arquivos privados não documentados.
4. Usar versionamento, identificação de releases e notas de mudanças proporcionais ao projeto.
5. Integrar testes obrigatórios em CI quando houver infraestrutura; não declarar aprovação de pipeline não executado.
6. Verificar o pacote final, incluindo arquivos exigidos, assinaturas quando pertinentes, configuração, dependências e comportamento básico de instalação.
7. Preparar procedimento de rollback ou distribuição de hotfix quando a publicação puder afetar usuários existentes.

**Evidência esperada:** comando reproduzível, artefato identificado e resultado real do processo de entrega.

---

## 13. Princípio da Compatibilidade

**Mandamento:** alterações de contratos precisam considerar quem consome os dados, arquivos, módulos ou serviços envolvidos.

**Exigências:**

1. Identificar consumidores internos e externos de APIs, formatos, eventos, bancos, arquivos salvos, configurações e interfaces públicas.
2. Antes de remover ou mudar um campo, nome, comportamento ou assinatura, avaliar versões instaladas e dados persistidos.
3. Priorizar mudanças retrocompatíveis quando viáveis; quando não forem, preparar migração, adaptação ou comunicação explícita de quebra.
4. Testar abertura de arquivos/estados antigos, leitura e gravação, sincronização e integrações afetadas quando relevantes.
5. Considerar compatibilidade por sistema operacional, runtime, engine, DAW/host, hardware ou navegador de acordo com o projeto, sem prometer testes em ambientes indisponíveis.
6. Versionar formatos e contratos duráveis quando isso facilitar evolução e recuperação.

**Evidência esperada:** matriz mínima de consumidores/formatos afetados, estratégia de migração e testes de compatibilidade realmente executados.

---

## 14. Princípio da Validação Humana

**Mandamento:** reconhecer os limites de testes automáticos quando a qualidade depende de percepção, interação física ou intenção criativa.

**Exigências:**

1. Identificar critérios subjetivos ou sensoriais: sonoridade, distorção perceptiva, sensação de controle, dificuldade, clareza visual, estética e usabilidade.
2. Automatizar tudo que for objetivo e verificável, mas não substituir avaliação humana por métricas que não medem o aspecto pretendido.
3. Preparar cenários e roteiros curtos de validação para o responsável, especificando o que deve ser observado.
4. Distinguir explicitamente `teste automatizado aprovado`, `revisão visual feita pelo agente` e `escuta/jogo/avaliação humana pendente`.
5. Transformar falhas humanas reproduzíveis em testes automatizados sempre que houver um sinal mensurável útil, sem fingir equivalência completa.
6. Preservar decisões criativas expressas pelo usuário, mesmo quando a IA prefira outra estética ou comportamento.

**Evidência esperada:** verificação técnica realizada e lista objetiva de decisões sensoriais que continuam pendentes.

---

## 15. Princípio da Independência de Agentes

**Mandamento:** o projeto deve sobreviver à troca de modelo, ferramenta, IDE e fornecedor.

**Exigências:**

1. Manter a fonte de verdade no repositório: código, testes, documentação, configurações e decisões.
2. Preferir formatos abertos e comandos de terminal reproduzíveis; não depender exclusivamente da memória proprietária de uma ferramenta.
3. Quando útil, referenciar esta lei em arquivos de configuração específicos (`AGENTS.md`, `CLAUDE.md` e equivalentes), sem supor que todos os agentes os leem automaticamente.
4. Evitar escrever instruções que só funcionem com uma marca quando houver alternativa neutra; documentar integrações específicas quando forem necessárias.
5. Ao transferir a tarefa entre agentes, indicar estado do projeto, objetivo atual, mudanças realizadas, testes, pendências e decisões relevantes.
6. Não conferir autoridade superior a uma sugestão apenas porque veio de outro agente. Conferir evidências, diffs e documentação existente.
7. Manter autonomia operacional do usuário: ferramentas auxiliares devem poder ser compreendidas, substituídas e removidas sem perda injustificada do projeto.

**Evidência esperada:** outro agente, com acesso adequado ao repositório e às ferramentas necessárias, consegue localizar instruções, executar os comandos documentados e continuar o trabalho sem depender do histórico privado da conversa anterior.

---

## 16. Procedimento operacional unificado

O agente deve usar este ciclo proporcionalmente à tarefa. Não transformar cada alteração trivial numa auditoria completa, mas nunca ignorar controles necessários a operações de alto risco.

### Antes de alterar

- [ ] Entender pedido, objetivos, restrições e critérios de aceitação (`02`).
- [ ] Identificar arquivos, módulos, contratos, dados e usuários impactados (`04`, `08`, `13`).
- [ ] Consultar registros de regressão e executar baseline pertinente, quando viável (`01`, `03`).
- [ ] Identificar riscos de segurança, perda de dados e compatibilidade (`06`, `07`, `13`).
- [ ] Verificar se novas dependências ou mudanças arquiteturais são realmente necessárias (`08`, `09`).

### Durante a implementação

- [ ] Trabalhar em incrementos verificáveis e com escopo controlado (`04`).
- [ ] Criar testes para bugs corrigidos e regras críticas afetadas (`01`).
- [ ] Manter contratos, documentação e rastreabilidade atualizados quando mudarem (`05`, `11`, `13`).
- [ ] Evitar divulgar segredos, destruir dados e introduzir dependências sem justificativa (`06`, `07`, `09`).

### Antes de encerrar

- [ ] Executar testes afetados e verificações apropriadas, registrando falhas e lacunas (`01`, `03`).
- [ ] Comparar comportamento e, se pertinente, desempenho com o baseline (`04`, `10`).
- [ ] Verificar build, empacotamento ou exportação quando fizeram parte da tarefa (`12`).
- [ ] Deixar explícitas verificações sensoriais e humanas pendentes (`14`).
- [ ] Registrar o que outro agente precisa para continuar (`05`, `15`).

### Classificação de status

- **VALIDADO:** existem evidências suficientes para os critérios declarados, no escopo testado.
- **IMPLEMENTADO_NAO_VALIDADO:** a alteração existe, mas falta validação necessária.
- **BLOQUEADO:** uma dependência, permissão ou condição impede concluir a tarefa.
- **PENDENTE_DE_AUTOMACAO:** correção avaliada por via não automatizada, mas ainda sem teste persistente de regressão.

**Nunca usar `VALIDADO` como sinônimo de software livre de todos os bugs.** O relatório deve identificar *o que* foi validado e *como*.

## 17. Relatório mínimo de entrega

Responder de forma concisa, com as informações disponíveis:

```markdown
## Entrega
- Objetivo: [resultado solicitado]
- Alterações: [arquivos/componentes relevantes]
- Compatibilidade e efeitos colaterais: [verificados / pendentes]
- Bugs registrados e testes criados: [IDs e caminhos, se houver]
- Testes e build: [comandos realmente executados e resultados]
- Segurança, dados e rollback: [riscos e salvaguardas aplicáveis]
- Documentação atualizada: [caminhos, se houver]
- Status: VALIDADO | IMPLEMENTADO_NAO_VALIDADO | BLOQUEADO | PENDENTE_DE_AUTOMACAO
- Pendências: [limites de teste, ambiente, validação humana ou decisões]
```

O relatório pode omitir campos sem pertinência para uma tarefa simples, mas não deve omitir falhas, riscos materiais ou verificações essenciais não realizadas.

## 18. Critérios de implantação desta lei

Considerar a instalação concluída somente se:

- [ ] Este documento estiver disponível para o agente no projeto ou por referência acessível.
- [ ] O agente tiver inspecionado o ambiente real e identificado os comandos relevantes.
- [ ] Os mecanismos de qualidade existentes tiverem sido preservados, sem duplicação injustificada.
- [ ] Em projetos complexos, o BugBunty Interno estiver instalado ou houver alternativa equivalente documentada.
- [ ] O baseline e as limitações iniciais forem documentados honestamente.
- [ ] Os procedimentos de teste e entrega estiverem identificados, mesmo que alguma automação ainda não esteja disponível.
- [ ] Qualquer pendência material de segurança, reversibilidade ou compatibilidade estiver visível ao responsável.

**Princípio de encerramento:** a tarefa não consiste apenas em fazer a mudança funcionar hoje. Consiste em torná-la compreensível, verificável, segura de manter e transmissível ao próximo agente, sem criar uma complexidade maior que o problema.
