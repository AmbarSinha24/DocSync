import { useEffect, useState } from 'react'
import { api } from '../api'

const typeBadge = {
  create: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400',
  rename: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400',
  delete: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400',
  content_edit: 'bg-accent-500/10 text-accent-600 dark:text-accent-400',
}

export default function ApprovalDetail({ approvalId, onResolved }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actor, setActor] = useState('reviewer')
  const [editingName, setEditingName] = useState(false)
  const [editingContent, setEditingContent] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [contentDraft, setContentDraft] = useState('')
  const [showFeedback, setShowFeedback] = useState(false)
  const [feedback, setFeedback] = useState('')

  const load = () => {
    setDetail(null)
    setError(null)
    api
      .getApproval(approvalId)
      .then((d) => {
        setDetail(d)
        setNameDraft(d.proposed_name || '')
        setContentDraft(d.proposed_content || '')
      })
      .catch((err) => setError(err.message))
  }

  useEffect(load, [approvalId])

  const runAction = async (fn) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      onResolved()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (error && !detail) {
    return <p className="text-sm text-red-600 dark:text-red-400">Failed to load: {error}</p>
  }
  if (!detail) {
    return <p className="text-sm text-ink-400 dark:text-paper-300">Loading…</p>
  }

  const isStructural = detail.change_type !== 'content_edit'

  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="flex items-center gap-2">
          <h2 className="font-mono text-lg font-semibold break-all text-ink-900 dark:text-paper-50">
            {detail.path}
          </h2>
          <span
            className={`flex-shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${typeBadge[detail.change_type] || 'bg-cream-100 text-ink-600 dark:bg-charcoal-800 dark:text-paper-300'}`}
          >
            {detail.change_type}
          </span>
        </div>

        {detail.change_type === 'create' && (
          <div className="mt-2 text-sm">
            {editingName ? (
              <div className="flex items-center gap-2">
                <input
                  className="rounded-md border border-cream-300 bg-white px-2 py-1 text-sm text-ink-900 focus:border-accent-500 focus:ring-1 focus:ring-accent-500 focus:outline-none dark:border-charcoal-700 dark:bg-charcoal-850 dark:text-paper-50"
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                />
                <button
                  className="text-xs font-medium text-accent-600 hover:text-accent-700 dark:text-accent-400 dark:hover:text-accent-300"
                  onClick={() =>
                    runAction(async () => {
                      await api.editApproval(detail.id, { actor, proposed_name: nameDraft })
                      setEditingName(false)
                      load()
                    })
                  }
                >
                  save
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-ink-600 dark:text-paper-300">
                Proposed name:{' '}
                <strong className="font-medium text-ink-900 dark:text-paper-50">
                  {detail.proposed_name}
                </strong>
                <button
                  className="text-xs font-medium text-accent-600 hover:text-accent-700 dark:text-accent-400 dark:hover:text-accent-300"
                  onClick={() => setEditingName(true)}
                >
                  edit
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <div>
        <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-ink-400 uppercase dark:text-paper-300">
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
              clipRule="evenodd"
            />
          </svg>
          Why flagged
        </div>
        <div className="rounded-lg border border-cream-200 bg-cream-50 p-3 text-xs whitespace-pre-wrap text-ink-600 dark:border-charcoal-800 dark:bg-charcoal-850 dark:text-paper-300">
          {detail.pr_context || 'No PR context available (one-time snapshot mode).'}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="mb-1.5 text-xs font-semibold tracking-wide text-ink-400 uppercase dark:text-paper-300">
            Current
          </div>
          <pre className="h-64 overflow-auto rounded-lg border border-cream-200 bg-cream-50 p-3 font-mono text-xs whitespace-pre-wrap text-ink-600 dark:border-charcoal-800 dark:bg-charcoal-850 dark:text-paper-300">
            {detail.current_content || '(nothing yet)'}
          </pre>
        </div>
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-semibold tracking-wide text-ink-400 uppercase dark:text-paper-300">
              Proposed
            </span>
            {detail.change_type !== 'delete' && !editingContent && (
              <button
                className="text-xs font-medium text-accent-600 hover:text-accent-700 dark:text-accent-400 dark:hover:text-accent-300"
                onClick={() => setEditingContent(true)}
              >
                edit
              </button>
            )}
          </div>
          {editingContent ? (
            <div>
              <textarea
                className="h-64 w-full rounded-lg border border-accent-400 bg-white p-3 font-mono text-xs text-ink-900 focus:ring-1 focus:ring-accent-500 focus:outline-none dark:bg-charcoal-850 dark:text-paper-50"
                value={contentDraft}
                onChange={(e) => setContentDraft(e.target.value)}
              />
              <button
                className="mt-1 text-xs font-medium text-accent-600 hover:text-accent-700 dark:text-accent-400 dark:hover:text-accent-300"
                onClick={() =>
                  runAction(async () => {
                    await api.editApproval(detail.id, { actor, proposed_content: contentDraft })
                    setEditingContent(false)
                    load()
                  })
                }
              >
                save
              </button>
            </div>
          ) : (
            <pre className="h-64 overflow-auto rounded-lg border border-cream-200 bg-cream-50 p-3 font-mono text-xs whitespace-pre-wrap text-ink-600 dark:border-charcoal-800 dark:bg-charcoal-850 dark:text-paper-300">
              {detail.proposed_content || '(nothing — this removes the section)'}
            </pre>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {showFeedback && (
        <div className="flex items-center gap-2 rounded-lg border border-cream-200 bg-cream-50 p-2 dark:border-charcoal-800 dark:bg-charcoal-850">
          <input
            className="flex-1 rounded-md border border-cream-300 bg-white px-2.5 py-1.5 text-sm text-ink-900 focus:border-accent-500 focus:ring-1 focus:ring-accent-500 focus:outline-none dark:border-charcoal-700 dark:bg-charcoal-900 dark:text-paper-50"
            placeholder="What should change about this proposal?"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
          />
          <button
            disabled={busy}
            className="rounded-md bg-ink-900 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-ink-900/90 disabled:opacity-50 dark:bg-paper-50 dark:text-charcoal-950 dark:hover:bg-paper-50/90"
            onClick={() =>
              runAction(async () => {
                await api.regenerate(detail.id, actor, feedback)
                setShowFeedback(false)
                setFeedback('')
                load()
              })
            }
          >
            Submit
          </button>
        </div>
      )}

      <div className="flex items-center gap-2 border-t border-cream-200 pt-4 dark:border-charcoal-800">
        <button
          disabled={busy}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-emerald-700 disabled:opacity-50"
          onClick={() => runAction(() => api.approve(detail.id, actor))}
        >
          Approve
        </button>
        <button
          disabled={busy}
          className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-red-700 disabled:opacity-50"
          onClick={() => runAction(() => api.reject(detail.id, actor))}
        >
          Reject
        </button>
        {detail.change_type !== 'delete' && (
          <button
            disabled={busy}
            className="rounded-md border border-cream-300 px-4 py-2 text-sm font-medium text-ink-700 transition-colors hover:bg-cream-100 disabled:opacity-50 dark:border-charcoal-700 dark:text-paper-300 dark:hover:bg-charcoal-800"
            onClick={() => setShowFeedback((s) => !s)}
          >
            Regenerate
          </button>
        )}
      </div>
    </div>
  )
}
