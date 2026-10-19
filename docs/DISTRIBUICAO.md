# Distribuição Windows — Editor Do Escobar

Desenvolvedor: [Pablo Escobar](https://pabloescobardj.web.app/Wikipedia-Pablo-Escobar.html).
Repositório: https://github.com/TruePabloEscobar/Editor-do-Escobar.

O EDE integra-se ao DaVinci como **plugin via script**, com aplicativo Python externo.
Não é um OFX nem um executável único. Alvo: Windows x64, Python 3.11 x64,
DaVinci Resolve Studio 21. O menu público continua `Área de Trabalho → Scripts → O EDITOR`.

## Instalar o ZIP

1. Instale Python 3.11 x64 e FFmpeg/ffprobe no PATH. Exemplo de instalação do FFmpeg:
   `winget install Gyan.FFmpeg`. Reabra o terminal após mudar o PATH.
2. Confira o SHA-256 do ZIP com o arquivo `.sha256` da mesma release.
3. Extraia o ZIP completo e execute **Instalar EDE.bat**. Não exige administrador.
4. O instalador valida os hashes dos arquivos, copia o aplicativo para
   `%LOCALAPPDATA%\Editor Do Escobar\releases\<versão-build>` e instala as dependências
   Python pela internet. Só depois atualiza e verifica o launcher do Resolve.
5. Reabra o Resolve e use `O EDITOR`. Na engrenagem, use **Baixar modelo…** ou
   carregue uma pasta CTranslate2 existente. Selecione CPU/GPU e salve.

O ZIP não contém Python, FFmpeg, drivers CUDA ou pesos de modelos. CPU é o fallback.
GPU NVIDIA exige bibliotecas CUDA/cuDNN compatíveis com CTranslate2; a detecção de
GPU não garante que essas bibliotecas estejam instaladas. Não instala drivers.
O botão Sobre apresenta um tutorial dentro do aplicativo.

O download usa os repositórios de dados CTranslate2 do catálogo, sem executar código
remoto. Pode ocupar vários GB; há cancelamento. Um download incompleto fica numa
pasta oculta de staging e nunca é selecionado. O modelo anterior não é sobrescrito.
Ao cancelar um download, a pasta parcial pode ser removida manualmente com o EDE
fechado. Uma pasta final existente inválida é recusada, sem apagá-la automaticamente.

Fonte do mecanismo de download: https://huggingface.co/docs/huggingface_hub/guides/download.
Turbo: https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo.

## Preparar e enviar

- **Preparar pacote EDE.bat**: gera ZIP e SHA-256 em `dist/`, sem publicar.
- **Publicar EDE no GitHub.bat**: executa o gate obrigatório; se passar, gera o pacote,
  envia um snapshot de fontes para `main` no repositório acima e cria uma release
  **em rascunho**, com ZIP e checksum. Requer Git, GitHub CLI e `gh auth login`.
  Você revisa e libera a release pelo GitHub. Não faz force-push nem altera o checkout
  local sujo; utiliza um clone temporário. Não envia o histórico local anterior.

Arquivos são selecionados por raízes/extensões permitidas e um manifesto SHA-256.
Não inclui `.venv`, runtime, caches, sessões, modelos, mídias, tokens ou `nul`.
O ZIP é reproduzível para as mesmas fontes. O hash comprova integridade relativa
ao pacote, não é uma assinatura de código nem certificação de segurança.

## Compatibilidade, atualização e reversão

Configurações/sessões/cache continuam em `%APPDATA%\O Editor`, preservando os dados
das versões anteriores. Cada build é instalado numa pasta separada; não remove
versões antigas. Para voltar, execute o instalador do ZIP anterior. O launcher
move apenas menus antigos conhecidos do EDE para a pasta de histórico; preserva
scripts de terceiros. Feche o EDE antes de reinstalar o mesmo build.

Transcrição, revisão e planejamento são locais. Rough Cut exige cópia verificada.
Zoom/texto têm aplicação real limitada ao preflight; não prometer mutações que
o capability probe não comprovou. Retorno de áudio exige conferência por escuta.
Um travamento anterior do executor real é rastreado em BUG-0017 e permanece
pendente de automação; não é resolvido pela existência deste instalador.

Os testes locais não substituem uma instalação em outro computador nem validação
editorial no Resolve. Resultados desta auditoria: `docs/AUDITORIA_RELEASE_2026-10-19.md`.


As versões de runtime testadas estão fixadas em requirements/runtime-windows.txt.
A release inclui .validation.json com contagens e cobertura, sem caminhos privados.
A CI usa o mesmo runtime e o mesmo gate; a execução remota deve ser conferida no
GitHub Actions, não inferida da existência do YAML.
