import { NavLink, Route, Routes } from 'react-router-dom'
import ProjectsIndex from './pages/ProjectsIndex'
import ProjectTree from './pages/ProjectTree'
import ApprovalQueue from './pages/ApprovalQueue'
import ThemeToggle from './components/ThemeToggle'
import { useTheme } from './useTheme'

const navLinkClass = ({ isActive }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive
      ? 'bg-cream-100 text-ink-900 dark:bg-charcoal-800 dark:text-paper-50'
      : 'text-ink-600 hover:bg-cream-100 hover:text-ink-900 dark:text-paper-300 dark:hover:bg-charcoal-800 dark:hover:text-paper-50'
  }`

function App() {
  const { theme, toggleTheme } = useTheme()

  return (
    <div className="flex min-h-svh flex-col bg-cream-50 text-ink-900 dark:bg-charcoal-950 dark:text-paper-50">
      <nav className="flex items-center justify-between border-b border-cream-200 px-6 py-3 dark:border-charcoal-800">
        <div className="flex items-center gap-6">
          <span className="flex items-center gap-2 font-semibold text-ink-900 dark:text-paper-50">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-accent-500 text-xs font-bold text-white">
              D
            </span>
            Docs Sync
          </span>
          <div className="flex items-center gap-1">
            <NavLink to="/" end className={navLinkClass}>
              Projects
            </NavLink>
            <NavLink to="/approvals" className={navLinkClass}>
              Approval Queue
            </NavLink>
          </div>
        </div>
        <ThemeToggle theme={theme} onToggle={toggleTheme} />
      </nav>
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        <Routes>
          <Route path="/" element={<ProjectsIndex />} />
          <Route path="/repos/:repoId" element={<ProjectTree />} />
          <Route path="/approvals" element={<ApprovalQueue />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
