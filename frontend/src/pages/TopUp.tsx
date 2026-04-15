import { useState } from "react"
import api from "../api/client"
import Layout from "../components/Layout"
import { useAuth } from "../context/AuthContext"

const presets = [50, 100, 200, 500]

export default function TopUp() {
  const [amount, setAmount] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const { user } = useAuth()

  const handleTopUp = async () => {
    const val = parseFloat(amount)
    if (!val || val < 1) { setError("请输入有效金额（最低 ¥1）"); return }
    setLoading(true)
    setError("")
    try {
      const { data } = await api.post("/billing/checkout", { amount_cny: val })
      window.location.href = data.checkout_url
    } catch (err: any) {
      setError(err.response?.data?.detail || "创建支付会话失败，请检查支付服务配置")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">充值</h1>
        <p className="text-sm text-gray-500 mt-1">当前余额：<span className="font-medium text-gray-900">¥{user?.balance}</span></p>
      </div>

      <div className="max-w-md">
        <div className="bg-white rounded-xl border border-gray-100 p-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">选择充值金额</h2>

          <div className="grid grid-cols-4 gap-2 mb-4">
            {presets.map((p) => (
              <button
                key={p}
                onClick={() => setAmount(String(p))}
                className={`py-2 rounded-lg text-sm font-medium border transition-colors ${
                  amount === String(p)
                    ? "bg-blue-50 border-blue-500 text-blue-700"
                    : "border-gray-200 text-gray-600 hover:border-gray-300"
                }`}
              >
                ¥{p}
              </button>
            ))}
          </div>

          <div className="mb-4">
            <label className="block text-xs text-gray-500 mb-1">或自定义金额（CNY）</label>
            <div className="flex items-center border border-gray-200 rounded-lg px-3 py-2 focus-within:ring-2 focus-within:ring-blue-500">
              <span className="text-gray-400 mr-1 text-sm">¥</span>
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
                min="1"
                className="flex-1 text-sm outline-none"
              />
            </div>
          </div>

          {error && (
            <div className="bg-red-50 text-red-600 text-xs px-3 py-2 rounded-lg mb-4">{error}</div>
          )}

          <button
            onClick={handleTopUp}
            disabled={loading || !amount}
            className="w-full bg-blue-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {loading ? "跳转中..." : `通过 Stripe 支付 ¥${amount || "0"}`}
          </button>

          <p className="text-xs text-gray-400 mt-3 text-center">
            充值后扣除 10% 平台服务费，余额按实际到账计算
          </p>
        </div>
      </div>
    </Layout>
  )
}
