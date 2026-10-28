# Editor Do Escobar — EDE

Desenvolvido por [Pablo Escobar](https://pabloescobardj.web.app/Wikipedia-Pablo-Escobar.html).

Assistente local para DaVinci Resolve Studio 21 no Windows x64. Transcreve áudio,
permite revisar as transcrições e planeja cortes e ajustes. A timeline original é
preservada; o Rough Cut exige uma cópia criada e verificada.

## Baixar e instalar

1. [Baixe EDE-Instalador-Windows-x64.exe](https://github.com/TruePabloEscobar/Editor-do-Escobar/releases/latest/download/EDE-Instalador-Windows-x64.exe).
   Use o arquivo da release; **Code → Download ZIP** contém fontes para desenvolvimento.
2. Confira o SHA-256 com o arquivo `.exe.sha256` correspondente.
3. Execute o EXE. Python 3.11 x64, bibliotecas, runtimes Microsoft e FFmpeg/ffprobe
   estão incluídos. Não é necessário instalar Python, Node.js, Git, pip ou FFmpeg
   separadamente, usar winget ou configurar o PATH.
4. Aguarde a conferência dos arquivos e do ambiente. Só depois o menu é atualizado.
5. A instalação registra o plugin oficial. Se o Windows solicitar permissão de
   administrador para a pasta de plugins, autorize essa etapa.
6. Reabra o Resolve: **Workspace → Workflow Integrations → EDE — Editor Do Escobar**.
   A interface completa do EDE abre em uma janela própria. O menu **Área de Trabalho
   → Scripts → O EDITOR** continua disponível como alternativa.
7. Na engrenagem, escolha **Baixar modelo…** ou uma pasta CTranslate2 existente.
   O botão **Sobre** contém o tutorial do aplicativo.

É necessária internet para baixar o modelo uma vez pelo botão. Depois a inferência
é local. O modelo não vem dentro do EXE, por escolha do responsável pelo projeto.
Uma instalação nova começa em **CPU / int8**, sem exigir CUDA, cuDNN ou NVIDIA.
Uma seleção de dispositivo existente é preservada. A GPU continua disponível nas
configurações para quem tiver os drivers e bibliotecas compatíveis.

O ZIP **Offline** é uma alternativa: extraia-o inteiro e execute **Instalar EDE.bat**.
Não execute o BAT dentro do visualizador de ZIP do Windows. A instalação é por
usuário, em `%LOCALAPPDATA%\Editor Do Escobar\releases`, sem alterar Python ou PATH
permanentes. O EXE registra diagnóstico em
`%LOCALAPPDATA%\Editor Do Escobar\installer-logs`.

A instalação offline não baixa dependências nem modelos de IA. O primeiro download
de modelo requer internet e clique explícito no aplicativo. Drivers CUDA/cuDNN não
são instalados; o funcionamento em GPU depende das bibliotecas compatíveis. A CPU
continua disponível. O pacote de fontes, sem `runtime-profile.json`, permanece uma
opção para desenvolvedores e exige Python/FFmpeg e instalação de dependências.

A instalação desta versão foi testada em perfil descartável no Windows x64;
a validação física em outro PC e a revisão editorial no Resolve são separadas.

## Atualização e dados

Para atualizar, instale o ZIP mais recente com o EDE fechado. Configurações e sessões
em `%APPDATA%\O Editor` são preservadas. Versões anteriores não são removidas.
Para voltar a uma delas, execute o instalador do ZIP anterior.

O programa funciona como plugin oficial Workflow Integration com aplicativo local
separado para preservar a interface e o processamento atuais. Não é um efeito OFX.
É necessário instalar primeiro o DaVinci Resolve Studio com seu SDK de desenvolvimento.
O módulo nativo é obtido dessa instalação, sem download e sem levar o binário de
outra versão do Resolve. Atualizações preservam o plugin anterior em `.ede-backups`
na pasta de plugins. Feche a janela da integração antes de atualizar.
As verificações de integridade fazem parte do instalador. Este repositório contém
somente os arquivos do aplicativo e de instalação, sem projetos, mídias, sessões,
modelos, testes ou ferramentas de desenvolvimento.

Aplicações reais dependem das capacidades disponíveis na versão do Resolve.
Confira os resultados na cópia da timeline antes de usar editorialmente.
