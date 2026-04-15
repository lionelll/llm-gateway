import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { AuthProvider, useAuth } from "./context/AuthContext"
import Login from "./pages/Login"
import Register from "./pages/Register"
import Dashboard from "./pages/Dashboard"
import ApiKeys from "./pages/ApiKeys"
import Usage from "./pages/Usage"
import TopUp from "./pages/TopUp"

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { token } = useAuth()
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

function AppRoutes() {
  const { token } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={token ? <Navigate to="/dashboard" /> : <Login />} />
      <Route path="/register" element={token ? <Navigate to="/dashboard" /> : <Register />} />
      <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
      <Route path="/keys" element={<PrivateRoute><ApiKeys /></PrivateRoute>} />
      <Route path="/usage" element={<PrivateRoute><Usage /></PrivateRoute>} />
      <Route path="/topup" element={<PrivateRoute><TopUp /></PrivateRoute>} />
      <Route path="*" element={<Navigate to={token ? "/dashboard" : "/login"} />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
