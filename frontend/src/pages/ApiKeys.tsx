import { useEffect, useState } from "react"
import api from "../api/client"
import Layout from "../components/Layout"

interface ApiKey {
  id: string
  key_prefix: string
  description: string | null
  is_active: boolean
  last_used_at: string | null
  created_at: string
}

export default function ApiKeys() {
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [desc, setDesc] = useState("")
  const [newKey, setNewKey] = useState("")

  const load = async () => {
    try {
      const { data } = await api.get("/v1/me/keys")
      setKeys(data)
    } catch {
      setKeys([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const createKey = async () => {
    setCreating(true)
    try {
      const { data } = await api.post("/v1/me/keys", { description: desc || "My Key" })
      setNewKey(data.api_key)
      setDesc("")
      load()
    } catch (err: any) {
      alert(err.response?.data?.detail || "创建失败")
    } finally {
      setCreating(false)
    }
  }

  const revokeKey = async (id: string) => {
    if (!confirm("确认吊销此 Key？")) return
    await api.delete(`/v1/me/keys/${id}`)
    load()
  }

  return (
    <Layout>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">API Keys</h1>
          <p className="text-sm text-gray-500 mt-1">管理你的 API 访问密钥</p>
        </div>
      </div>

      {/* Create */}
      <div className="bg-white rounded-xl border border-gray-100 p-5 mb-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-3">创建新 Key</h2>
        <div className="flex gap-3">
          <input
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="描述（选填）"
            className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={createKey}
            disabled={creating}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {creating ? "创建中..." : "创建"}
          </button>
        </div>
        {newKey && (
          <div className="mt-3 bg-green-50 border border-green-200 rounded-lg p-3">
            <p className="text-xs text-green-700 mb-1 font-medium">Key 已创建，请立即复制保存，之后不会再显示：</p>
            <code className="text-xs font-mono text-green-800 break-all">{newKey}</code>
          </div>
        )}
      </div>

      {/* List */}
      <div className="bg-white rounded-xl border border-gray-100">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">现有 Keys</h2>
        </div>
        {loading ? (
          <div className="px-5 py-8 text-center text-sm text-gray-400">加载中...</div>
        ) : keys.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-gray-400">暂无 API Key</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-400 border-b border-gray-100">
                <th className="text-left px-5 py-3 font-medium">前缀</th>
                <th className="text-left px-5 py-3 font-medium">描述</th>
                <th className="text-left px-5 py-3 font-medium">状态</th>
                <th className="text-left px-5 py-3 font-medium">最后使用</th>
                <th className="text-right px-5 py-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50">
                  <td className="px-5 py-3 font-mono text-xs">{k.key_prefix}...</td>
                  <td className="px-5 py-3 text-gray-600">{k.description || "—"}</td>
                  <td className="px-5 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                      k.is_active ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"
                    }`}>
                      {k.is_active ? "正常" : "已禁用"}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-gray-400 text-xs">
                    {k.last_used_at ? new Date(k.last_used_at).toLocaleString("zh-CN") : "从未"}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={() => revokeKey(k.id)}
                      className="text-xs text-red-500 hover:text-red-700 transition-colors"
                    >
                      吊销
                    </button>
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
