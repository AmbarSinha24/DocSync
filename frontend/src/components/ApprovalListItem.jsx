const typeDot = {
  create: 'bg-emerald-500',
  rename: 'bg-blue-500',
  delete: 'bg-red-500',
  content_edit: 'bg-accent-500',
}

export default function ApprovalListItem({ approval, isSelected, onSelect }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(approval.id)}
      className={`block w-full rounded-lg border px-3 py-2.5 text-left text-sm transition-colors ${
        isSelected
          ? 'border-accent-400 bg-accent-500/5 dark:border-accent-600'
          : 'border-transparent bg-white hover:border-cream-300 dark:bg-charcoal-900 dark:hover:border-charcoal-700'
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${typeDot[approval.change_type] || 'bg-ink-400'}`} />
        <span className="truncate font-medium text-ink-900 dark:text-paper-50">{approval.path}</span>
      </div>
      <div className="mt-0.5 pl-3.5 text-xs text-ink-400 dark:text-paper-300">
        {approval.proposed_name || approval.change_type}
      </div>
    </button>
  )
}
