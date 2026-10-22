-- In-memory DaVinci Resolve object model used to test the internal Lua host.
-- Only the documented methods used by O Editor are implemented. Options allow
-- simulating API conventions that are not specified by the documentation.

local F = {}

local id_counter = 0
local function next_id(prefix)
    id_counter = id_counter + 1
    return string.format("%s-%04d", prefix, id_counter)
end

local function new_class()
    local class = {}
    class.__index = class
    return class
end

local MediaPoolItem = new_class()
function MediaPoolItem:GetUniqueId() return self.id end
function MediaPoolItem:GetName() return self.name end
function MediaPoolItem:GetClipProperty(key)
    if key == "File Path" then return self.path end
    if key == "FPS" then return self.fps end
    if key == nil then return {["File Path"] = self.path, FPS = self.fps} end
    return ""
end

local TimelineItem = new_class()
function TimelineItem:GetUniqueId() return self.id end
function TimelineItem:GetName() return self.name end
function TimelineItem:GetType() return self.item_type end
function TimelineItem:GetStart(_subframe) return self.start end
function TimelineItem:GetEnd(_subframe) return self.finish end
function TimelineItem:GetDuration(_subframe) return self.finish - self.start end
function TimelineItem:GetSourceStartFrame()
    return self.src_start + ((self.timeline.project.options or {}).source_readback_bias or 0)
end
function TimelineItem:GetSourceEndFrame() return self.src_end end
function TimelineItem:GetSourceStartTime()
    return self.src_start / ((self.timeline.project.options or {}).source_time_fps or self.timeline.fps)
        + ((self.timeline.project.options or {}).source_time_bias or 0)
end
function TimelineItem:GetSourceEndTime() return self.src_end / self.timeline.fps end
function TimelineItem:GetLeftOffset(_subframe) return self.src_start end
function TimelineItem:GetRightOffset(_subframe)
    if self.mpi and self.mpi.frames then return self.mpi.frames - self.src_end end
    return 0
end
function TimelineItem:GetMediaPoolItem() return self.mpi end
function TimelineItem:GetClipEnabled() return self.enabled end
function TimelineItem:SetClipEnabled(value)
    if (self.timeline.project.options or {}).reject_clip_disable and value == false then return false end
    self.enabled = value; return true
end
function TimelineItem:GetLinkedItems()
    local result = {}
    for _, other in ipairs(self.timeline:_all_items()) do
        if other ~= self and self.link_group ~= nil and other.link_group == self.link_group then
            result[#result + 1] = other
        end
    end
    return result
end
function TimelineItem:GetSourceAudioChannelMapping() return self.mapping or "" end
-- Model of the reported defect: mapping metadata alone does not prove playback source.
-- A setter must not change the native stream provenance observed by this test.
function TimelineItem:SetSourceAudioChannelMapping(value) self.mapping = value; return true end
function TimelineItem:GetFusionCompCount() return self.fusion or 0 end
function TimelineItem:GetSpeed() return {Percentage = self.speed or 100.0} end
function TimelineItem:GetTrackTypeAndIndex() return {self.track_type, self.track_index} end
function TimelineItem:GetProperties()
    local copy = {}
    for key, value in pairs(self.props or {}) do copy[key] = value end
    return copy
end
function TimelineItem:SetProperties(values)
    self.props = self.props or {}
    for key, value in pairs(values) do self.props[key] = value end
    return true
end
function TimelineItem:GetClipColor() return self.color or "" end
function TimelineItem:SetClipColor(value) self.color = value; return true end

local Timeline = new_class()
function F.new_timeline(spec)
    local timeline = setmetatable({
        name = spec.name,
        id = spec.id or next_id("tl"),
        fps = spec.fps or 24,
        start_frame = spec.start_frame or 0,
        start_tc = spec.start_tc or "00:00:00:00",
        end_override = spec.end_frame,
        tracks = {video = {}, audio = {}, subtitle = {}},
        markers = {},
        mutation_log = {},
    }, Timeline)
    return timeline
end
function Timeline:add_track(track_type, name, subtype)
    local list = self.tracks[track_type]
    list[#list + 1] = {name = name, subtype = subtype or "", enabled = true, locked = false, items = {}}
    return #list
end
function Timeline:add_item(track_type, track_index, spec)
    local item = setmetatable({
        id = spec.id or next_id("item"),
        name = spec.name or "clip",
        item_type = spec.item_type or track_type,
        start = spec.start,
        finish = spec.finish,
        src_start = spec.src_start or 0,
        src_end = spec.src_end or (spec.src_start or 0) + (spec.finish - spec.start),
        mpi = spec.mpi,
        enabled = spec.enabled ~= false,
        link_group = spec.link_group,
        mapping = spec.mapping,
        effective_stream = spec.effective_stream or 1,
        fusion = spec.fusion,
        speed = spec.speed,
        props = nil,
        color = spec.color,
        track_type = track_type,
        track_index = track_index,
        timeline = self,
    }, TimelineItem)
    -- Each item owns its properties (DuplicateTimeline must not share tables).
    if spec.props then
        item.props = {}
        for key, value in pairs(spec.props) do item.props[key] = value end
    end
    local items = self.tracks[track_type][track_index].items
    items[#items + 1] = item
    table.sort(items, function(a, b) return a.start < b.start end)
    return item
end
function Timeline:_all_items()
    local result = {}
    for _, track_type in ipairs({"video", "audio", "subtitle"}) do
        for _, track in ipairs(self.tracks[track_type]) do
            for _, item in ipairs(track.items) do result[#result + 1] = item end
        end
    end
    return result
end
function Timeline:GetName() return self.name end
function Timeline:GetUniqueId() return self.id end
function Timeline:GetSetting(key)
    if key == "timelineFrameRate" then return self.fps end
    return ""
end
function Timeline:GetStartFrame() return self.start_frame end
function Timeline:GetEndFrame()
    if self.end_override then return self.end_override end
    local finish = self.start_frame
    for _, item in ipairs(self:_all_items()) do
        if item.finish > finish then finish = item.finish end
    end
    return finish
end
function Timeline:GetStartTimecode() return self.start_tc end
function Timeline:GetTrackCount(track_type) return #self.tracks[track_type] end
function Timeline:GetTrackName(track_type, index) return self.tracks[track_type][index].name end
function Timeline:GetTrackSubType(track_type, index) return self.tracks[track_type][index].subtype end
function Timeline:GetIsTrackEnabled(track_type, index) return self.tracks[track_type][index].enabled end
function Timeline:GetIsTrackLocked(track_type, index) return self.tracks[track_type][index].locked end
function Timeline:SetTrackEnable(track_type, index, value)
    self.mutation_log[#self.mutation_log + 1] = "SetTrackEnable"
    self.tracks[track_type][index].enabled = value
    return true
end
function Timeline:GetItemListInTrack(track_type, index)
    local result = {}
    for _, item in ipairs(self.tracks[track_type][index].items) do result[#result + 1] = item end
    return result
end
function Timeline:DeleteClips(items, _ripple)
    self.mutation_log[#self.mutation_log + 1] = "DeleteClips"
    for _, target in ipairs(items) do
        for _, track_type in ipairs({"video", "audio", "subtitle"}) do
            for _, track in ipairs(self.tracks[track_type]) do
                for position = #track.items, 1, -1 do
                    if track.items[position] == target then table.remove(track.items, position) end
                end
            end
        end
    end
    return true
end
function Timeline:SetClipsLinked(items, linked)
    self.mutation_log[#self.mutation_log + 1] = "SetClipsLinked"
    local group = linked and next_id("link") or nil
    for _, item in ipairs(items) do item.link_group = group end
    return true
end
function Timeline:GetMarkers()
    local copy = {}
    for frame, marker in pairs(self.markers) do copy[frame] = marker end
    return copy
end
function Timeline:AddMarker(frame, color, name, note, duration, custom)
    self.mutation_log[#self.mutation_log + 1] = "AddMarker"
    if self.markers[frame] then return false end
    self.markers[frame] = {color = color, name = name, note = note, duration = duration,
        customData = custom}
    return true
end
function Timeline:DeleteMarkerAtFrame(frame)
    self.mutation_log[#self.mutation_log + 1] = "DeleteMarkerAtFrame"
    if not self.markers[frame] then return false end
    self.markers[frame] = nil
    return true
end
function Timeline:DeleteMarkersByColor(color)
    self.mutation_log[#self.mutation_log + 1] = "DeleteMarkersByColor"
    if color == "All" then self.markers = {} end
    return true
end
function Timeline:SetName(name)
    self.mutation_log[#self.mutation_log + 1] = "SetName"
    self.name = name
    return true
end
function Timeline:DuplicateTimeline(name)
    self.mutation_log[#self.mutation_log + 1] = "DuplicateTimeline(source)"
    local copy = F.new_timeline({name = name, fps = self.fps, start_frame = self.start_frame,
        start_tc = self.start_tc})
    copy.project = self.project
    for _, track_type in ipairs({"video", "audio", "subtitle"}) do
        for index, track in ipairs(self.tracks[track_type]) do
            copy:add_track(track_type, track.name, track.subtype)
            copy.tracks[track_type][index].enabled = track.enabled
            copy.tracks[track_type][index].locked = track.locked
            for _, item in ipairs(track.items) do
                copy:add_item(track_type, index, {
                    name = item.name, item_type = item.item_type, start = item.start,
                    finish = item.finish, src_start = item.src_start, src_end = item.src_end,
                    mpi = item.mpi, enabled = item.enabled, link_group = item.link_group,
                    mapping = item.mapping, props = item.props, effective_stream = item.effective_stream,
                })
            end
        end
    end
    for frame, marker in pairs(self.markers) do copy.markers[frame] = marker end
    if self.project then
        local list = self.project.timelines
        list[#list + 1] = copy
    end
    return copy
end

local MediaPool = new_class()
function MediaPool:AppendToTimeline(infos)
    local project = self.project
    local timeline = project.current
    timeline.mutation_log[#timeline.mutation_log + 1] = "AppendToTimeline"
    local options = project.options
    local created = {}
    for _, info in ipairs(infos) do
        local mpi = info.mediaPoolItem
        local length = info.endFrame - info.startFrame
        if options.end_inclusive then length = length + 1 end
        local record = info.recordFrame
        if options.record_relative then record = timeline.start_frame + record end
        local media_type = info.mediaType or 1
        local track_type = media_type == 2 and "audio" or "video"
        if options.hidden_poly_audio and track_type == "audio" then
            local track = timeline.tracks.audio[info.trackIndex or 1]
            for _, item in ipairs(track and track.items or {}) do
                if item.start == record then return {} end
            end
        end
        local tracks = {info.trackIndex or 1}
        if track_type == "audio" and mpi.audio_tracks and mpi.audio_tracks > 1 then
            for extra = 1, mpi.audio_tracks - 1 do tracks[#tracks + 1] = (info.trackIndex or 1) + extra end
        end
        for stream_index, track_index in ipairs(tracks) do
            while #timeline.tracks[track_type] < track_index do
                timeline:add_track(track_type, "", "")
            end
            local item = timeline:add_item(track_type, track_index, {
                name = mpi.name, start = record, finish = record + length,
                src_start = info.startFrame, src_end = info.startFrame + length, mpi = mpi,
                effective_stream = stream_index,
                mapping = options.shared_poly_source and track_type == "audio" and
                    string.format('{"track_mapping":{"1":{"channel_idx":[%d,%d],"mute":false,"type":"stereo"}}}',
                        stream_index * 2 - 1, stream_index * 2) or nil,
            })
            created[#created + 1] = item
        end
    end
    if options.hidden_poly_audio and #created > 0 then return {created[1]} end
    return created
end

local Project = new_class()
function Project:GetName() return self.name end
function Project:GetCurrentTimeline() return self.current end
function Project:SetCurrentTimeline(timeline) self.current = timeline; return true end
function Project:GetTimelineCount() return #self.timelines end
function Project:GetTimelineByIndex(index) return self.timelines[index] end
function Project:GetMediaPool() return self.media_pool end

function F.new_project(name, options)
    local project = setmetatable({name = name, timelines = {}, options = options or {}}, Project)
    project.media_pool = setmetatable({project = project}, MediaPool)
    return project
end
function F.add_timeline(project, timeline)
    timeline.project = project
    project.timelines[#project.timelines + 1] = timeline
    if project.current == nil then project.current = timeline end
    return timeline
end
function F.new_media(spec)
    return setmetatable({id = spec.id or next_id("mpi"), name = spec.name or "media",
        path = spec.path, fps = spec.fps or 24, frames = spec.frames,
        audio_tracks = spec.audio_tracks}, MediaPoolItem)
end

local ProjectManager = new_class()
function ProjectManager:GetCurrentProject() return self.project end

local Resolve = new_class()
function Resolve:GetProjectManager() return self.manager end
function Resolve:GetVersionString() return "21.1.0.FAKE" end
function Resolve:GetProductName() return "DaVinci Resolve Studio (fake)" end
function F.new_resolve(project)
    local manager = setmetatable({project = project}, ProjectManager)
    return setmetatable({manager = manager}, Resolve)
end

-- Simple four-person podcast: V1 camera + A1..A4 microphones (A1 is camera-linked).
function F.podcast_fixture(options)
    local project = F.new_project("Podcast", options)
    local timeline = F.add_timeline(project, F.new_timeline({name = "Episodio 1", id = "tl-original",
        fps = (options or {}).fixture_fps or 24, start_frame = 86400, start_tc = "01:00:00:00"}))
    timeline:add_track("video", "Camera")
    for _, name in ipairs({"Pablo", "Jessica", "Mileni", "Renne"}) do
        timeline:add_track("audio", name, "mono")
    end
    timeline:add_track("audio", "Musica", "stereo")
    local camera = F.new_media({id = "mpi-cam", name = "cam.mov", path = "D:\\cam.mov", frames = 200000})
    local mics = {}
    for index, name in ipairs({"pablo", "jessica", "mileni", "renne"}) do
        mics[index] = F.new_media({id = "mpi-" .. name, name = name .. ".wav",
            path = "D:\\audio\\" .. name .. ".wav", frames = 200000,
            audio_tracks = (options or {}).poly_audio_tracks})
    end
    if (options or {}).shared_poly_source then
        local shared = F.new_media({id = "mpi-shared", name = "obs.mov", path = "D:\\obs.mov",
            frames = 200000, audio_tracks = 4})
        for index = 1, 4 do
            mics[index] = shared
            timeline.tracks.audio[index].subtype = "stereo"
        end
    end
    if (options or {}).fixture_fps then
        camera.fps = options.fixture_fps
        camera.frames = math.max(camera.frames, (options.fixture_source_start or 0) + 10000)
        for _, mic in ipairs(mics) do mic.fps = options.fixture_fps; mic.frames = camera.frames end
    end
    local music = F.new_media({id = "mpi-music", name = "music.wav", path = "D:\\music.wav", frames = 5000, fps = (options or {}).fixture_fps or 24})
    timeline:add_item("video", 1, {id = "v1-cam", name = "cam.mov", start = 86400, finish = 86400 + 2400,
        src_start = (options or {}).fixture_source_start or 1000, mpi = camera, link_group = "g1", props = {ZoomX = 1.1, Opacity = 100}})
    for index = 1, 4 do
        timeline:add_item("audio", index, {id = "a" .. index .. "-mic", name = mics[index].name,
            start = 86400, finish = 86400 + 2400, src_start = (options or {}).fixture_source_start or 1000, mpi = mics[index],
            link_group = index == 1 and "g1" or nil,
            mapping = '{"track_mapping":{"1":{"channel_idx":[1],"mute":false,"type":"mono"}}}',
            effective_stream = (options or {}).shared_poly_source and index or 1,
            props = {AudioVolume = -3.0}})
        if (options or {}).shared_poly_source then
            timeline.tracks.audio[index].items[1].mapping = string.format(
                '{"track_mapping":{"1":{"channel_idx":[%d,%d],"mute":false,"type":"stereo"}}}',
                index * 2 - 1, index * 2)
        end
    end
    timeline:add_item("audio", 5, {id = "a5-music", name = "music.wav", start = 86400, finish = 86400 + 480,
        src_start = 0, mpi = music})
    -- Marker keys are frame offsets relative to the timeline start (Resolve convention).
    timeline.markers[100] = {color = "Blue", name = "Inicio", note = "", duration = 1, customData = ""}
    timeline.markers[1300] = {color = "Red", name = "Corte", note = "", duration = 1, customData = ""}
    return F.new_resolve(project), project, timeline
end

return F
