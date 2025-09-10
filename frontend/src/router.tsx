import { createBrowserRouter } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Screener from './pages/Screener'
import Watchlist from './pages/Watchlist'
import History from './pages/History'
import Alerts from './pages/Alerts'
import Learning from './pages/Learning'
import Settings from './pages/Settings'

export const router = createBrowserRouter([
  { path: '/', element: <Dashboard /> },
  { path: '/screener', element: <Screener /> },
  { path: '/watchlist', element: <Watchlist /> },
  { path: '/history', element: <History /> },
  { path: '/alerts', element: <Alerts /> },
  { path: '/learning', element: <Learning /> },
  { path: '/settings', element: <Settings /> },
])
