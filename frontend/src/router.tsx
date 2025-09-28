import { Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './layouts/AppShell';
import Dashboard from './pages/DashboardPage';
import Screener from './pages/Screener';
import Watchlist from './pages/Watchlist';
import History from './pages/History';
import Alerts from './pages/Alerts';
import Settings from './pages/Settings';
import Learning from './pages/Learning'; // create stub if you don’t have it yet

export default function AppRouter() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="/screener" element={<Screener />} />
        <Route path="/watchlist" element={<Watchlist />} />
        <Route path="/history" element={<History />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/learning" element={<Learning />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
