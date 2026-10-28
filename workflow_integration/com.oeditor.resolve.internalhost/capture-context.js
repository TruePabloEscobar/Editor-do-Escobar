"use strict";

// Read-only transport of the same schema emitted by internal_common.capture_context.
// WorkflowIntegration exposes Resolve getters, but not the Python/Lua Fusion.Execute API.
async function optional(target, method, ...args) {
  try {
    return target && typeof target[method] === "function" ? await target[method](...args) : null;
  } catch (_) { return null; }
}
function numeric(value) {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  const result = Number(value);
  return Number.isFinite(result) ? result : null;
}
function text(value) {
  return value === null || value === undefined || typeof value === "object" || String(value) === ""
    ? null : String(value);
}
function list(value) {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== "object") return [];
  return Object.keys(value).filter(key => /^\d+$/.test(key)).sort((a, b) => Number(a) - Number(b)).map(key => value[key]);
}
function boolean(value) { return typeof value === "boolean" ? value : null; }

async function captureClip(item, trackType, trackIndex, itemIndex, warnings) {
  const nativeId = text(await optional(item, "GetUniqueId"));
  const id = nativeId || `${trackType}${trackIndex}_item${itemIndex}`;
  if (!nativeId) warnings.push(`Item sem GetUniqueId em ${trackType} ${trackIndex}; identificador sintético usado.`);
  const start = numeric(await optional(item, "GetStart", false));
  const end = numeric(await optional(item, "GetEnd", false));
  if (start === null || end === null) {
    warnings.push(`Item ${id} sem início/fim legível; ignorado.`);
    return null;
  }
  const media = await optional(item, "GetMediaPoolItem");
  const enabled = await optional(item, "GetClipEnabled");
  const speed = await optional(item, "GetSpeed");
  const linkedIds = [];
  for (const linked of list(await optional(item, "GetLinkedItems"))) {
    const linkedId = text(await optional(linked, "GetUniqueId"));
    if (linkedId && linkedId !== id) linkedIds.push(linkedId);
  }
  return {
    item_id: id, track_type: trackType, track_index: trackIndex, item_index: itemIndex,
    name: text(await optional(item, "GetName")),
    item_type: (text(await optional(item, "GetType")) || trackType).toLowerCase(),
    start_frame: start, end_frame: end,
    subframe_start: numeric(await optional(item, "GetStart", true)),
    subframe_end: numeric(await optional(item, "GetEnd", true)),
    source_start_frame: numeric(await optional(item, "GetSourceStartFrame")),
    source_end_frame: numeric(await optional(item, "GetSourceEndFrame")),
    source_start_seconds: numeric(await optional(item, "GetSourceStartTime")),
    source_end_seconds: numeric(await optional(item, "GetSourceEndTime")),
    left_offset_frames: numeric(await optional(item, "GetLeftOffset", false)),
    right_offset_frames: numeric(await optional(item, "GetRightOffset", false)),
    media_pool_item_id: text(await optional(media, "GetUniqueId")),
    file_path: text(await optional(media, "GetClipProperty", "File Path")),
    media_fps: numeric(await optional(media, "GetClipProperty", "FPS")),
    enabled: typeof enabled === "boolean" ? enabled : true,
    linked_item_ids: linkedIds,
    audio_channel_mapping: trackType === "audio" ? text(await optional(item, "GetSourceAudioChannelMapping")) : null,
    fusion_comp_count: trackType === "audio" ? 0 : numeric(await optional(item, "GetFusionCompCount")) || 0,
    speed_percent: speed && typeof speed === "object" ? numeric(speed.Percentage) : null,
  };
}

async function identity(resolve) {
  const manager = await resolve.GetProjectManager();
  const project = manager ? await manager.GetCurrentProject() : null;
  const timeline = project ? await project.GetCurrentTimeline() : null;
  if (!project || !timeline) throw new Error("Abra um projeto e uma timeline no DaVinci Resolve.");
  const value = {
    project_name: text(await project.GetName()), timeline_name: text(await timeline.GetName()),
    timeline_id: text(await optional(timeline, "GetUniqueId")),
    fps: numeric(await timeline.GetSetting("timelineFrameRate")),
    start_frame: numeric(await timeline.GetStartFrame()), end_frame: numeric(await timeline.GetEndFrame()),
  };
  if (!value.project_name || !value.timeline_name || !(value.fps > 0) ||
      value.start_frame === null || value.end_frame === null || value.end_frame <= value.start_frame) {
    throw new Error("O Resolve retornou um contexto de timeline inválido.");
  }
  return { timeline, value };
}

async function captureContext(resolve, progress = async () => {}) {
  const before = await identity(resolve);
  const timeline = before.timeline;
  const tracks = [], clips = [], audioTracks = [], warnings = [];
  const counts = {};
  for (const type of ["video", "audio", "subtitle"]) {
    // Required collection reads fail closed. Optional clip evidence remains null,
    // so existing planners can block unsupported material without fabricating data.
    const count = numeric(await timeline.GetTrackCount(type));
    if (!Number.isInteger(count) || count < 0) throw new Error(`Contagem de faixas inválida: ${type}.`);
    counts[type] = count;
    for (let index = 1; index <= count; index++) {
      const subtype = type === "audio" ? text(await optional(timeline, "GetTrackSubType", "audio", index)) : null;
      const enabled = boolean(await optional(timeline, "GetIsTrackEnabled", type, index));
      const locked = boolean(await optional(timeline, "GetIsTrackLocked", type, index));
      const name = text(await optional(timeline, "GetTrackName", type, index)) || "";
      tracks.push({ track_type: type, index, name, subtype, enabled, locked });
      const collection = await timeline.GetItemListInTrack(type, index);
      if (collection === null || collection === undefined) throw new Error(`Não foi possível listar a faixa ${type} ${index}.`);
      const items = list(collection);
      if (type === "audio") audioTracks.push({ index, label: `A${index}`, name, track_type: "audio",
        audio_type: ["mono", "stereo", "adaptive"].includes((subtype || "").toLowerCase()) ? subtype.toLowerCase() : "unknown",
        enabled, muted: enabled === null ? null : !enabled, locked, item_count: items.length });
      for (let offset = 0; offset < items.length; offset++) {
        const clip = await captureClip(items[offset], type, index, offset + 1, warnings);
        if (clip) clips.push(clip);
        if (offset % 25 === 0) await progress(clips.length);
      }
    }
  }
  const after = await identity(resolve);
  if (JSON.stringify(before.value) !== JSON.stringify(after.value)) {
    throw new Error("O projeto ou a timeline mudou durante a leitura. Aguarde e abra novamente o EDE.");
  }
  return {
    schema_version: 3, context_kind: "internal_resolve_host", launched_from_resolve: true,
    timestamp: new Date().toISOString(), resolve_source: "WorkflowIntegration.GetResolve",
    resolve_version: text(await resolve.GetVersionString()), product_name: text(await resolve.GetProductName()),
    ...before.value, duration_frames: before.value.end_frame - before.value.start_frame,
    start_timecode: text(await optional(timeline, "GetStartTimecode")) || "",
    track_counts: counts, audio_track_count: counts.audio, audio_tracks: audioTracks,
    layout: { schema_version: 1, tracks, clips, warnings },
  };
}
module.exports = { captureContext };
