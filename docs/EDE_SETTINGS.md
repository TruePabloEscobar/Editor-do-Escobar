# Editor Do Escobar — modelo local e processamento

Abra a engrenagem à direita da barra de etapas e escolha **Carregar modelo…**.
Modelo e GPU ficam na aba **Transcrição**; **Diagnóstico** reúne conexão,
capacidades, relatórios e logs. Fechar/reabrir conserva os relatórios.
A edição das configurações permanece bloqueada durante operações em andamento.
Selecione uma pasta local Whisper convertida para faster-whisper/CTranslate2,
com `model.bin`, `config.json` e `tokenizer.json`. Não é um importador de modelos
arbitrários: arquivos PyTorch `.pt`, GGUF ou outros motores exigem conversão ou
um adaptador próprio. Nenhum modelo é baixado automaticamente.

**Dispositivo:** Automático seleciona CUDA disponível e permite o fallback já
existente para CPU; CPU força processamento local sem GPU; GPU N força o índice
CUDA selecionado. Falha de uma GPU explícita é informada. Em sistemas com vários
adaptadores a lista usa índices lógicos CUDA, evitando nomes físicos incorretos.
O motor atual suporta GPUs NVIDIA CUDA; AMD/Intel não são expostas como aceleração.
A descoberta ocorre em processo filho limitado a oito segundos, sem bloquear a UI.

Salvar altera a próxima transcrição. Sessões e edições existentes permanecem;
use Transcrever ou Repetir transcrição para processar novamente. Pastas ou pesos
diferentes geram outra chave de cache de texto; o áudio renderizado é reutilizável.
A chave usa caminho e metadados dos arquivos, sem leitura integral dos pesos.
Caso os arquivos sejam alterados externamente preservando todos os metadados,
Repetir transcrição força a geração.

Configuração persistente compatível: `%APPDATA%\O Editor\config.json`, ou o arquivo
indicado por `O_EDITOR_CONFIG`. Escrita temporária e substituição atômica preservam
FFmpeg, configurações do Resolve e outras seções. `transcription.device_index`
tem padrão 0 para arquivos antigos. Ao trocar entre CPU/GPU, a precisão volta
a automática para não carregar uma precisão incompatível do dispositivo anterior.

Pacote `o_editor`, pastas de dados e menu único `O EDITOR` permanecem compatíveis
com a instalação existente. Nome visível da janela e cabeçalho: Editor Do Escobar,
EDE. Esta tarefa não altera scripts de edição nem timelines do Resolve.

## Verificação

- UI e persistência: `tests/ui/test_ede_settings.py`.
- Índice CUDA, falha explícita, identidade de arquivos e escrita atômica:
  `tests/unit/test_transcription_settings.py`.
- Troca de modelo e reutilização correta de áudio/cache: BUG-0018.
- Gate: `.venv/Scripts/python.exe scripts/run_regression.py`.

Teste real separado: RTX 4090, índice 0, modelo local large-v3-turbo carregado
e inferência CUDA executada em um segundo de silêncio sintético, sem download.
Evidência local: `runtime/reports/ede-gpu-smoke.json`. Isso não avalia qualidade
da fala nem prova compatibilidade com um segundo modelo/GPU não disponível.


## Download e Sobre

Baixar modelo abre um diálogo cancelável com catálogo CTranslate2. Nenhum download
começa ao abrir configurações: é necessário clicar em Baixar modelo. O processo
fica isolado da GUI e do Resolve; só seleciona a pasta completa, após validação.
A escolha só é persistida ao salvar as configurações. Sobre contém o tutorial,
Pablo Escobar como desenvolvedor e o link fornecido.
