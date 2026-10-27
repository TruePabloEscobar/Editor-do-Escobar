# Editor Do Escobar — EDE

Desenvolvido por [Pablo Escobar](https://pabloescobardj.web.app/Wikipedia-Pablo-Escobar.html).

Assistente local para DaVinci Resolve Studio 21 no Windows x64. Transcreve áudio,
permite revisar as transcrições e planeja cortes e ajustes. A timeline original é
preservada; o Rough Cut exige uma cópia criada e verificada.

## Baixar e instalar

1. [Baixe o instalador offline do EDE](https://github.com/TruePabloEscobar/Editor-do-Escobar/releases/latest/download/EDE-Instalador-Windows-x64.exe) ([página da versão](https://github.com/TruePabloEscobar/Editor-do-Escobar/releases/tag/v0.2.0-0ae55c69f845)).
2. Confira o SHA-256 com o arquivo `.exe.sha256` correspondente.
3. Execute o EXE. Python 3.11 x64, bibliotecas do aplicativo e FFmpeg/ffprobe já estão
   incluídos; não é necessário instalar Python, usar winget ou configurar o PATH.
4. Aguarde a conferência dos arquivos e do ambiente. Só depois o menu é atualizado.
5. Reabra o Resolve: **Área de Trabalho → Scripts → O EDITOR**.
6. Na engrenagem, escolha **Baixar modelo…** ou uma pasta CTranslate2 existente.
   O botão **Sobre** contém o tutorial do aplicativo.

A instalação é por usuário, em `%LOCALAPPDATA%\Editor Do Escobar\releases`,
sem alterar Python ou PATH permanentes. O EXE registra diagnóstico em
`%LOCALAPPDATA%\Editor Do Escobar\installer-logs`.

O ZIP de código-fonte gerado automaticamente pelo GitHub não é o instalador offline.
Para instalar sem preparar dependências, use o EXE do link acima.

A instalação offline não baixa dependências nem modelos de IA. O primeiro download
de modelo requer internet e clique explícito no aplicativo. Drivers CUDA/cuDNN não
são instalados; o funcionamento em GPU depende das bibliotecas compatíveis. A CPU
continua disponível. O pacote de fontes, sem `runtime-profile.json`, permanece uma
opção para desenvolvedores e exige Python/FFmpeg e instalação de dependências.

A instalação desta versão foi testada em perfil descartável no Windows x64;
a validação física em outro PC e a revisão editorial no Resolve são separadas.

## Atualização e dados

Para atualizar, execute o instalador EXE mais recente com o EDE fechado. Configurações e sessões
em `%APPDATA%\O Editor` são preservadas. Versões anteriores não são removidas.
Para voltar a uma delas, execute o EXE da versão anterior.

O programa funciona como script com aplicativo externo, e não como plugin OFX.
As verificações de integridade fazem parte do instalador. Este repositório contém
somente os arquivos do aplicativo e de instalação, sem projetos, mídias, sessões,
modelos, testes ou ferramentas de desenvolvimento.

Aplicações reais dependem das capacidades disponíveis na versão do Resolve.
Confira os resultados na cópia da timeline antes de usar editorialmente.
