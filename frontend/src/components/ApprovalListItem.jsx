const typeDot = {
  create: 'bg-emerald-500 shadow-sm shadow-emerald-500/50',
  rename: 'bg-blue-500 shadow-sm shadow-blue-500/50',
  delete: 'bg-rose-500 shadow-sm shadow-rose-500/50',
  content_edit: 'bg-brand-indigo shadow-sm shadow-brand-indigo/50',
}

const statusIcon = {
  processing: (
    <div className="h-3.5 w-3.5 flex-shrink-0 animate-spin rounded-full border-2 border-brand-indigo border-t-transparent dark:border-brand-cyan" />
  ),
  done: (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5 flex-shrink-0 text-emerald-500">
      <path fillRule="evenodd" d="M16.7 5.3a1 1 0 010 1.4l-7.5 7.5a1 1 0 01-1.4 0l-3.5-3.5a1 1 0 111.4-1.4l2.8 2.8 6.8-6.8a1 1 0 011.4 0z" clipRule="evenodd" />
    </svg>
  ),
  failed: (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5 flex-shrink-0 text-rose-500">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm-1-9a1 1 0 012 0v3a1 1 0 11-2 0V9zm1-4a1.25 1.25 0 100 2.5A1.25 1.25 0 0010 5z" clipRule="evenodd" />
    </svg>
  ),
}

export default function ApprovalListItem({ approval, isSelected, onSelect, selectMode, checked, onToggleCheck, bulkStatus }) {
  return (
    <div
      className={`group flex w-full items-center gap-2.5 rounded-xl border px-3 py-3 text-left text-sm transition-all duration-200 ${
        isSelected
          ? 'border-brand-indigo/35 bg-brand-indigo/5 dark:border-brand-cyan/35 dark:bg-brand-cyan/5 shadow-sm'
          : 'border-slate-200/50 bg-white/45 hover:border-slate-300 dark:border-slate-800/40 dark:bg-slate-900/30 dark:hover:border-slate-700/60'
      } ${checked ? 'ring-1 ring-brand-indigo/40 dark:ring-brand-cyan/40' : ''}`}
    >
      <div
        className={`grid flex-shrink-0 overflow-hidden transition-all duration-200 ease-out ${
          selectMode ? 'w-4 grid-cols-[1rem] opacity-100' : 'w-0 grid-cols-[0rem] opacity-0'
        }`}
      >
        <input
          type="checkbox"
          checked={!!checked}
          onChange={(e) => {
            e.stopPropagation()
            onToggleCheck(approval.id)
          }}
          onClick={(e) => e.stopPropagation()}
          className="h-4 w-4 cursor-pointer rounded border-slate-300 text-brand-indigo accent-brand-indigo focus:ring-brand-indigo/30 dark:border-slate-700 dark:accent-brand-cyan"
        />
      </div>

      <button type="button" onClick={() => onSelect(approval.id)} className="min-w-0 flex-1 text-left outline-none cursor-pointer">
        <div className="flex items-center gap-2">
          <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${typeDot[approval.change_type] || 'bg-slate-400'}`} />
          <span className="truncate font-semibold text-slate-800 dark:text-slate-200">{approval.path}</span>
        </div>
        <div className="mt-1 pl-3.5 text-[11px] font-medium text-slate-400 dark:text-slate-500 break-all truncate">
          {approval.proposed_name || approval.change_type}
        </div>
      </button>

      {bulkStatus && (
        <div className="flex-shrink-0 transition-opacity duration-200">{statusIcon[bulkStatus]}</div>
      )}
    </div>
  )
}

