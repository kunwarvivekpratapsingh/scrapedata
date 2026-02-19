import { AppShell } from './components/layout/AppShell'
import { DashboardPage } from './pages/DashboardPage'
import { RunEvalPage } from './pages/RunEvalPage'
import { useEvalStore } from './store/useEvalStore'

export function App() {
  const currentPage = useEvalStore((s) => s.currentPage)

  return (
    <AppShell>
      {currentPage === 'run' ? <RunEvalPage /> : <DashboardPage />}
    </AppShell>
  )
}
