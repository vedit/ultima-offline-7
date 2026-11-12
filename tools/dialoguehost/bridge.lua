-- Return a canonical wire record for each source VM suspension. Only strings,
-- integers, booleans, dense argument lists and string-keyed records cross the ABI.
local function quote(s)
    return '"' .. s:gsub('[%z\1-\31\\"]', function(c)
        if c == '"' or c == '\\' then return '\\' .. c end
        return string.format('\\u%04x', string.byte(c))
    end) .. '"'
end

local function encode(v, depth)
    assert(depth < 32, 'dialogue value nested too deeply')
    local t = type(v)
    if t == 'string' then return quote(v) end
    if t == 'boolean' or math.type(v) == 'integer' then return tostring(v) end
    if v == nil then return 'null' end
    assert(t == 'table', 'invalid dialogue value')
    local a, keys, count = {}, {}, 0
    for k in pairs(v) do
        count = count + 1
        if type(k) == 'string' then keys[#keys + 1] = k end
    end
    if #keys == 0 then
        for i=1,count do
            assert(v[i] ~= nil, 'sparse dialogue argument array')
            a[i] = encode(v[i], depth + 1)
        end
        return '[' .. table.concat(a, ',') .. ']'
    end
    assert(#keys == count, 'mixed dialogue array and record')
    table.sort(keys)
    for i,k in ipairs(keys) do a[i] = quote(k) .. ':' .. encode(v[k], depth + 1) end
    return '{' .. table.concat(a, ',') .. '}'
end

return function(module, function_id, event_id, item)
    local session = module.start(function_id, event_id, item)
    return function(reply) return encode(session:resume(reply), 0) end
end
