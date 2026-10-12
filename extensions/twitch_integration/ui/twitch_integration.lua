--[[
  Twitch Integration — UI/Lua layer.

  Minimal by design: the MD script owns transport (Named Pipes API) and game
  effects. Lua does only what MD can't: decode the inbound JSON line and re-emit
  it to MD as a typed event (so MD can branch per message type without string
  parsing). JSON stays here; game logic stays in MD.

  Flow:
    MD raises  'Twitch.Decode'  with the raw line  ->  onDecode() parses it  ->
    signal_md(<type>, <rawline>)  ->  MD cue 'Twitch_On<Type>' fires.

  Signal-to-MD call VERIFIED against sn_mod_support_apis (ui/named_pipes/library.lua):
    AddUITriggeredEvent(screen, control, return_value)
  and MD reads return_value as event.param3 (verified in simple_menu_api.xml).
  Still isolated in signal_md() below in case a future X4 version changes it.
]]--

local Lib = {}

-- ---- tiny JSON decoder (objects/arrays/strings/numbers/bool/null) ----------
-- Enough for our line protocol. Returns (value, nil) or (nil, errmsg).
local function json_decode(s)
  local i, n = 1, #s
  local decode_value

  local function skip_ws()
    while i <= n do
      local c = s:sub(i, i)
      if c == " " or c == "\t" or c == "\n" or c == "\r" then i = i + 1 else break end
    end
  end

  local function decode_string()
    i = i + 1 -- skip opening quote
    local buf = {}
    while i <= n do
      local c = s:sub(i, i)
      if c == '"' then i = i + 1; return table.concat(buf) end
      if c == "\\" then
        local e = s:sub(i + 1, i + 1)
        if e == "n" then buf[#buf + 1] = "\n"
        elseif e == "t" then buf[#buf + 1] = "\t"
        elseif e == "r" then buf[#buf + 1] = "\r"
        elseif e == "u" then
          -- pass the 4 hex digits through as a literal escape (good enough for scaffold)
          buf[#buf + 1] = "\\u" .. s:sub(i + 2, i + 5); i = i + 4
        else buf[#buf + 1] = e end
        i = i + 2
      else
        buf[#buf + 1] = c; i = i + 1
      end
    end
    return nil
  end

  local function decode_number()
    local start = i
    while i <= n and s:sub(i, i):match("[%d%+%-%.eE]") do i = i + 1 end
    return tonumber(s:sub(start, i - 1))
  end

  local function decode_array()
    i = i + 1; local arr = {}
    skip_ws()
    if s:sub(i, i) == "]" then i = i + 1; return arr end
    while true do
      skip_ws()
      arr[#arr + 1] = decode_value()
      skip_ws()
      local c = s:sub(i, i)
      if c == "," then i = i + 1
      elseif c == "]" then i = i + 1; return arr
      else return nil end
    end
  end

  local function decode_object()
    i = i + 1; local obj = {}
    skip_ws()
    if s:sub(i, i) == "}" then i = i + 1; return obj end
    while true do
      skip_ws()
      if s:sub(i, i) ~= '"' then return nil end
      local key = decode_string()
      skip_ws()
      if s:sub(i, i) ~= ":" then return nil end
      i = i + 1; skip_ws()
      obj[key] = decode_value()
      skip_ws()
      local c = s:sub(i, i)
      if c == "," then i = i + 1
      elseif c == "}" then i = i + 1; return obj
      else return nil end
    end
  end

  decode_value = function()
    skip_ws()
    local c = s:sub(i, i)
    if c == "{" then return decode_object()
    elseif c == "[" then return decode_array()
    elseif c == '"' then return decode_string()
    elseif c == "t" and s:sub(i, i + 3) == "true" then i = i + 4; return true
    elseif c == "f" and s:sub(i, i + 4) == "false" then i = i + 5; return false
    elseif c == "n" and s:sub(i, i + 3) == "null" then i = i + 4; return nil
    else return decode_number() end
  end

  skip_ws()
  local ok, val = pcall(decode_value)
  if not ok then return nil, "decode error" end
  return val, nil
end
Lib.json_decode = json_decode

-- ---- signal helpers --------------------------------------------------------

-- The ONE version-sensitive call. Emit a typed event to MD; MD catches it with
-- <event_ui_triggered screen="'Twitch_Integration'" control="<type>"/> and reads
-- the raw JSON line from the event param.
local function signal_md(screen, control, value)
  -- VERIFIED 3-arg form: AddUITriggeredEvent(screen, control, value); MD reads them
  -- as event.param / event.param2 / event.param3 respectively (documented in
  -- common.xsd on <event_ui_triggered>: "param = screen ID, param2 = control ID,
  -- param3 = screen parameters"). cf. sn_mod_support_apis named_pipes/library.lua
  -- L.Raise_Signal -> AddUITriggeredEvent("Named_Pipes", name, return_value).
  if AddUITriggeredEvent then
    AddUITriggeredEvent(screen, control, value)
  else
    DebugError("[Twitch] AddUITriggeredEvent unavailable; cannot signal MD")
  end
end

-- ---- inbound: MD hands us a raw line to decode ------------------------------

local function onDecode(_, line)
  if type(line) ~= "string" or line == "" then return end
  local msg, err = json_decode(line)
  if not msg or type(msg) ~= "table" or not msg.t then
    DebugError("[Twitch] bad line: " .. tostring(err or line))
    return
  end
  -- Vetted commands carry an action id; emit that as the MD `control` so MD can
  -- have one cue per action (Twitch_On<Action>). Other messages emit by type.
  local control = msg.t
  if msg.t == "cmd" and msg.id then control = tostring(msg.id) end
  -- Pass arg VALUES as a ';'-joined STRING. Only STRINGS marshal Lua->MD via
  -- AddUITriggeredEvent on our screen — tables arrive NOTABLE and NUMBERS don't come
  -- through at all (both verified live via tools/x4_probe.py). So multi-value
  -- commands send e.g. "argon;paranid"; MD matches the pair by string comparison.
  -- ORDER: read `argv` (a JSON ARRAY, order preserved by decode_array) with ipairs.
  -- NEVER iterate msg.args with pairs() — it is a hash table and pairs() order is
  -- undefined, which silently SWAPPED multi-arg commands ("50;energycells").
  local vals = {}
  if type(msg.argv) == "table" then
    for _, v in ipairs(msg.argv) do vals[#vals + 1] = tostring(v) end
  elseif type(msg.args) == "table" then
    -- Fallback for lines without argv (older bridge / hand-written test lines):
    -- sorted keys, so at least the order is deterministic instead of random.
    local keys = {}
    for k in pairs(msg.args) do keys[#keys + 1] = k end
    table.sort(keys)
    for _, k in ipairs(keys) do vals[#vals + 1] = tostring(msg.args[k]) end
  end
  local payload = table.concat(vals, ";")
  -- Log every dispatch. An event_ui_triggered with no matching cue is a SILENT
  -- no-op in MD — which is exactly what a stale deployed mod looks like from
  -- chat: the companion confirms the purchase, the game does nothing, and
  -- x4debug.txt says nothing at all. With this line the log always shows the
  -- command reaching the game, so "never arrived" and "arrived, nobody
  -- listening" stop looking identical. (DebugError is the only log channel Lua
  -- has; it prints under [=ERROR=] regardless of severity.)
  DebugError("[Twitch] -> " .. tostring(control) .. " [" .. payload .. "]")
  signal_md("Twitch_Integration", control, payload)

  -- TWO-FIELD COMMANDS. MD strings support formatting and nothing else — no split,
  -- no substring, no indexof (scriptproperties.xml, datatype "string") — so a
  -- ';'-joined payload can NEVER be taken apart on the MD side. But the UI event
  -- carries three independent strings, and `control` is OPTIONAL on
  -- <event_ui_triggered> (common.xsd; vanilla ships the control-less form, e.g.
  -- screen='DockedMenu'). So a 2-arg command ALSO goes out on a screen of its own
  -- with the args in the control+value slots: a cue listening on that screen reads
  -- them as event.param2 / event.param3 with no parsing at all.
  -- The joined form above still fires, so 1-arg cues are untouched. 3+ args would
  -- need another slot and have no consumer yet — joined-only, by design.
  if #vals == 2 then
    signal_md("Twitch_" .. tostring(control), vals[1], vals[2])
  end
end

-- NOTE: in-game process spawn via FFI is NOT possible. X4 restricts dangerous
-- FFI calls even with Protected UI off — `ffi.C.system` returns "Access to FFI
-- function 'system' is restricted!" and `ffi.load("c")` is blocked (verified live
-- 2026-06-09). Engine functions (GetSaveFolderPath etc.) are whitelisted, but libc
-- is not. The companion is therefore launched OUTSIDE the game (Steam launch-option
-- wrapper, or a future native Lua C module). See docs/09 + DEVLOG.

-- ---- init ------------------------------------------------------------------

local function init()
  -- MD -> Lua: raw lines to decode.
  if RegisterEvent then RegisterEvent("Twitch.Decode", onDecode) end
  -- Tell MD we are loaded so it (re)starts the pipe read loop.
  signal_md("Twitch_Integration", "reloaded", "")
  DebugError("[Twitch] ui lua loaded")
end

init()
return Lib
