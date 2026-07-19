export default function RepoPendingCardsRow({ repos }) {
  if (!repos || repos.length === 0) return null

  return (
    <div className="mb-8 -mx-1 flex gap-3 overflow-x-auto px-1 pb-2">
      {repos.map((repo) => (
        <a
          key={repo.id}
          href={repo.confluence_url}
          target="_blank"
          rel="noopener noreferrer"
          className="group gradient-border glass-panel flex flex-shrink-0 items-center gap-3 rounded-2xl p-4 shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md hover:shadow-brand-indigo/5"
        >
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-brand-indigo/10 text-brand-indigo dark:bg-brand-cyan/10 dark:text-brand-cyan">
            <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
              <path d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V8a2 2 0 00-2-2h-6.5a1 1 0 01-.8-.4L7.7 3.4A1 1 0 006.9 3H4z" />
            </svg>
          </div>
          <div className="min-w-0">
            <div className="max-w-[160px] truncate text-sm font-semibold text-slate-900 transition-colors duration-200 group-hover:text-brand-indigo dark:text-white dark:group-hover:text-brand-cyan">
              {repo.name}
            </div>
            <div className="mt-0.5 text-[11px] font-medium text-slate-400 dark:text-slate-500">
              {repo.pendingCount} pending
            </div>
          </div>
          <svg
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-3.5 w-3.5 flex-shrink-0 text-slate-300 transition-colors group-hover:text-brand-indigo dark:text-slate-600 dark:group-hover:text-brand-cyan"
          >
            <path
              fillRule="evenodd"
              d="M6.22 4.22a.75.75 0 011.06 0l5 5a.75.75 0 010 1.06l-5 5a.75.75 0 11-1.06-1.06L10.94 10 6.22 5.28a.75.75 0 010-1.06z"
              clipRule="evenodd"
            />
          </svg>
        </a>
      ))}
    </div>
  )
}
