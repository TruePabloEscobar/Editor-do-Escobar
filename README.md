# Editor Do Escobar — EDE

Desenvolvido por [Pablo Escobar](https://pabloescobardj.web.app/Wikipedia-Pablo-Escobar.html).

Assistente local para DaVinci Resolve Studio 21 no Windows x64. Transcreve áudio,
permite revisar as transcrições e planeja cortes e ajustes. A timeline original é
preservada; o Rough Cut exige uma cópia criada e verificada.

## Baixar e instalar

1. [Baixe o ZIP da versão atual](https://github.com/TruePabloEscobar/Editor-do-Escobar/releases/latest).
2. Instale **Python 3.11 x64** e **FFmpeg/ffprobe**, disponíveis no PATH.
3. Confira o SHA-256 do ZIP com o arquivo `.sha256` da mesma versão.
4. Extraia o ZIP completo e execute **Instalar EDE.bat**. Não exige administrador.
5. Reabra o Resolve e acesse **Área de Trabalho → Scripts → O EDITOR**.
6. Na engrenagem, escolha **Baixar modelo…** ou uma pasta CTranslate2 existente.
   O botão **Sobre** contém o tutorial do aplicativo.

A instalação baixa as dependências Python pela internet e mantém cada versão em
`%LOCALAPPDATA%\Editor Do Escobar\releases`. O ZIP não contém Python, FFmpeg,
drivers nem modelos de IA. Modelos são baixados somente por ação explícita na interface.
CPU é o fallback; GPU NVIDIA exige bibliotecas CUDA/cuDNN compatíveis com CTranslate2.

## Atualização e dados

Para atualizar, instale o ZIP mais recente com o EDE fechado. Configurações e sessões
em `%APPDATA%\O Editor` são preservadas. Versões anteriores não são removidas.
Para voltar a uma delas, execute o instalador do ZIP anterior.

O programa funciona como script com aplicativo externo, e não como plugin OFX.
As verificações de integridade fazem parte do instalador. Este repositório contém
somente os arquivos do aplicativo e de instalação, sem projetos, mídias, sessões,
modelos, testes ou ferramentas de desenvolvimento.

Aplicações reais dependem das capacidades disponíveis na versão do Resolve.
Confira os resultados na cópia da timeline antes de usar editorialmente.
