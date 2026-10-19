# Transcrição por faixa, TXT editável e Rough Cut

Fluxo completo:

```text
Resolve: Workspace > Scripts > O EDITOR   (captura clipes de todas as tracks)
O Editor: aba "Transcrição e Rough Cut"
  1. marcar as faixas de voz (lista "Faixas usadas para voz")
  2. Transcrever faixas selecionadas
  3. Exportar transcrição  -> Podcast_Pablo.txt ... Podcast_Completo.txt
  4. editar o TXT (Bloco de Notas, VS Code, ChatGPT, Claude...)
  5. Importar transcrição editada  -> prévia das diferenças -> confirmar
  6. ajustar a limpeza de silêncios e a regra de cada faixa
  7. Gerar prévia  ->  Aplicar Rough Cut (confirmação)
Resolve: Workspace > Scripts > O EDITOR
  -> nova timeline "<original>_OE_ROUGHCUT_001"; a original não é alterada
```

## 1. Leitura da timeline

`O EDITOR` (Lua, dentro do Resolve) agora envia o contexto schema 3 com o
objeto `layout`. Para cada track de vídeo, áudio e legenda ele grava o nome, o subtipo
(mono/estéreo) e os estados habilitada/bloqueada. Para cada clipe grava:

- `GetUniqueId`, `GetName`, `GetType`, `GetStart`/`GetEnd` (inteiro e subframe);
- `GetSourceStartFrame`/`GetSourceEndFrame`, `GetSourceStartTime`/`GetSourceEndTime`;
- `GetLeftOffset`/`GetRightOffset`, `GetClipEnabled`, `GetSpeed`, `GetLinkedItems`;
- `GetMediaPoolItem` -> `GetUniqueId`, `GetClipProperty("File Path")`, `GetClipProperty("FPS")`;
- áudio: `GetSourceAudioChannelMapping` (21.1); vídeo: `GetFusionCompCount`.

Todas as chamadas são somente leitura e protegidas por `pcall`. Um método ausente vira
`null` e não interrompe a captura. O participante é o **nome da track**; o arquivo de
origem é preservado separadamente.

## 2. Áudio isolado de cada faixa

A API não permite renderizar uma track isolada (`SetRenderSettings` não tem chave de
track), e alterar mute/solo está proibido. Por isso cada faixa é **reconstruída a partir
das mídias originais** (`infrastructure/audio/track_renderer.py`):

- cada clipe é decodificado com FFmpeg a partir do ponto de entrada na mídia e gravado na
  posição exata da timeline (16 kHz mono, alinhado por amostra; a amostra 0 é o início
  da timeline), com silêncio digital nas lacunas;
- o ponto de entrada só é aceito quando duas leituras independentes concordam
  (`GetLeftOffset`, `GetSourceStartFrame`/FPS da mídia, `GetSourceStartTime`) e o trecho
  cabe na duração medida pelo FFprobe. Caso contrário, a faixa é recusada com mensagem;
- canais: o mapeamento do Resolve (`channel_idx`) tem prioridade, o que funciona com
  arquivos poly-WAV de gravadores multipista; sem mapeamento vale a seleção
  Ambos/Esquerdo/Direito/Mono da interface;
- clipes desabilitados viram silêncio; clipes com velocidade diferente de 100% são
  recusados.

## 3. Transcrição

`FasterWhisperTrackTranscriber` carrega o modelo uma vez para todas as faixas e usa
CUDA quando disponível, com `vad_filter`, `condition_on_previous_text=False`, limiares de
`no_speech` e `log_prob` e timestamps por palavra. Proteções extras:

- trechos sem sinal na própria faixa (menos de 15% de atividade) são descartados como
  alucinação sobre silêncio, e a quantidade descartada aparece nos avisos;
- **sobreposição**: trechos que se sobrepõem a fala de outra faixa recebem a marcação
  `SOBREPOSTO` e nenhum tempo é deslocado;
- **vazamento**: texto semelhante, tempo coincidente e nível pelo menos 6 dB menor que o
  da outra faixa recebe a marcação `VAZAMENTO`. Esse trecho não protege intervalos e é
  omitido do TXT consolidado. Sem medida de nível nada é marcado (comportamento conservador);
- IDs `SEG_0001...` são atribuídos em ordem cronológica global. A sessão é gravada em
  `%APPDATA%\O Editor\sessions\<id>\session.json`, com histórico por revisão;
- `Repetir transcrição` ignora o cache e cria uma nova revisão. Estados e correções de
  trechos idênticos são preservados. TXT de revisões anteriores passa a ser bloqueado.

CUDA: o relatório anterior registrou a ausência de `cublas64_12.dll`. Instale os
runtimes no ambiente do projeto (sem download de modelos):

```powershell
.\.venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
```

O Editor registra automaticamente `site-packages\nvidia\*\bin` antes de carregar o modelo.

## 4. Formato TXT

```text
@OE_TRANSCRIPT 1
@SESSION 3b6814a6733c40c1
@REVISION 1
@PROJECT Podcast
@TIMELINE Episodio 1
@TIMELINE_ID 597ad560-...
@FPS 23.976
@TIMELINE_START 01:00:00:00
@SCOPE ALL                       (ou A1, A2... nos arquivos individuais)
@PARTICIPANTS A1=Pablo; A2=Jessica; A3=Mileni; A4=Renne
@SEGMENTS 128
@CHECKSUM 9f2c...
@BEGIN

[SEG_0001] [A1: Pablo] [00:00:12.300 --> 00:00:17.500] [KEEP]
Então, hoje vamos conversar sobre inteligência artificial.

[SEG_0003] [A1: Pablo] [00:00:21.400 --> 00:00:25.900] [CUT] [FLAGS: SOBREPOSTO]
Não, espera, deixa eu começar essa parte novamente.

@END 128
```

- Os tempos são posições na timeline a partir do início dela; a TC real aparece na
  interface (coluna TC).
- O cabeçalho comentado (`#`) traz instruções para pessoas e IAs.
- O leitor tolera blocos de código, comentários da IA antes e depois, `→` no lugar de
  `-->`, negrito Markdown, `keep/cut` em minúsculas e sinônimos (MANTER/CORTAR/REMOVER),
  além de UTF-8, UTF-8 com BOM e Windows-1252.
- A referência para cortar é sempre o **ID + intervalo original da sessão**. Corrigir o
  texto não altera o áudio, e mudar o nome do participante gera aviso sem desvincular a track.

### Bloqueios na importação (nada é alterado)

`@OE_TRANSCRIPT`/`@SESSION`/`@REVISION`/`@CHECKSUM`/`@SCOPE` alterados; `@BEGIN` ou
`@END` ausentes (arquivo truncado); contagens adulteradas; ID duplicado, desconhecido ou
de outro escopo; faixa trocada; tempo alterado (tolerância de 1 frame); estado inválido;
cabeçalho de trecho malformado; arquivo vazio ou com mais da metade dos trechos ausente.

### Trechos ausentes

São candidatos à remoção. A importação registra os IDs em `pending_missing` e o rough
cut fica bloqueado até o usuário escolher **Remover ausentes** ou **Manter ausentes**.

## 5. Plano de cortes (global)

`domain/rough_cut.py` decide uma única vez, na timeline global:

1. **Fala protegida** = trechos `KEEP` sem `VAZAMENTO`, com guarda de 100 ms antes e
   150 ms depois.
2. **Cortes de texto** = trechos `CUT` menos a fala protegida. Se outro participante está
   falando, essa parte permanece e um aviso de remoção parcial é exibido.
3. **Silêncio** = lacunas sem fala protegida e sem atividade de sinal em nenhuma faixa
   transcrita (risos e reações não transcritos ficam protegidos quando a opção está
   marcada). Remove o início, o fim e as pausas maiores que o mínimo, preservando as
   margens antes e depois da fala.

| Intensidade | Silêncio mínimo | Margem antes | Margem depois |
|---|---:|---:|---:|
| Suave | 2000 ms | 400 ms | 500 ms |
| Média | 1200 ms | 250 ms | 350 ms |
| Forte | 700 ms | 150 ms | 200 ms |

Cortes menores que 120 ms são descartados. Os intervalos mantidos são aplicados de forma
idêntica a **todas** as tracks com regra "Cortar junto" (vídeo, voz, música, efeitos),
o que garante a sincronia. "Omitir" deixa a track vazia na nova timeline. Legendas não
são reconstruídas. Clipes de áudio não reconstruíveis (sem mídia, velocidade alterada)
**bloqueiam** o plano; clipes de vídeo desse tipo geram aviso.

## 6. Aplicação no Resolve

`O EDITOR` lê `%APPDATA%\O Editor\plans\rough-cut-pending.json`:

1. valida schema, idade (máximo de 12 h), projeto, timeline, ID, FPS e limites;
2. compara **cada clipe** da timeline ativa com o plano (posição, track, quantidade). Se
   algo divergir, bloqueia sem mutações;
3. no modo VALIDATE ("Validar no Resolve") termina aqui;
4. no modo APPLY (exige `confirmed_by_user`): `DuplicateTimeline` com nome livre, ativa a
   cópia e só então limpa os itens **da cópia**. O ID da timeline ativa é conferido antes
   de cada mutação;
5. `AppendToTimeline` por operação. A primeira operação **calibra** as convenções não
   documentadas (`endFrame` inclusivo ou exclusivo; `recordFrame` absoluto ou relativo).
   Cada item é conferido por readback de posição, duração e frame de origem. Itens extras
   criados pelo Resolve em outras tracks (mídia multipista) são removidos da cópia;
6. copia propriedades de transformação e áudio, mapeamento de canais, estado e cor do
   clipe; revincula vídeo e áudio que eram vinculados; reposiciona marcadores;
7. confere a contagem final e verifica de novo a timeline original;
8. em caso de falha, a cópia é renomeada `..._FALHOU` para inspeção. A original nunca é
   alterada.

Não são copiados: grades de cor, composições Fusion, transições, keyframes e efeitos
Fairlight de track.

## 7. Testes

Automatizados (`pytest`):

| Teste | Arquivo |
|---|---|
| A — 4 faixas → 4 transcrições | `tests/integration/test_track_transcription.py` |
| B — fala no minuto 15 com TC real | idem (`test_b_...`) |
| C — export/import sem alteração | `tests/unit/test_transcript_document.py` |
| D — CUT → intervalo exato | idem e `tests/unit/test_rough_cut_plan.py` |
| E — silêncio removível | `tests/unit/test_rough_cut_plan.py` |
| F — fala simultânea | idem |
| G — sincronização | idem e `tests/integration/test_lua_rough_cut.py` |
| H — original intacta | `tests/integration/test_lua_rough_cut.py` |

Os testes de Lua executam o código real de `launcher/internal_common.lua` em Lua 5.1
contra um Resolve simulado (`tests/lua/fake_resolve.lua`). Eles provam a lógica, não o
comportamento da API real.

### Teste manual obrigatório no Resolve (ainda não executado)

1. Reinstale os scripts (`O Editor - Instalar no DaVinci.cmd`) e reinicie o Resolve.
2. Abra uma timeline **de teste** com 2 a 4 microfones e uma câmera.
3. `O EDITOR` → confira na aba que todas as faixas e clipes aparecem.
4. Transcreva, exporte, marque um trecho como CUT, importe e gere a prévia.
5. "Validar no Resolve" → execute `O EDITOR` → resultado SUCCESS sem
   alterações.
6. "Aplicar Rough Cut" → execute o script novamente → confira a nova timeline (sincronia
   entre câmera e microfones, canais e cortes) e confira que a original está igual.
7. Envie `%APPDATA%\O Editor\logs\internal-roughcut.log` e o relatório em
   `%APPDATA%\O Editor\reports` se algo falhar.


O menu único abre a interface atual. Depois de confirmar Validar/Aplicar no app,
execute O EDITOR em até cinco minutos: ele consome essa solicitação uma única vez.
Um plano salvo sozinho não dispara alterações ao abrir. Reinicie o Resolve depois
da atualização para limpar os itens de menu em cache.

## Verificação de 19/10/2026

Resolve Studio 21.1.1.10: probe completo na mídia OBS do relato criou
`OE_TEST_ROUGHCUT_VALIDATION`, 45 itens verificados, 36 mapeamentos de áudio
conferidos sem divergências e original intacta. Evidência local:
`runtime/probe-roughcut-fixed.json` e `runtime/roughcut-channel-readback.json`.
Esta rodada substitui a pendência do teste real para esse cenário; não comprova
outros formatos, escuta humana ou preservação de efeitos não suportados.

A API pode inserir pistas de áudio que não aparecem no retorno de AppendToTimeline.
A engine confere a timeline copiada por IDs antes/depois e desvincula/remove os
adicionais. O getter do frame de origem pode truncar um frame em 23.976: o aceite
exige duas leituras independentes concordantes com o pedido; divergências bloqueiam.

Após Validar/Aplicar, os botões ficam aguardando uma resposta por até cinco minutos.
Execute O EDITOR uma vez no menu do Resolve. O resultado aparece na prévia, também
quando é recebido diretamente pelo arquivo persistido, sem o launcher auxiliar.
Casos e testes: BUG-0003, BUG-0004 e BUG-0005 em `qa/regressoes/REGISTRO.md`.
