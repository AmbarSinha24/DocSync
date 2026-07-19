import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import ApprovalListItem from '../components/ApprovalListItem'
import ApprovalDetail from '../components/ApprovalDetail'
import RepoPendingCardsRow from '../components/RepoPendingCardsRow'

const BULK_ACTIONS = {
  approve: { label: 'Approve All', verb: 'Approving', fn: (a, id, actor) => api.approve(id, actor) },
  reject: { label: 'Reject All', verb: 'Rejecting', fn: (a, id, actor) => api.reject(id, actor) },
  regenerate: {
    label: 'Regenerate All',
    verb: 'Regenerating',
    fn: (a, id, actor, feedback) => api.regenerate(id, actor, feedback),
  },
}

export default function ApprovalQueue({ actor }) {
  const isMountedRef = useRef(true)
  useEffect(() => {
    return () => {
      isMountedRef.current = false
    }
  }, [])

  const [approvals, setApprovals] = useState(null)
  const [repos, setRepos] = useState(null)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)

  const [selectMode, setSelectMode] = useState(false)
  const [checkedIds, setCheckedIds] = useState(() => new Set())
  const [bulkAction, setBulkAction] = useState(null) // 'approve' | 'reject' | 'regenerate' | null
  const [bulkFeedback, setBulkFeedback] = useState('')
  const [bulkStatuses, setBulkStatuses] = useState(() => new Map()) // id -> 'processing'|'done'|'failed'
  const [bulkProgress, setBulkProgress] = useState(null) // { done, total } | null
  const [bulkError, setBulkError] = useState(null)

  const load = () => {
    api
      .listApprovals('pending')
      .then((list) => {
        if (!isMountedRef.current) return
        setApprovals(list)
        setSelectedId((current) =>
          list.some((a) => a.id === current) ? current : (list[0]?.id ?? null)
        )
        setCheckedIds((current) => new Set([...current].filter((id) => list.some((a) => a.id === id))))
      })
      .catch((err) => {
        if (isMountedRef.current) setError(err.message)
      })
  }

  useEffect(load, [])

  useEffect(() => {
    api.listRepos().then(setRepos).catch(() => setRepos([]))
  }, [])

  const repoGroups = useMemo(() => {
    if (!approvals || !repos) return []
    const countByRepoId = new Map()
    for (const a of approvals) {
      countByRepoId.set(a.repo_id, (countByRepoId.get(a.repo_id) || 0) + 1)
    }
    return repos
      .filter((r) => countByRepoId.has(r.id))
      .map((r) => ({ ...r, pendingCount: countByRepoId.get(r.id) }))
  }, [approvals, repos])

  const exitSelectMode = () => {
    setSelectMode(false)
    setCheckedIds(new Set())
    setBulkAction(null)
    setBulkFeedback('')
    setBulkStatuses(new Map())
    setBulkProgress(null)
    setBulkError(null)
  }

  const toggleCheck = (id) => {
    setCheckedIds((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (!approvals) return
    setCheckedIds((current) =>
      current.size === approvals.length ? new Set() : new Set(approvals.map((a) => a.id))
    )
  }

  const runBulkAction = async (kind) => {
    if (kind === 'regenerate' && bulkAction !== 'regenerate') {
      setBulkAction('regenerate')
      return
    }

    const ids = [...checkedIds]
    const { fn, verb } = BULK_ACTIONS[kind]
    setBulkAction(kind)
    setBulkError(null)
    setBulkProgress({ done: 0, total: ids.length })
    const statuses = new Map()
    setBulkStatuses(statuses)

    for (let i = 0; i < ids.length; i++) {
      const id = ids[i]
      statuses.set(id, 'processing')
      if (isMountedRef.current) setBulkStatuses(new Map(statuses))
      try {
        await fn(approvals, id, actor, bulkFeedback)
        statuses.set(id, 'done')
      } catch {
        statuses.set(id, 'failed')
        if (isMountedRef.current) {
          setBulkError(`${verb} failed for one or more items -- they remain in the queue.`)
        }
      }
      if (isMountedRef.current) {
        setBulkStatuses(new Map(statuses))
        setBulkProgress({ done: i + 1, total: ids.length })
      }
    }

    load()
    setTimeout(() => {
      if (isMountedRef.current) exitSelectMode()
    }, 900)
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-200/50 bg-red-500/5 p-4 text-sm text-red-600 dark:border-red-500/20 dark:text-red-400">
        Failed to load approvals: {error}
      </div>
    )
  }

  if (approvals === null) {
    return (
      <div className="flex h-48 items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-indigo border-t-transparent dark:border-brand-cyan"></div>
      </div>
    )
  }

  const structural = approvals.filter((a) => a.change_type !== 'content_edit')
  const contentEdits = approvals.filter((a) => a.change_type === 'content_edit')

  return (
    <div>
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Approval Queue
          </h1>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            You have <span className="font-semibold text-slate-800 dark:text-slate-200">{approvals.length} pending {approvals.length === 1 ? 'change' : 'changes'}</span> awaiting documentation sync review.
          </p>
        </div>
        {approvals.length > 0 && (
          <button
            type="button"
            onClick={() => (selectMode ? exitSelectMode() : setSelectMode(true))}
            disabled={bulkProgress !== null}
            className={`inline-flex flex-shrink-0 items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-semibold shadow-sm transition-all duration-300 disabled:opacity-50 cursor-pointer ${
              selectMode
                ? 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-300 dark:hover:bg-slate-900/50'
                : 'bg-gradient-to-r from-brand-indigo to-brand-violet text-white hover:shadow-md hover:shadow-brand-indigo/25'
            }`}
          >
            <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
              <path fillRule="evenodd" d="M16.7 5.3a1 1 0 010 1.4l-7.5 7.5a1 1 0 01-1.4 0l-3.5-3.5a1 1 0 111.4-1.4l2.8 2.8 6.8-6.8a1 1 0 011.4 0z" clipRule="evenodd" />
            </svg>
            {selectMode ? 'Cancel' : 'Select'}
          </button>
        )}
      </div>

      {/* Bulk action toolbar */}
      <div
        className={`grid overflow-hidden transition-all duration-300 ease-out ${
          selectMode ? 'mb-6 grid-rows-[1fr] opacity-100' : 'mb-0 grid-rows-[0fr] opacity-0'
        }`}
      >
        <div className="min-h-0">
          <div className="glass-panel flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200/60 p-4 dark:border-slate-800/40">
            <label className="flex items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-400 cursor-pointer">
              <input
                type="checkbox"
                checked={approvals.length > 0 && checkedIds.size === approvals.length}
                onChange={toggleSelectAll}
                disabled={bulkProgress !== null}
                className="h-4 w-4 cursor-pointer rounded border-slate-300 text-brand-indigo accent-brand-indigo focus:ring-brand-indigo/30 dark:border-slate-700 dark:accent-brand-cyan"
              />
              Select all
            </label>

            <span className="text-xs font-semibold text-slate-400 dark:text-slate-500">
              {checkedIds.size} selected
            </span>

            <div className="ml-auto flex flex-wrap items-center gap-2">
              {bulkProgress ? (
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                  {BULK_ACTIONS[bulkAction]?.verb} {bulkProgress.done}/{bulkProgress.total}…
                </span>
              ) : (
                <>
                  <button
                    type="button"
                    disabled={checkedIds.size === 0}
                    onClick={() => runBulkAction('approve')}
                    className="inline-flex items-center justify-center rounded-lg bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 px-3.5 py-1.5 text-xs font-bold text-white shadow-sm transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                  >
                    Approve All
                  </button>
                  <button
                    type="button"
                    disabled={checkedIds.size === 0}
                    onClick={() => runBulkAction('reject')}
                    className="inline-flex items-center justify-center rounded-lg bg-gradient-to-r from-rose-500 to-red-600 hover:from-rose-600 hover:to-red-700 px-3.5 py-1.5 text-xs font-bold text-white shadow-sm transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                  >
                    Reject All
                  </button>
                  <button
                    type="button"
                    disabled={checkedIds.size === 0}
                    onClick={() => runBulkAction('regenerate')}
                    className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950/40 dark:hover:bg-slate-900/50 px-3.5 py-1.5 text-xs font-bold text-slate-700 dark:text-slate-300 transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                  >
                    Regenerate All
                  </button>
                </>
              )}
            </div>

            {/* Regenerate-all feedback input */}
            <div
              className={`grid w-full overflow-hidden transition-all duration-300 ease-out ${
                bulkAction === 'regenerate' && !bulkProgress ? 'grid-rows-[1fr] opacity-100 mt-1' : 'grid-rows-[0fr] opacity-0'
              }`}
            >
              <div className="min-h-0 flex items-center gap-2">
                <input
                  autoFocus
                  className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 placeholder-slate-400 focus:border-brand-indigo focus:ring-2 focus:ring-brand-indigo/15 focus:outline-none dark:border-slate-800 dark:bg-slate-950 dark:text-white"
                  placeholder="What should change about these proposals?"
                  value={bulkFeedback}
                  onChange={(e) => setBulkFeedback(e.target.value)}
                />
                <button
                  type="button"
                  disabled={!bulkFeedback.trim()}
                  onClick={() => runBulkAction('regenerate')}
                  className="rounded-lg bg-gradient-to-r from-brand-indigo to-brand-violet px-3 py-1.5 text-xs font-bold text-white shadow-sm disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                >
                  Submit
                </button>
              </div>
            </div>

            {bulkError && (
              <p className="w-full text-xs text-red-600 dark:text-red-400">{bulkError}</p>
            )}
          </div>
        </div>
      </div>

      <RepoPendingCardsRow repos={repoGroups} />

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[340px_1fr]">
        <div className="flex flex-col gap-6 self-start lg:sticky lg:top-20 lg:max-h-[calc(100svh-6rem)] lg:overflow-y-auto">
          {/* Structural changes */}
          <div>
            <div className="mb-3 flex items-center gap-2 text-[10px] font-bold tracking-wider text-slate-400 uppercase dark:text-slate-500">
              <span className="h-1.5 w-1.5 rounded-full bg-brand-pink shadow-sm shadow-brand-pink/50 animate-pulse" />
              Structural Changes
              <span className="text-slate-300 dark:text-slate-700">({structural.length})</span>
            </div>
            <div className="flex flex-col gap-2">
              {structural.map((a) => (
                <ApprovalListItem
                  key={a.id}
                  approval={a}
                  isSelected={a.id === selectedId}
                  onSelect={setSelectedId}
                  selectMode={selectMode}
                  checked={checkedIds.has(a.id)}
                  onToggleCheck={toggleCheck}
                  bulkStatus={bulkStatuses.get(a.id)}
                />
              ))}
              {structural.length === 0 && (
                <p className="px-3 py-1.5 text-xs text-slate-400 dark:text-slate-500 italic">No structural changes pending.</p>
              )}
            </div>
          </div>

          {/* Content edits */}
          <div>
            <div className="mb-3 flex items-center gap-2 text-[10px] font-bold tracking-wider text-slate-400 uppercase dark:text-slate-500">
              <span className="h-1.5 w-1.5 rounded-full bg-brand-indigo shadow-sm shadow-brand-indigo/50 animate-pulse" />
              Content Edits
              <span className="text-slate-300 dark:text-slate-700">({contentEdits.length})</span>
            </div>
            <div className="flex flex-col gap-2">
              {contentEdits.map((a) => (
                <ApprovalListItem
                  key={a.id}
                  approval={a}
                  isSelected={a.id === selectedId}
                  onSelect={setSelectedId}
                  selectMode={selectMode}
                  checked={checkedIds.has(a.id)}
                  onToggleCheck={toggleCheck}
                  bulkStatus={bulkStatuses.get(a.id)}
                />
              ))}
              {contentEdits.length === 0 && (
                <p className="px-3 py-1.5 text-xs text-slate-400 dark:text-slate-500 italic">No content edits pending.</p>
              )}
            </div>
          </div>
        </div>

        {/* Detail Panel */}
        <div className="glass-panel relative rounded-2xl border border-slate-200/60 p-6 shadow-sm dark:border-slate-800/40 min-h-[450px]">
          {selectedId ? (
            <ApprovalDetail approvalId={selectedId} onResolved={load} actor={actor} />
          ) : (
            <div className="flex h-full min-h-[400px] flex-col items-center justify-center text-center p-6">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-12 w-12 text-slate-300 dark:text-slate-600 mb-3 animate-bounce">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white">No Selected Item</h3>
              <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                {approvals.length === 0 ? 'Nothing pending. New changes will show up here.' : 'Select an approval record from the left sidebar to review details.'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

