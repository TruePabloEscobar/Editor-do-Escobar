# O Editor

## Especificação técnica e diretrizes do projeto

**Documento:** especificação funcional e técnica  
**Versão:** 0.1.0  
**Status:** base para implementação do MVP  
**Plataforma inicial:** Windows 11 + DaVinci Resolve Studio 21.x  
**Idioma da interface:** Português do Brasil  
**Nome do produto:** Editor Do Escobar (EDE), atualizado por solicitação em 2026-10-19
**Nome técnico do repositório:** `o-editor`  
**Pacote Python:** `o_editor`

---

## 1. Visão do produto

O Editor é um assistente local de edição para DaVinci Resolve. Ele analisa a timeline ativa, transcreve a fala, identifica momentos relevantes e propõe zooms dinâmicos e textos curtos. Nenhuma alteração editorial deve ser aplicada sem revisão do usuário.

O produto não pretende substituir o editor humano. Seu papel é reduzir tarefas repetitivas e preparar uma primeira camada de dinamismo editorial que continue editável dentro do DaVinci Resolve.

### Princípios do produto

1. **Sugestão antes de aplicação:** analisar, mostrar e pedir aprovação.
2. **Não destruir a edição existente:** trabalhar em uma cópia da timeline.
3. **Edição reversível:** alterações identificáveis, editáveis e removíveis.
4. **Funcionamento local:** mídia, áudio e transcrição permanecem no computador.
5. **API verificada:** nunca presumir que um método existe no Resolve.
6. **Falha segura:** operações não suportadas devem ser recusadas ou ignoradas com relatório claro.
7. **Sem automação de interface como padrão:** mouse e teclado simulados não fazem parte do backend principal.
8. **Código desacoplado:** análise editorial não deve depender diretamente da API do Resolve.

---

## 2. Objetivo do MVP

O MVP deve permitir que o usuário:

1. Abra uma timeline no DaVinci Resolve.
2. Execute `Workspace > Scripts > O Editor`.
3. Analise a timeline ativa.
4. Exporte ou obtenha um áudio temporário correspondente à timeline.
5. Transcreva a fala com timestamps.
6. Identifique frases importantes.
7. Gere sugestões de zoom.
8. Gere sugestões de textos curtos.
9. Revise as sugestões em uma janela de aprovação.
10. Ajuste intensidade e frequência.
11. Duplique a timeline antes da aplicação.
12. Aplique apenas as sugestões aprovadas.
13. Coloque textos em uma track dedicada.
14. Gere um relatório de tudo o que foi aplicado, ignorado ou recusado.

---

## 3. Escopo funcional do MVP

### 3.1 Incluído

- Conexão com o projeto e a timeline ativos.
- Leitura de nome, frame rate, início, fim, tracks e itens da timeline.
- Exportação de áudio temporário da timeline.
- Transcrição local em português e inglês.
- Timestamps por segmento e, quando disponíveis, por palavra.
- Análise heurística de importância.
- Interface para futura análise semântica por modelo local ou remoto.
- Sugestões de:
  - `push_in`;
  - `push_and_return`;
  - `punch_in`;
  - texto de palavra-chave;
  - texto numérico;
  - texto de conclusão.
- Aprovação individual e em lote.
- Edição manual do texto antes da aplicação.
- Intensidade e frequência independentes para zooms e textos.
- Duplicação obrigatória da timeline.
- Track dedicada com nome configurável, padrão `OE - TEXTOS`.
- Identificação dos elementos criados por O Editor.
- Modo `dry-run`, sem alterações no projeto.
- Cache reutilizável de áudio, transcrição e análise.
- Logs técnicos e relatório legível pelo usuário.
- Tratamento explícito de clips não suportados.
- Configuração local em JSON.

### 3.2 Não incluído

- Remoção automática de silêncios.
- Jump cuts automáticos.
- B-roll automático.
- Edição multicâmera.
- Corte automático entre câmeras.
- Correção de cor.
- Mixagem.
- Sonoplastia.
- Publicação em redes sociais.
- Colaboração em nuvem.
- Aplicativo para macOS ou Linux no primeiro ciclo.
- Treinamento de modelos.
- Envio automático de mídia para serviços externos.
- Substituição de clips existentes.
- Alteração da timeline original.
- Suporte garantido a clips com Fusion pré-existente no primeiro MVP.
- Automação por coordenadas de mouse, OCR ou atalhos como backend principal.

---

## 4. Forma de execução

### 4.1 Experiência do usuário

O usuário executará:

```text
Workspace
└── Scripts
    └── O Editor
```

O item de menu será um launcher leve instalado na pasta de scripts do Resolve.

### 4.2 Launcher interno

O launcher:

- deve usar somente a biblioteca padrão disponível no ambiente de scripting do Resolve;
- conecta-se ao Resolve;
- valida projeto e timeline ativos;
- localiza o executável ou módulo principal de O Editor;
- abre o aplicativo externo;
- transmite contexto mínimo por arquivo temporário ou argumentos;
- não importa PySide6, faster-whisper, CUDA ou dependências pesadas dentro do processo do Resolve.

### 4.3 Aplicativo externo

O aplicativo externo será escrito em Python e usará PySide6.

Responsabilidades:

- interface;
- orquestração;
- comunicação com o Resolve;
- exportação e cache de áudio;
- transcrição;
- geração de sugestões;
- aprovação;
- aplicação;
- relatório.

A conexão com o Resolve deve ser encapsulada por um adaptador. Nenhum módulo de domínio pode importar `DaVinciResolveScript` diretamente.

---

## 5. Regra crítica: prova de capacidade da API

A API de scripting do Resolve possui diferenças entre versões e operações que não são expostas de forma uniforme. Portanto, o primeiro artefato executável do projeto será um **Resolve Capability Probe**.

### 5.1 O probe deve verificar

1. Conexão com o Resolve.
2. Leitura do projeto ativo.
3. Leitura da timeline ativa.
4. Leitura da versão do Resolve.
5. Acesso aos itens de vídeo e áudio.
6. Leitura de propriedades de clips.
7. Criação de marcador de teste.
8. Remoção do marcador de teste.
9. Adição de track de vídeo.
10. Renomeação de track.
11. Duplicação segura da timeline.
12. Alternativa de duplicação por exportação/importação, quando disponível.
13. Adição de uma Fusion Composition a um clip de teste.
14. Criação de nodes Fusion.
15. Criação de keyframes em um `Transform`.
16. Inserção de Fusion Title.
17. Posicionamento do título no frame desejado.
18. Definição da duração do título.
19. Inserção em track específica.
20. Alteração do conteúdo de `Text+`.
21. Exportação de áudio da timeline.
22. Leitura e escrita de markers.
23. Salvamento do projeto.

### 5.2 Resultado do probe

Gerar:

```text
docs/RESOLVE_CAPABILITY_REPORT.md
runtime/resolve_capabilities.json
```

Cada capacidade deve ter um destes estados:

```text
SUPPORTED
UNSUPPORTED
UNVERIFIED
FAILED
```

Cada resultado deve conter:

- versão do Resolve;
- sistema operacional;
- método efetivamente encontrado;
- retorno;
- exceção, quando houver;
- observações;
- impacto no MVP;
- fallback selecionado.

### 5.3 Regras para o Codex e para o código

- Não inventar métodos da API.
- Não copiar exemplos sem validar a assinatura.
- Consultar primeiro a documentação instalada em `Help > Documentation > Developer`.
- Permitir que o caminho da documentação local seja informado por configuração.
- Usar introspecção apenas como complemento, nunca como prova única.
- Uma operação `UNVERIFIED` não pode ser tratada como concluída.
- O aplicativo não pode dizer que aplicou uma edição sem verificar o resultado.
- Métodos não documentados devem ficar isolados em um adaptador marcado como experimental.
- Nenhuma alteração deve ser feita diretamente no banco de dados interno do Resolve.

---

## 6. Arquitetura

```text
DaVinci Resolve
    |
    | Workspace > Scripts > O Editor
    v
Launcher leve
    |
    v
Aplicativo PySide6
    |
    +--> Resolve Adapter
    |       +--> Capability Probe
    |       +--> Timeline Reader
    |       +--> Audio Exporter
    |       +--> Timeline Duplicator
    |       +--> Zoom Backend
    |       +--> Title Backend
    |
    +--> Transcription
    |       +--> FasterWhisperProvider
    |       +--> MockTranscriptionProvider
    |
    +--> Editorial Analysis
    |       +--> HeuristicAnalyzer
    |       +--> SemanticAnalyzer interface
    |
    +--> Review UI
    |
    +--> Application Planner
    |
    +--> Persistence
            +--> JSON
            +--> SQLite opcional após o MVP
```

### 6.1 Camadas

#### `domain`

Entidades e regras puras:

- timeline;
- transcript;
- suggestion;
- review decision;
- application plan;
- result report.

Não conhece Resolve, PySide6, FFmpeg ou Whisper.

#### `application`

Casos de uso:

- analyze active timeline;
- review suggestions;
- duplicate timeline;
- apply approved plan;
- generate report.

#### `infrastructure`

Integrações:

- Resolve;
- FFmpeg;
- faster-whisper;
- sistema de arquivos;
- configuração;
- logs.

#### `ui`

Janelas, models, delegates e controllers do PySide6.

---

## 7. Estrutura inicial do repositório

```text
o-editor/
├── AGENTS.md
├── README.md
├── CHANGELOG.md
├── LICENSE
├── pyproject.toml
├── .gitignore
├── .editorconfig
├── .env.example
├── config/
│   ├── defaults.json
│   └── styles.example.json
├── docs/
│   ├── O_EDITOR_PROJECT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── INSTALL_WINDOWS.md
│   ├── RESOLVE_API_NOTES.md
│   ├── RESOLVE_CAPABILITY_REPORT.md
│   └── TROUBLESHOOTING.md
├── launcher/
│   └── O Editor.py
├── scripts/
│   ├── install_windows.ps1
│   ├── uninstall_windows.ps1
│   ├── doctor.ps1
│   └── run_dev.ps1
├── src/
│   └── o_editor/
│       ├── __init__.py
│       ├── __main__.py
│       ├── bootstrap.py
│       ├── domain/
│       │   ├── models.py
│       │   ├── enums.py
│       │   ├── scoring.py
│       │   └── validation.py
│       ├── application/
│       │   ├── analyze_timeline.py
│       │   ├── build_plan.py
│       │   ├── apply_plan.py
│       │   └── generate_report.py
│       ├── infrastructure/
│       │   ├── resolve/
│       │   │   ├── adapter.py
│       │   │   ├── loader.py
│       │   │   ├── capabilities.py
│       │   │   ├── timeline_reader.py
│       │   │   ├── audio_exporter.py
│       │   │   ├── duplicator.py
│       │   │   ├── fusion_zoom_backend.py
│       │   │   ├── fusion_title_backend.py
│       │   │   ├── alpha_title_backend.py
│       │   │   └── mock_adapter.py
│       │   ├── transcription/
│       │   │   ├── base.py
│       │   │   ├── faster_whisper.py
│       │   │   └── mock.py
│       │   ├── analysis/
│       │   │   ├── heuristic.py
│       │   │   ├── semantic_base.py
│       │   │   └── mock_semantic.py
│       │   ├── ffmpeg/
│       │   │   └── runner.py
│       │   ├── config.py
│       │   ├── cache.py
│       │   └── logging.py
│       └── ui/
│           ├── main_window.py
│           ├── review_window.py
│           ├── settings_window.py
│           ├── capability_dialog.py
│           ├── models/
│           └── controllers/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── golden/
└── runtime/
    ├── cache/
    ├── logs/
    └── reports/
```

`runtime/` deve ser ignorado pelo Git, exceto arquivos `.gitkeep` necessários.

---

## 8. Fluxo completo

### 8.1 Inicialização

1. Launcher valida se o Resolve está aberto.
2. Valida projeto ativo.
3. Valida timeline ativa.
4. Abre O Editor.
5. O aplicativo reconecta ao Resolve.
6. Executa um diagnóstico rápido.
7. Exibe timeline, duração, frame rate e status.

### 8.2 Análise

1. Ler snapshot da timeline.
2. Criar identificador da análise.
3. Calcular fingerprint da timeline.
4. Verificar cache.
5. Exportar áudio temporário quando necessário.
6. Transcrever.
7. Normalizar timestamps em frames.
8. Segmentar frases.
9. Calcular importância.
10. Gerar sugestões.
11. Validar conflitos.
12. Mostrar revisão.

### 8.3 Aprovação

O usuário pode:

- ativar ou desativar uma sugestão;
- visualizar o timecode;
- levar o playhead ao ponto;
- alterar o texto;
- alterar tipo de zoom;
- alterar intensidade;
- alterar duração;
- alterar entrada e saída;
- aprovar todos;
- rejeitar todos;
- filtrar por tipo;
- aplicar somente zooms;
- aplicar somente textos.

### 8.4 Aplicação

1. Revalidar que a timeline não mudou desde a análise.
2. Caso tenha mudado, bloquear aplicação e pedir nova análise.
3. Gerar plano imutável.
4. Duplicar a timeline.
5. Confirmar que a cópia foi criada.
6. Alterar o projeto ativo para a cópia.
7. Criar ou localizar track `OE - TEXTOS`.
8. Aplicar zooms aprovados.
9. Aplicar textos aprovados.
10. Verificar cada resultado.
11. Adicionar markers de auditoria, quando configurado.
12. Salvar o projeto.
13. Gerar relatório.
14. Exibir resumo.

---

## 9. Snapshot e fingerprint da timeline

A análise deve ser vinculada a um snapshot.

Campos mínimos:

```json
{
  "project_name": "Projeto",
  "timeline_name": "Entrevista",
  "timeline_id": "quando disponível",
  "fps": 29.97,
  "drop_frame": true,
  "start_frame": 107892,
  "end_frame": 180000,
  "video_track_count": 3,
  "audio_track_count": 4,
  "items": []
}
```

O fingerprint deve considerar:

- nome;
- frame rate;
- início e fim;
- quantidade de tracks;
- itens;
- posição;
- duração;
- fonte;
- estado habilitado;
- propriedades relevantes.

A aplicação deve ser recusada quando o fingerprint atual for diferente do snapshot analisado, salvo quando uma política explícita de tolerância for implementada.

---

## 10. Áudio temporário

### 10.1 Requisitos

- WAV PCM.
- Mono ou estéreo.
- 16 kHz ou 48 kHz.
- Sem normalização destrutiva.
- Deve refletir a timeline, não apenas os arquivos-fonte.
- Respeitar tracks habilitadas.
- Ter correspondência temporal conhecida com o frame inicial da timeline.

### 10.2 Backend preferencial

Usar a API de render do Resolve com preset temporário criado e restaurado de forma segura.

### 10.3 Fallback

Quando a exportação de áudio pela API não estiver disponível:

- informar a limitação;
- permitir seleção manual de um WAV exportado pelo usuário;
- validar duração e offset;
- não usar automação de interface silenciosamente.

### 10.4 Cache

Chave sugerida:

```text
{project}_{timeline}_{fingerprint}_{audio_settings_hash}
```

---

## 11. Transcrição

### 11.1 Provider inicial

`faster-whisper`, executado no aplicativo externo.

### 11.2 Requisitos

- seleção de modelo;
- escolha de dispositivo;
- CUDA quando disponível;
- fallback para CPU;
- idioma automático ou forçado;
- timestamps por palavra quando suportados;
- progresso;
- cancelamento;
- cache;
- tratamento de ausência do modelo;
- não bloquear a interface.

### 11.3 Modelos sugeridos

Configuração, não regra rígida:

```json
{
  "transcription": {
    "provider": "faster-whisper",
    "model": "large-v3-turbo",
    "device": "auto",
    "compute_type": "auto",
    "language": "pt"
  }
}
```

O programa deve permitir modelos menores.

### 11.4 Saída normalizada

```json
{
  "language": "pt",
  "segments": [
    {
      "id": "seg_0001",
      "start_seconds": 12.42,
      "end_seconds": 16.08,
      "start_frame": 373,
      "end_frame": 482,
      "text": "Esse foi o principal problema.",
      "words": []
    }
  ]
}
```

Toda decisão de edição deve usar frames internamente. Segundos são apenas intercâmbio e exibição.

---

## 12. Analisador editorial

### 12.1 Estratégia do MVP

O MVP terá um analisador heurístico determinístico. Um analisador semântico será uma interface opcional, não um requisito para o primeiro fluxo funcional.

### 12.2 Sinais de importância

- números e percentuais;
- datas;
- nomes próprios;
- perguntas;
- frases conclusivas;
- contrastes;
- mudança de tópico;
- repetição lexical;
- pausa anterior;
- duração da frase;
- energia relativa do áudio, quando implementada;
- palavras ou expressões configuráveis;
- estruturas como:
  - “o mais importante”;
  - “o problema”;
  - “por isso”;
  - “em resumo”;
  - “a conclusão”;
  - “mas”;
  - “porém”;
  - “entretanto”.

### 12.3 Score

Faixa:

```text
0.00 a 1.00
```

Exemplo conceitual:

```text
importance =
    semantic_weight
  + numeric_weight
  + conclusion_weight
  + pause_weight
  + audio_emphasis_weight
  - repetition_penalty
  - conflict_penalty
```

O cálculo deve ser testável e configurável.

---

## 13. Sugestões de zoom

### 13.1 Tipos

#### `push_in`

Aproxima suavemente e permanece.

#### `push_and_return`

Aproxima, mantém e retorna.

#### `punch_in`

Mudança rápida de enquadramento.

### 13.2 Intensidade

Valores padrão:

| Nível | Zoom mínimo | Zoom máximo |
|---|---:|---:|
| muito suave | 1.03 | 1.05 |
| suave | 1.05 | 1.08 |
| médio | 1.08 | 1.12 |
| forte | 1.12 | 1.15 |

O limite padrão do MVP será `1.15`.

### 13.3 Frequência

| Nível | Máximo aproximado | Intervalo mínimo |
|---|---:|---:|
| baixa | 1 por minuto | 20 s |
| média | 3 por minuto | 8 s |
| alta | 6 por minuto | 4 s |

Os valores são parâmetros configuráveis, não promessas rígidas.

### 13.4 Regras de bloqueio

Não sugerir quando:

- clip é curto demais;
- sugestão cruza o fim do clip;
- há transição próxima;
- já existe outra sugestão incompatível;
- clip é multicam não suportado;
- clip possui Fusion que o backend não consegue preservar;
- propriedades necessárias não podem ser lidas;
- a margem de imagem é insuficiente, quando essa análise existir.

### 13.5 Aplicação técnica preferencial

Backend preferencial:

1. localizar o `TimelineItem`;
2. calcular frames locais do clip;
3. validar que não existe composição Fusion incompatível;
4. adicionar ou criar uma composição Fusion;
5. criar ou reutilizar um node `Transform` identificado como `OE_DynamicZoom`;
6. ligar `MediaIn -> Transform -> MediaOut`;
7. criar animação no parâmetro `Size`;
8. criar animação em `Center`, quando necessário;
9. verificar os keyframes;
10. marcar o item como processado.

O backend só pode ser habilitado se o capability probe confirmar todas as operações necessárias.

### 13.6 Fallback de zoom

Se não houver backend automático seguro:

- gerar markers e plano de edição;
- não afirmar que o zoom foi aplicado;
- manter a sugestão como `UNAPPLIED`;
- exibir o motivo.

Automação de mouse e teclado só poderá existir futuramente como módulo experimental, desabilitado por padrão e explicitamente autorizado pelo usuário.

---

## 14. Sugestões de texto

### 14.1 Categorias

- palavra-chave;
- número;
- data;
- nome;
- conclusão;
- contraste;
- chamada curta.

### 14.2 Regras

- de 2 a 6 palavras por padrão;
- não repetir a frase inteira;
- não inventar fatos;
- preservar números;
- preservar nomes;
- evitar texto durante cortes muito rápidos;
- evitar sobreposição com títulos existentes;
- intervalo mínimo padrão de 10 segundos;
- duração padrão entre 1,5 e 3 segundos.

### 14.3 Track

Nome padrão:

```text
OE - TEXTOS
```

A track deve:

- ser criada acima do conteúdo existente;
- ser reutilizada quando já existir;
- ser identificada sem depender apenas do índice;
- não substituir uma track do usuário;
- permanecer desbloqueada após aplicação, salvo configuração contrária.

### 14.4 Backend preferencial

Fusion Title customizado, com pelo menos:

- `Text`;
- `Font`;
- `Size`;
- `PositionX`;
- `PositionY`;
- `MainColor`;
- `AccentColor`;
- `BackgroundEnabled`;
- `EntryDuration`;
- `ExitDuration`;
- `Style`.

### 14.5 Fallback de texto

`AlphaTitleBackend`:

- renderiza um overlay com alpha;
- importa o arquivo;
- coloca no frame e track planejados;
- informa que o texto não será editável como `Text+`;
- só é usado com autorização do usuário.

O backend Fusion é o objetivo do MVP. O fallback existe para preservar utilidade quando a versão da API impedir posicionamento ou duração confiáveis.

---

## 15. Duplicação da timeline

A timeline original nunca deve ser alterada.

Nome padrão:

```text
{timeline_original}_OE_EDIT_001
```

### Estratégias

1. método documentado de duplicação, quando disponível;
2. exportação e reimportação de timeline em formato que preserve a edição;
3. outra estratégia documentada e validada pelo capability probe.

Se nenhuma estratégia preservar a timeline com segurança:

- bloquear `Aplicar`;
- permitir apenas `dry-run`;
- explicar o motivo;
- não reconstruir a timeline a partir dos arquivos-fonte.

---

## 16. Interface

### 16.1 Tela principal

Exibir:

- projeto;
- timeline;
- duração;
- frame rate;
- status da conexão;
- status do FFmpeg;
- status do Whisper;
- status das capacidades do Resolve;
- botão `Analisar timeline`;
- botão `Abrir diagnóstico`;
- configurações de intensidade e frequência;
- progresso;
- cancelamento.

### 16.2 Tela de revisão

Colunas:

- aprovado;
- timecode;
- tipo;
- conteúdo;
- intensidade;
- duração;
- confiança;
- motivo;
- status de conflito.

Ações:

- visualizar no Resolve;
- editar;
- ativar;
- desativar;
- aplicar filtro;
- aprovar todos;
- rejeitar todos;
- aplicar aprovados;
- exportar plano JSON.

### 16.3 Estados

```text
IDLE
CONNECTING
READY
ANALYZING
TRANSCRIBING
GENERATING_SUGGESTIONS
REVIEWING
VALIDATING
APPLYING
COMPLETED
FAILED
CANCELLED
```

A interface não pode congelar. Processamento pesado deve ocorrer fora da thread principal.

---

## 17. Contrato de sugestão

```json
{
  "id": "sug_01JXYZ",
  "kind": "zoom",
  "subtype": "push_and_return",
  "timeline_start_frame": 4320,
  "timeline_end_frame": 4470,
  "clip_id": "clip_001",
  "clip_local_start_frame": 120,
  "clip_local_end_frame": 270,
  "confidence": 0.86,
  "importance": 0.91,
  "reason_codes": [
    "CONCLUSION",
    "PAUSE_BEFORE"
  ],
  "parameters": {
    "zoom_start": 1.0,
    "zoom_peak": 1.09,
    "center_x": 0.5,
    "center_y": 0.5,
    "attack_frames": 10,
    "hold_frames": 80,
    "release_frames": 12
  },
  "approved": true,
  "edited_by_user": false,
  "status": "PENDING"
}
```

Texto:

```json
{
  "id": "sug_01JABC",
  "kind": "text",
  "subtype": "number",
  "timeline_start_frame": 7800,
  "timeline_end_frame": 7860,
  "confidence": 0.94,
  "source_segment_ids": ["seg_0042"],
  "text": "50% menos tempo",
  "parameters": {
    "style": "keyword",
    "position": "lower_center",
    "entry_frames": 8,
    "exit_frames": 8
  },
  "approved": true,
  "status": "PENDING"
}
```

---

## 18. Plano de aplicação

O plano aprovado deve ser salvo antes da alteração:

```text
runtime/reports/{analysis_id}/application_plan.json
```

Estados por operação:

```text
PENDING
APPLIED
SKIPPED
UNSUPPORTED
FAILED
ROLLED_BACK
```

O plano deve ser imutável durante a aplicação. Alterações na UI geram uma nova revisão do plano.

---

## 19. Segurança e integridade

- Nunca alterar a timeline original.
- Nunca excluir mídia.
- Nunca apagar tracks do usuário.
- Nunca editar banco de dados interno.
- Nunca enviar mídia à internet sem configuração explícita.
- Nunca armazenar tokens no repositório.
- Nunca registrar conteúdo integral da transcrição em logs técnicos por padrão.
- Não sobrescrever arquivos de cache sem verificação.
- Criar backup do plano e relatório.
- Interromper quando a timeline mudar.
- Verificar retorno de cada chamada da API.
- Usar timeout em operações externas.
- Permitir cancelamento seguro.
- Salvar o projeto apenas após validações.
- Registrar a versão de O Editor e do Resolve.

---

## 20. Configuração padrão

```json
{
  "app": {
    "language": "pt-BR",
    "theme": "system",
    "log_level": "INFO"
  },
  "resolve": {
    "target_major_version": 21,
    "require_studio": true,
    "text_track_name": "OE - TEXTOS",
    "duplicate_suffix": "_OE_EDIT",
    "add_audit_markers": true
  },
  "transcription": {
    "provider": "faster-whisper",
    "model": "large-v3-turbo",
    "device": "auto",
    "compute_type": "auto",
    "language": "pt",
    "word_timestamps": true
  },
  "zoom": {
    "enabled": true,
    "intensity": "medium",
    "frequency": "medium",
    "max_zoom": 1.15,
    "minimum_gap_seconds": 8,
    "maximum_per_minute": 3
  },
  "text": {
    "enabled": true,
    "frequency": "low",
    "minimum_gap_seconds": 10,
    "maximum_per_minute": 2,
    "minimum_words": 2,
    "maximum_words": 6,
    "minimum_duration_seconds": 1.5,
    "maximum_duration_seconds": 3.0
  },
  "safety": {
    "dry_run_default": true,
    "require_timeline_duplicate": true,
    "skip_existing_fusion_comps": true,
    "allow_gui_automation": false,
    "allow_alpha_title_fallback": false
  }
}
```

---

## 21. Logs e relatórios

### Logs técnicos

```text
runtime/logs/o-editor.log
```

Devem conter:

- timestamp;
- nível;
- módulo;
- analysis ID;
- operação;
- resultado;
- exceção sanitizada.

### Relatório de aplicação

```text
runtime/reports/{analysis_id}/APPLICATION_REPORT.md
```

Conteúdo:

- projeto e timeline;
- timeline duplicada;
- versão do Resolve;
- quantidade de sugestões;
- aprovadas;
- aplicadas;
- ignoradas;
- falhas;
- motivos;
- caminhos de arquivos;
- duração das etapas;
- capacidades usadas.

---

## 22. Testes

### 22.1 Unitários

- conversão de segundos para frames;
- timecode non-drop;
- timecode drop-frame;
- scoring;
- controle de frequência;
- detecção de conflitos;
- validação de contratos;
- geração de nomes;
- fingerprint;
- cache;
- serialização.

### 22.2 Integração sem Resolve

Usar `MockResolveAdapter` para:

- análise completa;
- duplicação simulada;
- aplicação simulada;
- falhas;
- rollback lógico;
- geração de relatório.

### 22.3 Integração com Resolve

Testes manuais assistidos:

1. timeline curta com um clip;
2. timeline com vários cortes;
3. timeline 23.976;
4. timeline 29.97 DF;
5. timeline 30;
6. track de texto existente;
7. clip com Fusion;
8. clip multicam;
9. timeline modificada após análise;
10. aplicação cancelada.

### 22.4 Golden tests

Fixtures de transcrição devem produzir sugestões estáveis.

---

## 23. Qualidade de código

- Python com type hints.
- `ruff` para lint e formatação.
- `mypy` para checagem estática gradual.
- `pytest`.
- Cobertura mínima inicial de 75% no domínio e application layer.
- Funções pequenas.
- Dependências invertidas.
- Sem `except Exception: pass`.
- Erros de domínio próprios.
- Mensagens ao usuário em português.
- Identificadores e documentação técnica do código em inglês.
- Nenhum método da API do Resolve chamado fora do adaptador.
- Nenhum caminho absoluto fixo.
- Nenhum segredo.
- Nenhuma dependência desnecessária.

---

## 24. Git

O projeto deve usar Git desde o primeiro arquivo.

### Branch inicial

```text
main
```

### Commits sugeridos

```text
chore: initialize project structure
feat: add resolve capability probe
feat: add timeline snapshot domain
feat: add transcription provider
feat: add heuristic suggestion engine
feat: add review interface
feat: add safe application planner
feat: add fusion zoom backend
feat: add title application backend
docs: add Windows installation guide
```

Não criar um único commit gigantesco.

---

## 25. Fases de implementação

### Fase 0 — Descoberta técnica

Entregas:

- estrutura do repositório;
- carregador da API;
- capability probe;
- relatório;
- mock adapter;
- documentação das limitações.

Gate:

- não iniciar aplicação automática real antes de conhecer as capacidades.

### Fase 1 — Fluxo offline

Entregas:

- interface;
- importação manual de WAV;
- transcrição;
- análise;
- revisão;
- exportação do plano JSON;
- testes.

Gate:

- analisar e revisar sem modificar o Resolve.

### Fase 2 — Integração de leitura

Entregas:

- timeline ativa;
- snapshot;
- fingerprint;
- áudio exportado;
- playhead navigation;
- cache.

### Fase 3 — Aplicação segura

Entregas:

- duplicação;
- track;
- zoom backend;
- title backend;
- relatório;
- verificação.

### Fase 4 — Instalador

Entregas:

- PowerShell;
- launcher;
- atalhos;
- doctor;
- documentação.

---

## 26. Critérios de aceitação do MVP

O MVP só pode ser considerado concluído quando:

1. `Workspace > Scripts > O Editor` abre o aplicativo.
2. O aplicativo identifica projeto e timeline.
3. O diagnóstico informa capacidades reais.
4. Uma timeline curta pode ser transcrita localmente.
5. Sugestões são geradas e exibidas.
6. O usuário pode editar e aprovar sugestões.
7. A timeline original permanece intocada.
8. A cópia é criada e validada.
9. Pelo menos um backend de zoom dinâmico funciona e é verificado.
10. O texto é colocado em track dedicada.
11. O texto fica editável por Fusion no backend principal.
12. Operações incompatíveis são ignoradas com justificativa.
13. O projeto gera relatório.
14. O fluxo completo funciona em `dry-run`.
15. Os testes passam.
16. A instalação está documentada.
17. Não existem métodos fictícios da API.
18. O programa não declara sucesso sem confirmar o resultado no Resolve.

Caso os itens 9, 10 ou 11 sejam impedidos pela API da versão instalada, o resultado deve ser classificado como protótipo técnico, não como MVP concluído.

---

## 27. Decisões arquiteturais iniciais

### ADR-001 — Aplicativo externo

O Editor será um aplicativo externo iniciado por um launcher do Resolve. Isso isola dependências pesadas e reduz risco de travamento do processo principal.

### ADR-002 — Python

Python será usado no launcher e no aplicativo. O launcher terá dependências mínimas; o aplicativo externo usará ambiente virtual próprio.

### ADR-003 — PySide6

A interface será construída com PySide6.

### ADR-004 — Transcrição local

O primeiro provider será faster-whisper. Nenhuma API paga será obrigatória.

### ADR-005 — Frames como unidade interna

Toda decisão editorial será armazenada em frames. Timecode e segundos serão representações derivadas.

### ADR-006 — Capability gate

A API real da instalação decide quais backends podem ser habilitados.

### ADR-007 — Sem GUI automation por padrão

Automação de mouse e teclado não será usada para mascarar limitações da API.

### ADR-008 — Timeline original imutável

Aplicação só ocorre em cópia verificada.

---

## 28. Pontos que permanecem configuráveis

- versão mínima exata do Resolve 21;
- modelo Whisper padrão;
- estilo visual dos títulos;
- posição padrão;
- fonte;
- cores;
- duração;
- limite de zoom;
- tratamento de clips com Fusion;
- uso futuro de modelo semântico;
- formato de empacotamento do instalador.

Esses pontos não impedem a criação da arquitetura e do capability probe.

---

## 29. Definição de pronto por tarefa

Uma tarefa só está pronta quando:

- código implementado;
- type hints adicionados;
- erros tratados;
- testes criados;
- documentação atualizada;
- comportamento verificado;
- logs adequados;
- nenhum método fictício;
- commit específico realizado;
- limitações registradas.

---

## 30. Referências técnicas que devem ser consultadas durante o desenvolvimento

Prioridade:

1. documentação instalada com a mesma versão do DaVinci Resolve;
2. `Help > Documentation > Developer`;
3. `Developer/Scripting/README.txt`;
4. exemplos instalados pela Blackmagic Design;
5. Fusion Scripting Guide;
6. notas oficiais da versão instalada;
7. fórum oficial da Blackmagic apenas para investigar comportamentos e bugs, nunca como substituto da validação local.

A documentação da instalação real é a fonte operacional de verdade para as assinaturas da API.


## Evolução autorizada — distribuição 0.2.0 (2026-10-19)

Download de modelo permitido somente por clique explícito no botão das configurações,
em subprocesso cancelável, de catálogo CTranslate2. A inferência continua local.
Sobre contém tutorial e créditos. Distribuição é plugin via script Windows com
Python externo, não OFX. Detalhes: docs/DISTRIBUICAO.md. O restante dos gates,
original imutável e validação de capabilities permanece obrigatório.
