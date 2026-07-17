import { useEffect, useState } from 'react'
import { api } from '../api'
import ApprovalListItem from '../components/ApprovalListItem'
import ApprovalDetail from '../components/ApprovalDetail'

export default function ApprovalQueue() {
  const [approvals, setApprovals] = useState(null)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)

  const load = () => {
    api
      .listApprovals('pending')
      .then((list) => {
        setApprovals(list)
        setSelectedId((current) =>
          list.some((a) => a.id === current) ? current : (list[0]?.id ?? null)
        )
      })
      .catch((err) => setError(err.message))
  }

  useEffect(load, [])

  if (error) {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400">
        Failed to load approvals: {error}
      </p>
    )
  }
  if (approvals === null) {
    return <p className="text-sm text-ink-400 dark:text-paper-300">Loading…</p>
  }

  const structural = approvals.filter((a) => a.change_type !== 'content_edit')
  const contentEdits = approvals.filter((a) => a.change_type === 'content_edit')

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-ink-900 dark:text-paper-50">Approval Queue</h1>
        <p className="mt-1 text-sm text-ink-600 dark:text-paper-300">
          {approvals.length} pending {approvals.length === 1 ? 'change' : 'changes'} awaiting review.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        <div className="flex flex-col gap-5">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold tracking-wide text-ink-400 uppercase dark:text-paper-300">
              <span className="h-1.5 w-1.5 rounded-full bg-purple-500" />
              Structural Changes
              <span className="text-ink-300 dark:text-charcoal-700">({structural.length})</span>
            </div>
            <div className="flex flex-col gap-1.5">
              {structural.map((a) => (
                <ApprovalListItem
                  key={a.id}
                  approval={a}
                  isSelected={a.id === selectedId}
                  onSelect={setSelectedId}
                />
              ))}
              {structural.length === 0 && (
                <p className="px-3 text-xs text-ink-400 dark:text-paper-300">None pending.</p>
              )}
            </div>
          </div>
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold tracking-wide text-ink-400 uppercase dark:text-paper-300">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-500" />
              Content Edits
              <span className="text-ink-300 dark:text-charcoal-700">({contentEdits.length})</span>
            </div>
            <div className="flex flex-col gap-1.5">
              {contentEdits.map((a) => (
                <ApprovalListItem
                  key={a.id}
                  approval={a}
                  isSelected={a.id === selectedId}
                  onSelect={setSelectedId}
                />
              ))}
              {contentEdits.length === 0 && (
                <p className="px-3 text-xs text-ink-400 dark:text-paper-300">None pending.</p>
              )}
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-cream-200 bg-white p-6 shadow-sm dark:border-charcoal-800 dark:bg-charcoal-900">
          {selectedId ? (
            <ApprovalDetail approvalId={selectedId} onResolved={load} />
          ) : (
            <p className="text-sm text-ink-400 dark:text-paper-300">
              {approvals.length === 0 ? 'Nothing pending. New changes will show up here.' : 'Select an item.'}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
