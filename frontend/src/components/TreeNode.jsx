const statusColors = {
  synced: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400',
  pending: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400',
  failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400',
}

export default function TreeNode({ node, depth = 0 }) {
  return (
    <div>
      <div
        className="flex items-center gap-2 rounded-md px-2 py-2 hover:bg-cream-100 dark:hover:bg-charcoal-800"
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
      >
        {depth > 0 && <span className="text-ink-400 dark:text-paper-300">└</span>}
        <span className="text-sm font-medium text-ink-900 dark:text-paper-50">
          {node.title || node.path}
        </span>
        <span className="font-mono text-xs text-ink-400 dark:text-paper-300">{node.path}</span>
        <span
          className={`ml-auto rounded-full px-2 py-0.5 text-[11px] font-medium ${statusColors[node.sync_status] || 'bg-cream-100 text-ink-600 dark:bg-charcoal-800 dark:text-paper-300'}`}
        >
          {node.sync_status}
        </span>
        {node.is_promoted && (
          <span className="rounded-full bg-accent-500/10 px-2 py-0.5 text-[11px] font-medium text-accent-600 dark:text-accent-400">
            promoted
          </span>
        )}
      </div>
      {node.children?.map((child) => (
        <TreeNode key={child.id} node={child} depth={depth + 1} />
      ))}
    </div>
  )
}
