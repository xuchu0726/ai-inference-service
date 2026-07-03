-- 用途：
--   wrk 饱和吞吐补充测试；不用于固定 QPS 结论。
--
-- 示例：
--   wrk -t4 -c100 -d30s \
--     -s loadtest/wrk/jobs_admission.lua \
--     http://127.0.0.1:8000

wrk.method = "POST"

wrk.headers["Content-Type"] = "application/json"

wrk.body = [[
{
  "prompt": "Week4 wrk admission saturation request",
  "max_new_tokens": 8,
  "temperature": 0.0,
  "thinking_budget": 0
}
]]

request = function()
  return wrk.format(
    "POST",
    "/jobs",
    wrk.headers,
    wrk.body
  )
end

done = function(summary, latency, requests)
  io.write("\n===== wrk admission summary =====\n")
  io.write(string.format("requests=%d\n", summary.requests))
  io.write(string.format("duration_us=%d\n", summary.duration))
  io.write(string.format("errors.connect=%d\n", summary.errors.connect))
  io.write(string.format("errors.read=%d\n", summary.errors.read))
  io.write(string.format("errors.write=%d\n", summary.errors.write))
  io.write(string.format("errors.status=%d\n", summary.errors.status))
  io.write(string.format("latency_p50_us=%d\n", latency:percentile(50.0)))
  io.write(string.format("latency_p95_us=%d\n", latency:percentile(95.0)))
end
