--[[
  Twitch Integration — UI/Lua layer.

  Minimal by design: the MD script owns transport (Named Pipes API) and game
  effects. Lua does only what MD can't: decode the inbound JSON line and re-emit
  it to MD as a typed event (so MD can branch per message type without string
  parsing). JSON stays here; game logic stays in MD.

  Flow:
    MD raises  'Twitch.Decode'  with the raw line  ->  onDecode() parses it  ->
    signal_md(<type>, <rawline>)  ->  MD cue 'Twitch_On<Type>' fires.

  [VERIFY on first run] the exact X4 signal-to-MD call. Different X4 versions
  expose this differently (AddUITriggeredEvent argument count/shape). It is
  isolated in signal_md() below so there is exactly one place to fix.
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
local function signal_md(msgtype, rawline)
  -- [VERIFY] argument shape for this X4 version.
  if AddUITriggeredEvent then
    AddUITriggeredEvent("Twitch_Integration", msgtype, rawline)
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
  signal_md(tostring(msg.t), line)
end

-- ---- init ------------------------------------------------------------------

local function init()
  -- MD -> Lua: raw lines to decode.
  if RegisterEvent then RegisterEvent("Twitch.Decode", onDecode) end
  -- Tell MD we are loaded so it (re)starts the pipe read loop.
  signal_md("reloaded", "")
  DebugError("[Twitch] ui lua loaded")
end

init()
return Lib
