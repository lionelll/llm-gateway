import { NavLink, useNavigate } from "react-router-dom"
import { useAuth } from "../context/AuthContext"

const nav = [
  { to: "/dashboard", label: "概览" },
  { to: "/keys", label: "API Keys" },
  { to: "/usage", label: "用量" },
  { to: "/topup", label: "充值" },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate("/login")
  }

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Sidebar */}
      <aside className="w-56 bg-white border-r border-gray-100 flex flex-col">
        <div className="px-5 py-5 border-b border-gray-100">
          <span className="font-bold text-gray-900 text-base">LLM Gateway</span>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {nav.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-blue-50 text-blue-700 font-medium"
                    : "text-gray-600 hover:bg-gray-50"
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-4 border-t border-gray-100">
          <p className="text-xs text-gray-500 mb-1 truncate">{user?.name}</p>
          <p className="text-xs font-medium text-gray-900 mb-3">余额 ¥{user?.balance}</p>
          <button
            onClick={handleLogout}
            className="text-xs text-gray-500 hover:text-red-500 transition-colors"
          >
            退出登录
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <div className="max-w-5xl mx-auto px-8 py-8">{children}</div>
      </main>
    </div>
  )
}
