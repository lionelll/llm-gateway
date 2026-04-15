import { useEffect, useState } from "react"
import api from "../api/client"
import { useAuth } from "../context/AuthContext"
import Layout from "../components/Layout"

interface Stats {
  balance: string
  total_requests: number
  total_tokens: number
  total_charged: string
}

export default function Dashboard() {
  const { user } = useAuth()
  const [stats, setStats] = useState<Stats | null>(null)
  const [recentRequests, setRecentRequests] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [dashRes] = await Promise.all([
          api.get("/v1/me/dashboard"),
        ])
        const d = dashRes.data
        const summary = d.usage_summary || {}
        setStats({
          balance: d.balance,
          total_requests: summary.request_count ?? 0,
          total_tokens: summary.total_tokens ?? 0,
          total_charged: summary.billed_amount ?? "0.00",
        })
        setRecentRequests(d.recent_requests || [])
      } catch {
        // fallback: just show balance
        const balRes = await api.get("/v1/me/balance")
        setStats({
          balance: balRes.data.balance,
          total_requests: 0,
          total_tokens: 0,
          total_charged: "0.00",
        })
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const cards = [
    { label: "账户余额", value: `¥${stats?.balance ?? "--"}`, color: "text-blue-600" },
    { label: "累计请求", value: stats?.total_requests?.toLocaleString() ?? "--", color: "text-gray-900" },
    { label: "累计 Tokens", value: stats?.total_tokens?.toLocaleString() ?? "--", color: "text-gray-900" },
    { label: "累计扣费", value: `¥${stats?.total_charged ?? "--"}`, color: "text-gray-900" },
  ]

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">你好，{user?.name} 👋</h1>
        <p className="text-sm text-gray-500 mt-1">以下是你的账户概览</p>
      </div>

      {loading ? (
        <div className="text-sm text-gray-400">加载中...</div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-2 gap-4 mb-8 lg:grid-cols-4">
            {cards.map(({ label, value, color }) => (
              <div key={label} className="bg-white rounded-xl border border-gray-100 p-5">
                <p className="text-xs text-gray-500 mb-1">{label}</p>
                <p className={`text-2xl font-bold ${color}`}>{value}</p>
              </div>
            ))}
          </div>

          {/* Recent requests */}
          <div className="bg-white rounded-xl border border-gray-100">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-900">最近请求</h2>
            </div>
            {recentRequests.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-gray-400">暂无请求记录</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-400 border-b border-gray-100">
                    <th className="text-left px-5 py-3 font-medium">模型</th>
                    <th className="text-left px-5 py-3 font-medium">状态</th>
                    <th className="text-right px-5 py-3 font-medium">Tokens</th>
                    <th className="text-right px-5 py-3 font-medium">费用</th>
                    <th className="text-right px-5 py-3 font-medium">时间</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRequests.map((r, i) => (
                    <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-gray-50">
                      <td className="px-5 py-3 font-mono text-xs text-gray-700">{r.model}</td>
                      <td className="px-5 py-3">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          r.status_code < 300 ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"
                        }`}>
                          {r.status_code}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-right text-gray-600">{r.total_tokens ?? "--"}</td>
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
        </>
      )}
    </Layout>
  )
}
