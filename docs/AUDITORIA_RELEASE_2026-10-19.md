# Auditoria de preparação da release 0.2.0

## Escopo e sequência

Implementações solicitadas feitas antes da bateria: download explícito/cancelável
de modelos nas configurações, Sobre com tutorial/créditos, ZIP e instalação via
script no DaVinci, publicação em rascunho e CI Windows. Fontes em Python/PySide6,
launcher Lua e instalação PowerShell foram preservadas na arquitetura existente.
Não houve redesign nem mudanças de mídia, sessões ou timeline original.

As três leis canônicas foram lidas e suas cópias conferidas por SHA-256; os
originais externos permanecem inalterados. Registro de regressões integrado ao
existente, sem duplicação de suíte. Baseline anterior: 336 testes aprovados.

## Desempenho medido

Método reproduzível: `scripts/benchmark_planner.py`, três repetições, Python 3.11,
Windows x64, Intel Core i9-12900K. Cinco microfones e uma faixa de vídeo, 24 fps,
fala/retorno sintéticos. Não mede inferência de Whisper, GPU nem latência do Resolve.

| Cenário | Mediana anterior | Mediana final | Operações |
| --- | ---: | ---: | ---: |
| 200 segmentos | 0,0498 s | 0,0255 s | 1.206 |
| 1.000 segmentos | 0,7922 s | 0,2096 s | 6.006 |

No cenário maior, cerca de 3,8 vezes mais rápido. cProfile identificou 10 milhões
de verificações no gerador de mute; busca por faixa com índice de intervalos
substituiu a varredura por operação. Os hashes completos dos planos dos dois
cenários ficaram iguais. O teste persistente compara decisões com a regra anterior,
incluindo intervalos aninhados e fontes previamente desativadas.
Evidências locais: runtime/reports/planner-before.json e planner-final.json.

## Bugs confirmados e protegidos

- BUG-0021: custo quadrático do lookup de mute; índice com mesma regra de contenção.
- BUG-0022: instalador antigo procurava Python em SourceRoot, apesar de instalar em
  outro diretório; corrigido encaminhamento e instalação editável. Teste nativo
  usa stub de Python/pip em APPDATA isolado, sem persistir variáveis do usuário.
- BUG-0023: avisos conhecidos em pip/setuptools/pytest; pisos de versões corrigidos.
- BUG-0024: JSON malformado do subprocesso de download escapava do tratamento de
  erro; formato e caminho agora validados, preservando a configuração anterior.
- BUG-0025: instrumentação herdada pelo ZIP duplicava fontes na cobertura;
  subprocesso da instalação foi isolado, mantendo threshold de 75%.
- BUG-0027: metadados .egg-info entravam no ZIP após liberar TXT; excluídos por
  componente de caminho e protegidos pelo teste real do pacote.
- BUG-0026: referência omitida ou muda podia silenciar a cópia restante; apenas
  faixas audíveis e incluídas podem justificar gating na nova timeline.

Casos, reprodução, RED/GREEN e testes estão em qa/regressoes/casos. Não foi
alegado RED para caminhos que apenas passaram. Nenhum teste antigo foi removido
ou marcado como skip para viabilizar a entrega.

## Segurança e distribuição

pip-audit apontou 12 entradas (IDs duplicados) em três ferramentas; depois das
atualizações, zero avisos conhecidos em 46 distribuições do ambiente de trabalho
e em 45 da instalação de distribuição. Isso é consulta a bases públicas, não
certificação de ausência de vulnerabilidades nem exploração de falhas.

Referências primárias dos avisos: [pip](https://github.com/advisories/GHSA-qwm4-qh6w-59xr),
[pytest](https://github.com/advisories/GHSA-6w46-j5rx-g56g),
[setuptools](https://github.com/pypa/setuptools/releases/tag/v83.0.0).

O pacote seleciona fontes por allowlist, exclui runtime/modelos/mídia/cache/.venv,
traz manifesto SHA-256 e checksum do ZIP. Busca por padrões específicos de tokens
e chaves privadas não encontrou ocorrências nas fontes selecionadas. Essa busca
tem escopo limitado e não substitui revisão de segurança completa.

Instalação real do ZIP em pasta/APPDATA isolados passou, incluindo SHA-256 dos
helpers e um único menu público. Autodiagnóstico da instalação independente passou.
As versões de runtime verificadas estão em requirements/runtime-windows.txt.
A instalação exige Python/FFmpeg externos e internet para dependências, conforme
docs/DISTRIBUICAO.md; não contém drivers CUDA nem pesos.

## Verificações de interface e modelo

Capturas reais do Qt, em runtime/release-visual: configurações 760×600, diálogo
Sobre e download. Conferidos por inspeção; navegação principal também possui
testes em 1000×680 e 1280×820. O link usa a paleta existente. Não é aprovação
estética humana nem captura da janela de trabalho dentro do Resolve.

Download real do modelo tiny concluído em diretório de teste. Carregamento local
CPU INT8 e inferência de um segundo de silêncio sintético passaram, sem envio de
áudio. Isso comprova o mecanismo, não qualidade de transcrição de fala ou GPU.
Interrupção/rede ausente/cache inválido/cancelamento e persistência após Salvar
são cobertos por testes isolados; nenhum modelo do usuário foi trocado.

## Gates e limites

O primeiro gate teve 355 testes aprovados, mas recusou cobertura duplicada. Na
repetição, 355 testes passaram com cobertura de 86%; restou uma formatação HTML,
corrigida. Dois testes adicionais de BUG-0026 passaram na suíte dirigida de 34
casos. A publicação exige gate completo posterior a essas correções, sem skips,
e recusa fontes alteradas durante a execução. A evidência final sanitizada é
incluída no asset .validation.json da release; logs locais em runtime/regression.

Nenhum Rough Cut real nem escuta humana foi executado nesta rodada. BUG-0017
(travamento anterior do executor técnico real) continua PENDENTE_DE_AUTOMACAO;
não foi repetida a sequência de mutações que travou o host. Qualidade de áudio,
instalação em outro computador e uso editorial real ainda exigem avaliação humana.
Zoom/texto continuam limitados às capacidades comprovadas; não são novos backends.

A CI é configurada para executar o mesmo gate no GitHub Actions. Seu resultado
remoto precisa ser conferido na execução correspondente; a existência do YAML
não significa que rodou. A publicação cria uma release **em rascunho** para o
desenvolvedor decidir quando liberá-la.
