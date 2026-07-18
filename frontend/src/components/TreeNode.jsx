import { useState } from 'react'
import { api } from '../api'

const statusColors = {
  synced: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  pending: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  failed: 'bg-rose-500/10 text-rose-600 dark:text-rose-400',
}

export default function TreeNode({ node, depth = 0, onPromoted }) {
  const hasChildren = node.children && node.children.length > 0
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const promote = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.promote(node.id)
      onPromoted?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div
        className="group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-200 hover:bg-slate-100/80 dark:hover:bg-slate-800/40"
        style={{ paddingLeft: `${depth * 24 + 12}px` }}
      >
        {depth > 0 && (
          <span className="block h-3.5 w-3.5 border-l-2 border-b-2 border-slate-200/60 dark:border-slate-800/80 rounded-bl-lg -mt-1.5 flex-shrink-0"></span>
        )}
        
        {/* Node Icon */}
        {hasChildren ? (
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-4.5 w-4.5 flex-shrink-0 text-brand-indigo dark:text-brand-cyan">
            <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
          </svg>
        ) : (
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-4.5 w-4.5 flex-shrink-0 text-slate-400 dark:text-slate-500">
            <path fillRule="evenodd" d="M4.5 2A1.5 1.5 0 003 3.5v13a1.5 1.5 0 001.5 1.5h11a1.5 1.5 0 001.5-1.5V7.621a1.5 1.5 0 00-.44-1.06l-4.12-4.122A1.5 1.5 0 0011.378 2H4.5zm2.25 8.5a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5zm0 3a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5z" clipRule="evenodd" />
          </svg>
        )}

        <div className="flex flex-col min-w-0">
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
            {node.title || node.path.split('/').pop()}
          </span>
          <span className="font-mono text-[10px] text-slate-400 dark:text-slate-500 truncate mt-0.5">
            {node.path}
          </span>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {error && (
            <span className="text-[10px] font-semibold text-red-600 dark:text-red-400">{error}</span>
          )}
          {node.is_promotable && !node.is_promoted && (
            <button
              type="button"
              onClick={promote}
              disabled={busy}
              title="Propose promoting this section to its own top-level page"
              className="rounded-full border border-brand-indigo/30 bg-brand-indigo/10 px-2.5 py-0.5 text-[10px] font-semibold text-brand-indigo transition-colors duration-200 hover:bg-brand-indigo/20 disabled:opacity-50 dark:border-brand-cyan/30 dark:bg-brand-cyan/10 dark:text-brand-cyan dark:hover:bg-brand-cyan/20 cursor-pointer"
            >
              {busy ? 'Promoting…' : 'Promote'}
            </button>
          )}
          {node.is_promoted && (
            <span className="rounded-full bg-brand-pink/10 px-2 py-0.5 text-[10px] font-semibold text-brand-pink dark:text-brand-pink">
              promoted
            </span>
          )}
          <span
            className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${statusColors[node.sync_status] || 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'}`}
          >
            {node.sync_status}
          </span>
        </div>
      </div>
      {node.children?.map((child) => (
        <TreeNode key={child.id} node={child} depth={depth + 1} onPromoted={onPromoted} />
      ))}
    </div>
  )
}

