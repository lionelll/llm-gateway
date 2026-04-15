import { useState } from "react"
import { useNavigate, Link } from "react-router-dom"
import api from "../api/client"
import { useAuth } from "../context/AuthContext"

export default function Register() {
  const [form, setForm] = useState({ name: "", email: "", password: "" })
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError("")
    try {
      const { data } = await api.post("/auth/register", form)
      login(data.access_token, {
        user_id: data.user_id,
        name: data.name,
        balance: data.balance,
        is_admin: false,
      })
      navigate("/dashboard")
    } catch (err: any) {
      setError(err.response?.data?.detail || "注册失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white p-8 rounded-2xl shadow-sm border border-gray-100 w-full max-w-sm">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">创建账号</h1>
        <p className="text-gray-500 text-sm mb-6">免费开始使用 LLM Gateway</p>

        {error && (
          <div className="bg-red-50 text-red-600 text-sm px-4 py-3 rounded-lg mb-4">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {[
            { label: "用户名", key: "name", type: "text", placeholder: "yourname" },
            { label: "邮箱", key: "email", type: "email", placeholder: "you@example.com" },
            { label: "密码", key: "password", type: "password", placeholder: "至少 8 位" },
          ].map(({ label, key, type, placeholder }) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
              <input
                type={type}
                value={form[key as keyof typeof form]}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder={placeholder}
                required
              />
            </div>
          ))}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {loading ? "注册中..." : "注册"}
          </button>
        </form>

        <p className="text-center text-sm text-gray-500 mt-6">
          已有账号？{" "}
          <Link to="/login" className="text-blue-600 hover:underline">
            直接登录
          </Link>
        </p>
      </div>
    </div>
  )
}
