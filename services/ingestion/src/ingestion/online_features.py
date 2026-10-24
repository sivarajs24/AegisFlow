"""Online feature path: ONE Lua script per transaction, compiled from definitions.py.
Atomic (Redis runs a script without interleaving), idempotent (seen:txn:{id} NX guard,
Decision D3) and on event time (ts passed in, Decision D1).

Keys (all expire after KEY_TTL_S):
  seen:txn:{id}                                  idempotency guard
  feat:acct:{id}                                 hash: n, mean, m2 (Welford), last_ts, sum1..sum4
  vel:acct:{id}:{1m|1h|24h|7d}                   zset member "{txn_id}|{amount_minor}" score ts
  dist:acct:{id}:dev|ip                          zset of devices / IPs seen by the account (score = last seen)
  share:dev:{id} / share:ip:{id}                 zset of accounts seen on the device / IP
  gfeat:acct:{id}                                written by the hourly graph job, read here"""
from aegis_ml.features import definitions as D

SCRIPT = r"""
local function fmt(x) return string.format('%.17g', x) end
local ts = tonumber(ARGV[2])
local amt = tonumber(ARGV[3])
local ttl = tonumber(ARGV[9])
if not redis.call('SET', KEYS[1], '1', 'NX', 'EX', ttl) then
    return {'dup'}
end
local out = {}
local member = ARGV[1] .. '|' .. ARGV[3]

-- 1. velocity windows (ts - w, ts], running sums kept in the account hash
for i = 1, 4 do
    local k = KEYS[2 + i]
    local cut = ts - tonumber(ARGV[9 + i])
    local field = 'sum' .. i
    local s = tonumber(redis.call('HGET', KEYS[2], field)) or 0
    local expired = redis.call('ZRANGEBYSCORE', k, '-inf', fmt(cut))
    for _, m in ipairs(expired) do
        s = s - tonumber(string.match(m, '|(%-?%d+)$'))
    end
    if #expired > 0 then redis.call('ZREMRANGEBYSCORE', k, '-inf', fmt(cut)) end
    redis.call('ZADD', k, fmt(ts), member)
    s = s + amt
    redis.call('HSET', KEYS[2], field, fmt(s))
    redis.call('EXPIRE', k, ttl)
    out[#out + 1] = fmt(redis.call('ZCARD', k))
    out[#out + 1] = fmt(s)
end

-- 2. distinct counts: trim to the window, add the current entity, count
local function distinct(k, w, m, has)
    redis.call('ZREMRANGEBYSCORE', k, '-inf', fmt(ts - w))
    if has == '1' then redis.call('ZADD', k, fmt(ts), m) end
    redis.call('EXPIRE', k, ttl)
    return redis.call('ZCARD', k)
end
local dw, sw = tonumber(ARGV[14]), tonumber(ARGV[15])
out[#out + 1] = fmt(distinct(KEYS[7], dw, ARGV[7], ARGV[4]))
out[#out + 1] = fmt(distinct(KEYS[8], dw, ARGV[8], ARGV[5]))
if ARGV[4] == '1' then out[#out + 1] = fmt(distinct(KEYS[9], sw, ARGV[6], '1'))
else out[#out + 1] = '0' end
if ARGV[5] == '1' then out[#out + 1] = fmt(distinct(KEYS[10], sw, ARGV[6], '1'))
else out[#out + 1] = '0' end

-- 3. z-score from the profile BEFORE this amount (D4), then Welford update
local h = redis.call('HMGET', KEYS[2], 'n', 'mean', 'm2', 'last_ts')
local n = tonumber(h[1]) or 0
local mean = tonumber(h[2]) or 0
local m2 = tonumber(h[3]) or 0
local x = amt / 100
local z = 0
if n >= 2 then
    local sd = math.sqrt(m2 / (n - 1))
    if sd > 0 then z = (x - mean) / sd end
end
local since = -1
if h[4] then since = ts - tonumber(h[4]) end
n = n + 1
local delta = x - mean
mean = mean + delta / n
m2 = m2 + delta * (x - mean)
redis.call('HSET', KEYS[2], 'n', fmt(n), 'mean', fmt(mean), 'm2', fmt(m2), 'last_ts', fmt(ts))
redis.call('EXPIRE', KEYS[2], ttl)
out[#out + 1] = fmt(z)
out[#out + 1] = fmt(since)
return out
"""


def keys_for(t: dict) -> list[str]:
    a = t["account_id"]
    return ([f"seen:txn:{t['id']}", f"feat:acct:{a}"]
            + [f"vel:acct:{a}:{label}" for label in D.WINDOWS]
            + [f"dist:acct:{a}:dev", f"dist:acct:{a}:ip",
               f"share:dev:{t['device_id'] or '-'}", f"share:ip:{t['ip_id'] or '-'}"])


def args_for(t: dict) -> list:
    return ([str(t["id"]), repr(D.epoch_seconds(t["ts"])), str(t["amount_minor"]),
             "1" if t["device_id"] else "0", "1" if t["ip_id"] else "0",
             str(t["account_id"]), str(t["device_id"] or ""), str(t["ip_id"] or ""),
             str(D.KEY_TTL_S)]
            + [str(w) for w in D.WINDOWS.values()]
            + [str(D.DISTINCT_WINDOW_S), str(D.SHARE_WINDOW_S)])


def read_graph(r, account_id) -> dict:
    vals = r.hmget(f"gfeat:acct:{account_id}", *D.GRAPH_FIELDS.values())
    return {name: (float(v) if v is not None else D.BY_NAME[name].default)
            for name, v in zip(D.GRAPH_FIELDS, vals)}


def update(r, t: dict) -> dict | None:
    """t: {id, ts (aware datetime), account_id, amount_minor, device_id, ip_id}.
    Returns the full feature row in FEATURE_LIST order, or None for a duplicate id."""
    res = r.register_script(SCRIPT)(keys=keys_for(t), args=args_for(t))
    res = [x.decode() if isinstance(x, bytes) else x for x in res]
    if res == ["dup"]:
        return None
    row = dict(zip(D.LUA_OUTPUTS, (float(x) for x in res)))
    row.update(D.calendar(t["ts"]))
    row.update(read_graph(r, t["account_id"]))
    return {name: row[name] for name in D.FEATURE_LIST}
