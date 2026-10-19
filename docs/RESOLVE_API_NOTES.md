# Notas da API do DaVinci Resolve

## Fontes locais consultadas

- `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\README.txt`;
- exemplos Lua oficiais instalados no mesmo diretório;
- documentação de Workflow Integrations apenas para distinguir seu
  `WorkflowIntegration.GetResolve()` do host de scripts de menu.

O README instalado está atualizado em 15 de julho de 2026. Os exemplos Lua de
scripts de menu usam a função global `Resolve()`.

## Resolução do objeto interno

`internal_common.get_internal_resolve()` registra os globais disponíveis e
verifica cada candidato por uma chamada somente leitura de `GetProjectManager`.
A ordem é:

1. `resolve` global, se já for um objeto Resolve;
2. `app` global, se já for compatível com Resolve;
3. `app.GetResolve`, somente quando o membro for realmente exposto pelo host;
4. `Resolve()`, caminho documentado e usado pelos exemplos oficiais.

Não são usados `DaVinciResolveScript`, `scriptapp`, `fusionscript.dll` ou a
bridge externa.

## Leituras usadas

- `Resolve.Fusion`, `GetProjectManager`, `GetVersionString`, `GetProductName`;
- `ProjectManager.GetCurrentProject`;
- `Project.GetCurrentTimeline`, `GetMediaPool`;
- `Timeline.GetName`, `GetUniqueId`, `GetSetting`, `GetStartFrame`,
  `GetEndFrame`, `GetStartTimecode`, `GetTrackCount`, `GetItemListInTrack`,
  `GetMarkers`;
- `TimelineItem.GetProperty`, `GetFusionCompCount`, `GetFusionCompByIndex`.

Cada leitura é executada e validada. A mera presença de um método não vira
`SUPPORTED`.

## Capabilities mutáveis

Duplicação, tracks, Fusion nodes, keyframes, títulos, Text+, exportação de áudio
e salvamento permanecem `UNVERIFIED` enquanto não forem executados e verificados
em ambiente descartável. O probe desta etapa é exclusivamente `READ_ONLY`.

## Faixas de áudio e render

Leituras documentadas e executadas pelo host interno:

- `Timeline.GetTrackCount("audio")`;
- `Timeline.GetTrackName("audio", index)`;
- `Timeline.GetTrackSubType("audio", index)`;
- `Timeline.GetIsTrackEnabled("audio", index)`;
- `Timeline.GetIsTrackLocked("audio", index)`;
- `Timeline.GetItemListInTrack("audio", index)`.

`GetIsTrackEnabled` é a fonte do campo `enabled`; `muted` é a representação inversa desse
estado no contexto de seleção. Valores que não puderem ser lidos viram `null` ou `unknown`.

A documentação também lista `SetRenderSettings`, `AddRenderJob`, `StartRendering`,
`GetRenderJobStatus`, `StopRendering`, `DeleteRenderJob` e opções de áudio. Ela não lista uma
chave de render para selecionar explicitamente uma ou várias tracks. `SetTrackEnable` existe,
mas é mutável. Por isso seleção de track para render, WAV e restauração permanecem
`UNVERIFIED`, e nenhum backend real foi habilitado.

## Workflow Integration persistente

O README oficial instalado documenta plugins Electron, `Initialize`, `GetResolve`,
`SetAPITimeout`, callbacks `RenderStart`, `RenderStop` e `ResolveQuit`, além de `CleanUp`.
UIManager Python documenta `RunLoop` e `ExitLoop`, mas não timer; por isso não foi usado como
poller automático.

`AudioTrack` aparece em `GenerateSpeech`, não nas chaves de `SetRenderSettings`.
`DuplicateTimeline` e `SetTrackEnable` são documentados, mas exigem teste mutável com
restauração verificada antes de habilitar qualquer backend.

## Resolve 21.1 — leitura de clipes e rough cut

Fonte: `Developer\Scripting\README.md` e `DaVinciResolveScript.pyi` instalados
(atualizados em 31/08/2026). A API não possui função de lâmina/split; por isso o rough
cut reconstrói a timeline em uma cópia.

Leituras adicionadas ao `O Editor - Abrir`: `TimelineItem.GetUniqueId`, `GetType`,
`GetStart/GetEnd(subframe)`, `GetSourceStartFrame/EndFrame`, `GetSourceStartTime/EndTime`,
`GetLeftOffset/GetRightOffset`, `GetClipEnabled`, `GetSpeed`, `GetLinkedItems`,
`GetMediaPoolItem`, `GetSourceAudioChannelMapping`; `MediaPoolItem.GetUniqueId`,
`GetClipProperty("File Path"|"FPS")`.

Mutações, somente em `O Editor - Aplicar Rough Cut` e somente na cópia:
`Timeline.DuplicateTimeline`, `Project.SetCurrentTimeline`, `Timeline.DeleteClips`,
`Timeline.DeleteMarkersByColor("All")`, `MediaPool.AppendToTimeline`,
`TimelineItem.SetProperties`, `SetSourceAudioChannelMapping`, `SetClipEnabled`,
`SetClipColor`, `Timeline.SetClipsLinked`, `Timeline.AddMarker`, `Timeline.SetName`
(somente para marcar uma cópia que falhou).

Convenções não documentadas e tratadas por calibração em tempo de execução:
`AppendClipInfo.endFrame` (inclusivo ou exclusivo) e `recordFrame` (absoluto ou relativo
ao início). A convenção dos `frameId` de marcadores é assumida como relativa ao início
da timeline (UNVERIFIED; afeta apenas marcadores).

Estado: **UNVERIFIED na API real** até a execução do teste manual descrito em
`TRANSCRIPT_ROUGH_CUT.md`.
