import { useEffect, useState } from 'react'
import { api } from '../api'

const typeBadge = {
  create: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20',
  rename: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20',
  delete: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20',
  content_edit: 'bg-brand-indigo/10 text-brand-indigo dark:text-brand-cyan border border-brand-indigo/20 dark:border-brand-cyan/20',
  promote: 'bg-brand-pink/10 text-brand-pink border border-brand-pink/20',
}

export default function ApprovalDetail({ approvalId, onResolved, actor }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
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
    return (
      <div className="rounded-xl border border-red-200/50 bg-red-500/5 p-4 text-sm text-red-600 dark:border-red-500/20 dark:text-red-400">
        Failed to load approval details: {error}
      </div>
    )
  }
  
  if (!detail) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-indigo border-t-transparent dark:border-brand-cyan"></div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Title Header */}
      <div>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="font-mono text-xl font-bold tracking-tight text-slate-900 dark:text-white break-all">
              {detail.path}
            </h2>
            <div className="mt-2 flex items-center gap-2">
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider ${typeBadge[detail.change_type] || 'bg-slate-100 text-slate-600'}`}>
                {detail.change_type}
              </span>
            </div>
          </div>
        </div>

        {detail.change_type === 'create' && (
          <div className="mt-3.5 rounded-xl border border-slate-200/60 bg-slate-50/50 p-3.5 dark:border-slate-800/40 dark:bg-slate-900/30 text-sm">
            {editingName ? (
              <div className="flex items-center gap-3">
                <input
                  className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-900 focus:border-brand-indigo focus:ring-2 focus:ring-brand-indigo/15 focus:outline-none dark:border-slate-800 dark:bg-slate-950 dark:text-white"
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                />
                <button
                  type="button"
                  className="rounded-lg bg-brand-indigo px-3 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-brand-indigo/90"
                  onClick={() =>
                    runAction(async () => {
                      await api.editApproval(detail.id, { actor, proposed_name: nameDraft })
                      setEditingName(false)
                      load()
                    })
                  }
                >
                  Save
                </button>
                <button
                  type="button"
                  className="text-xs font-semibold text-slate-500 hover:text-slate-700"
                  onClick={() => setEditingName(false)}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-4 text-slate-600 dark:text-slate-400">
                <span>
                  Proposed Confluence Title:{' '}
                  <strong className="font-semibold text-slate-900 dark:text-slate-100">
                    {detail.proposed_name}
                  </strong>
                </span>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-xs font-bold text-brand-indigo hover:text-brand-indigo/80 dark:text-brand-cyan dark:hover:text-brand-cyan/80"
                  onClick={() => setEditingName(true)}
                >
                  <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
                    <path d="M5.433 13.917l1.262-3.155A4 4 0 017.58 9.42l6.92-6.918a2.121 2.121 0 013 3l-6.92 6.918c-.383.383-.84.685-1.343.886l-3.154 1.262a.5.5 0 01-.65-.65z" />
                    <path d="M3.5 5.75c0-.69.56-1.25 1.25-1.25H10A.75.75 0 0010 3H4.75A2.75 2.75 0 002 5.75v9.5A2.75 2.75 0 004.75 18h9.5A2.75 2.75 0 0017 15.25V10a.75.75 0 00-1.5 0v5.25c0 .69-.56 1.25-1.25 1.25h-9.5c-.69 0-1.25-.56-1.25-1.25v-9.5z" />
                  </svg>
                  Edit Title
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Flagged Context Card */}
      <div className="rounded-xl border border-slate-200/70 bg-slate-50/50 p-4 dark:border-slate-800/40 dark:bg-slate-900/20">
        <div className="mb-2 flex items-center gap-2 text-[10px] font-bold tracking-wider text-slate-400 uppercase dark:text-slate-500">
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4 text-brand-indigo dark:text-brand-cyan">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
          Why flagged
        </div>
        <div className="font-sans text-xs leading-relaxed text-slate-600 dark:text-slate-400 whitespace-pre-wrap pl-0">
          {detail.pr_context || 'No PR context available (one-time snapshot mode).'}
        </div>
      </div>

      {/* Comparison Editors */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {/* Current live version */}
        <div>
          <div className="flex items-center justify-between rounded-t-xl bg-slate-900 px-4 py-2 border-b border-slate-800">
            <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
              Current
            </span>
          </div>
          <pre className="h-80 overflow-auto border border-t-0 border-slate-200 bg-slate-950 p-4 font-mono text-xs text-slate-300 dark:border-slate-800 rounded-b-xl">
            {detail.current_content || (
              <span className="italic text-slate-600 select-none">(nothing yet)</span>
            )}
          </pre>
        </div>

        {/* Proposed synchronized version */}
        <div>
          <div className="flex items-center justify-between rounded-t-xl bg-slate-900 px-4 py-2 border-b border-slate-800">
            <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
              Proposed
            </span>
            {detail.change_type !== 'delete' && !editingContent && (
              <button
                type="button"
                className="inline-flex items-center gap-1 text-[11px] font-bold text-brand-cyan hover:text-brand-cyan/85 cursor-pointer"
                onClick={() => setEditingContent(true)}
              >
                edit
              </button>
            )}
          </div>
          {editingContent ? (
            <div className="flex flex-col">
              <textarea
                className="h-80 w-full border border-t-0 border-brand-indigo/35 bg-slate-950 p-4 font-mono text-xs text-slate-100 focus:outline-none dark:border-brand-cyan/35 rounded-b-xl"
                value={contentDraft}
                onChange={(e) => setContentDraft(e.target.value)}
              />
              <div className="mt-2 flex items-center gap-2 self-end">
                <button
                  type="button"
                  className="rounded-lg bg-brand-indigo/10 border border-brand-indigo/35 px-3 py-1.5 text-xs font-semibold text-brand-indigo dark:bg-brand-cyan/10 dark:border-brand-cyan/35 dark:text-brand-cyan hover:bg-brand-indigo/20 transition-all duration-200"
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
                <button
                  type="button"
                  className="text-xs font-semibold text-slate-500 hover:text-slate-700"
                  onClick={() => setEditingContent(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <pre className="h-80 overflow-auto border border-t-0 border-slate-200 bg-slate-950 p-4 font-mono text-xs text-slate-300 dark:border-slate-800 rounded-b-xl">
              {detail.proposed_content || (
                <span className="italic text-rose-500 select-none">(nothing — this removes the section)</span>
              )}
            </pre>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200/50 bg-red-500/5 p-3 text-xs text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Regeneration feedback textbox */}
      {showFeedback && (
        <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50/50 p-3 dark:border-slate-800 dark:bg-slate-900/20">
          <input
            className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-brand-indigo focus:ring-2 focus:ring-brand-indigo/15 focus:outline-none dark:border-slate-800 dark:bg-slate-950 dark:text-white dark:focus:border-brand-cyan dark:focus:ring-brand-cyan/15"
            placeholder="What should change about this proposal?"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            disabled={busy}
          />
          <button
            type="button"
            disabled={busy || !feedback.trim()}
            className="rounded-xl bg-gradient-to-r from-brand-indigo to-brand-violet hover:from-brand-indigo/90 hover:to-brand-violet/90 px-4 py-2 text-sm font-semibold text-white shadow-sm disabled:opacity-50 transition-all duration-200 cursor-pointer"
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

      {/* Action Buttons */}
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-200/50 pt-5 dark:border-slate-800/40">
        <button
          type="button"
          disabled={busy}
          className="inline-flex items-center justify-center rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 px-5 py-2.5 text-sm font-bold text-white shadow-md shadow-emerald-500/10 hover:shadow-lg hover:shadow-emerald-500/25 transition-all duration-300 disabled:opacity-50 cursor-pointer"
          onClick={() => runAction(() => api.approve(detail.id, actor))}
        >
          Approve
        </button>
        <button
          type="button"
          disabled={busy}
          className="inline-flex items-center justify-center rounded-xl bg-gradient-to-r from-rose-500 to-red-600 hover:from-rose-600 hover:to-red-700 px-5 py-2.5 text-sm font-bold text-white shadow-md shadow-rose-500/10 hover:shadow-lg hover:shadow-rose-500/25 transition-all duration-300 disabled:opacity-50 cursor-pointer"
          onClick={() => runAction(() => api.reject(detail.id, actor))}
        >
          Reject
        </button>
        {detail.change_type !== 'delete' && (
          <button
            type="button"
            disabled={busy}
            className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950/40 dark:hover:bg-slate-900/50 px-5 py-2.5 text-sm font-bold text-slate-700 dark:text-slate-300 transition-all duration-300 disabled:opacity-50 cursor-pointer"
            onClick={() => setShowFeedback((s) => !s)}
          >
            Regenerate
          </button>
        )}
      </div>
    </div>
  )
}
