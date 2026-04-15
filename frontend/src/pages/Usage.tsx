import { useEffect, useState } from "react"
import api from "../api/client"
import Layout from "../components/Layout"

export default function Usage() {
  const [logs, setLogs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get("/v1/me/dashboard")
      .then(({ data }) => setLogs(data.recent_requests || []))
      .catch(() => setLogs([]))
      .finally(() => setLoading(false))
  }, [])

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">用量记录</h1>
        <p className="text-sm text-gray-500 mt-1">最近的 API 调用记录</p>
      </div>

      <div className="bg-white rounded-xl border border-gray-100">
        {loading ? (
          <div className="px-5 py-8 text-center text-sm text-gray-400">加载中...</div>
        ) : logs.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-gray-400">暂无记录</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-400 border-b border-gray-100">
                <th className="text-left px-5 py-3 font-medium">模型</th>
                <th className="text-right px-5 py-3 font-medium">输入 Tokens</th>
                <th className="text-right px-5 py-3 font-medium">输出 Tokens</th>
                <th className="text-right px-5 py-3 font-medium">费用</th>
                <th className="text-right px-5 py-3 font-medium">时间</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((r, i) => (
                <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-gray-50">
                  <td className="px-5 py-3 font-mono text-xs text-gray-700">{r.model}</td>
                  <td className="px-5 py-3 text-right text-gray-600">{r.prompt_tokens ?? "--"}</td>
                  <td className="px-5 py-3 text-right text-gray-600">{r.completion_tokens ?? "--"}</td>
                  <td className="px-5 py-3 text-right text-gray-600">¥{r.billed_amount ?? "0.00"}</td>
                  <td className="px-5 py-3 text-right text-gray-400 text-xs">
                    {new Date(r.created_at).toLocaleString("zh-CN")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Layout>
  )
}
