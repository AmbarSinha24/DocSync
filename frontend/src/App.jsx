import { NavLink, Route, Routes } from 'react-router-dom'
import ProjectsIndex from './pages/ProjectsIndex'
import ProjectTree from './pages/ProjectTree'
import ApprovalQueue from './pages/ApprovalQueue'
import ThemeToggle from './components/ThemeToggle'
import { useTheme } from './useTheme'
import { useActor } from './useActor'

const navLinkClass = ({ isActive }) =>
  `rounded-lg px-4 py-1.5 text-sm font-medium transition-all duration-200 border ${
    isActive
      ? 'bg-brand-indigo/10 text-brand-indigo border-brand-indigo/25 dark:bg-brand-cyan/10 dark:text-brand-cyan dark:border-brand-cyan/25 shadow-sm'
      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-900/60 border-transparent'
  }`

function App() {
  const { theme, toggleTheme } = useTheme()
  const { actor, setActor } = useActor()

  return (
    <div className="relative flex min-h-svh flex-col bg-slate-50 text-slate-900 transition-colors duration-300 dark:bg-[#06080f] dark:text-slate-100 overflow-hidden">
      {/* Background ambient glows */}
      <div className="pointer-events-none absolute top-0 left-1/4 h-[500px] w-[500px] rounded-full bg-[radial-gradient(circle,var(--color-primary-glow)_0%,transparent_70%)] blur-3xl opacity-70"></div>
      <div className="pointer-events-none absolute top-1/3 right-1/4 h-[600px] w-[600px] rounded-full bg-[radial-gradient(circle,var(--color-secondary-glow)_0%,transparent_70%)] blur-3xl opacity-70"></div>

      <nav className="sticky top-0 z-50 flex items-center justify-between border-b border-slate-200/50 bg-white/70 px-6 py-3.5 backdrop-blur-md dark:border-slate-800/40 dark:bg-[#06080f]/75">
        <div className="flex items-center gap-8">
          <NavLink to="/" className="flex items-center gap-2.5 font-bold tracking-tight">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-tr from-brand-indigo via-brand-violet to-brand-pink text-sm font-extrabold text-white shadow-md shadow-brand-indigo/20">
              D
            </span>
            <span className="bg-gradient-to-r from-slate-900 via-brand-indigo to-brand-violet bg-clip-text text-lg text-transparent dark:from-white dark:to-brand-cyan">
              Documentify
            </span>
          </NavLink>
          <div className="flex items-center gap-1.5">
            <NavLink to="/" end className={navLinkClass}>
              Projects
            </NavLink>
            <NavLink to="/approvals" className={navLinkClass}>
              Approval Queue
            </NavLink>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <input
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            placeholder="your name"
            title="Identifies you in the approval audit trail"
            className="w-32 rounded-xl border border-slate-200 bg-white/50 px-3 py-1.5 text-sm text-slate-700 placeholder-slate-400 focus:border-brand-indigo focus:ring-2 focus:ring-brand-indigo/15 focus:outline-none dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-300 dark:focus:border-brand-cyan dark:focus:ring-brand-cyan/15"
          />
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </div>
      </nav>

      <main className="relative z-10 mx-auto w-full max-w-6xl flex-1 px-6 py-10">
        <Routes>
          <Route path="/" element={<ProjectsIndex />} />
          <Route path="/repos/:repoId" element={<ProjectTree />} />
          <Route path="/approvals" element={<ApprovalQueue actor={actor} />} />
        </Routes>
      </main>
    </div>
  )
}

export default App

