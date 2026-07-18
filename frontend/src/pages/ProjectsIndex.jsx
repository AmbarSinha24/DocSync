import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAddRepoJob } from '../useAddRepoJob'

function RepoIcon() {
  return (
    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-indigo/10 text-brand-indigo dark:bg-brand-cyan/10 dark:text-brand-cyan">
      <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
        <path d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V8a2 2 0 00-2-2h-6.5a1 1 0 01-.8-.4L7.7 3.4A1 1 0 006.9 3H4z" />
      </svg>
    </div>
  )
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
      <path
        fillRule="evenodd"
        d="M8.75 1A2.75 2.75 0 006 3.75v.25H3.5a.75.75 0 000 1.5h.55l.7 10.32A2.75 2.75 0 007.49 18h5.02a2.75 2.75 0 002.74-2.18l.7-10.32h.55a.75.75 0 000-1.5H14v-.25A2.75 2.75 0 0011.25 1h-2.5zM10 4V3.75c0-.69.56-1.25 1.25-1.25h-2.5C8.06 2.5 7.5 3.06 7.5 3.75V4h5zM8.5 8.25a.75.75 0 00-1.5 0v6.5a.75.75 0 001.5 0v-6.5zm3.5 0a.75.75 0 00-1.5 0v6.5a.75.75 0 001.5 0v-6.5z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function RepoCard({ repo, onDeleted }) {
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState(null)
  const [exiting, setExiting] = useState(false)

  const requestDelete = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setError(null)
    setConfirming(true)
  }

  const cancelDelete = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setConfirming(false)
    setError(null)
  }

  const confirmDelete = async (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDeleting(true)
    setError(null)
    try {
      await api.deleteRepo(repo.id)
      setExiting(true)
      setTimeout(() => onDeleted(repo.id), 300)
    } catch (err) {
      setDeleting(false)
      setError(err.message)
    }
  }

  return (
    <Link
      to={`/repos/${repo.id}`}
      className={`group gradient-border glass-panel relative rounded-2xl p-6 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-md hover:shadow-brand-indigo/5 ${
        exiting ? 'pointer-events-none scale-95 opacity-0' : 'scale-100 opacity-100'
      }`}
    >
      {confirming ? (
        <div className="flex min-h-10 flex-col justify-center gap-2">
          <p className="text-xs font-semibold text-red-600 dark:text-red-400">
            Delete this repo? It's also removed from Confluence.
          </p>
          {error && <p className="text-[11px] text-red-500">{error}</p>}
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={deleting}
              onClick={confirmDelete}
              className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1 text-xs font-bold text-white shadow-sm transition-all duration-200 hover:bg-red-700 disabled:opacity-60 cursor-pointer"
            >
              {deleting && (
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              )}
              {deleting ? 'Deleting…' : 'Delete'}
            </button>
            <button
              type="button"
              disabled={deleting}
              onClick={cancelDelete}
              className="text-xs font-semibold text-slate-500 hover:text-slate-700 disabled:opacity-60 dark:text-slate-400"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between">
          <RepoIcon />
          <div className="flex items-center gap-2">
            {repo.last_synced_sha ? (
              <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                </span>
                synced
              </span>
            ) : (
              <span className="flex items-center gap-1.5 rounded-full bg-amber-500/10 px-2.5 py-0.5 text-xs font-semibold text-amber-600 dark:text-amber-400">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500"></span>
                pending
              </span>
            )}
            <button
              type="button"
              onClick={requestDelete}
              title="Delete repo"
              className="text-slate-400 transition-colors duration-200 hover:text-red-500 dark:text-slate-600 dark:hover:text-red-500 cursor-pointer"
            >
              <TrashIcon />
            </button>
          </div>
        </div>
      )}

      <div className="mt-4 text-base font-semibold tracking-tight text-slate-900 transition-colors duration-200 group-hover:text-brand-indigo dark:text-white dark:group-hover:text-brand-cyan break-all">
        {repo.name}
      </div>
      <div className="mt-1 text-xs font-medium text-slate-400 dark:text-slate-500">
        {repo.source_type === 'github_app' ? 'GitHub App Integration' : 'Public snapshot'}
      </div>
      <div className="mt-5 flex items-center justify-between border-t border-slate-200/50 pt-4 text-xs text-slate-500 dark:border-slate-800/40 dark:text-slate-400">
        <span>Last Sync</span>
        {repo.last_synced_sha ? (
          <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            {repo.last_synced_sha.slice(0, 7)}
          </code>
        ) : (
          <span className="italic text-slate-400">never</span>
        )}
      </div>
    </Link>
  )
}

function AddRepoForm({ onStart, disabled }) {
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onStart(url)
      setOpen(false)
      setUrl('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-brand-indigo to-brand-violet px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all duration-300 hover:shadow-md hover:shadow-brand-indigo/25 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
          <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
        </svg>
        Add Repo
      </button>
    )
  }

  return (
    <form
      onSubmit={submit}
      className="glass-panel flex items-center gap-2 rounded-xl border border-slate-200/60 p-2 dark:border-slate-800/40"
    >
      <input
        autoFocus
        className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-900 placeholder-slate-400 focus:border-brand-indigo focus:ring-2 focus:ring-brand-indigo/15 focus:outline-none dark:border-slate-800 dark:bg-slate-950 dark:text-white"
        placeholder="github.com/owner/repo or owner/repo"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        disabled={busy}
      />
      <button
        type="submit"
        disabled={busy || !url.trim()}
        className="rounded-lg bg-gradient-to-r from-brand-indigo to-brand-violet px-3 py-1.5 text-xs font-bold text-white shadow-sm disabled:opacity-50 cursor-pointer"
      >
        {busy ? 'Starting…' : 'Add'}
      </button>
      <button
        type="button"
        className="text-xs font-semibold text-slate-500 hover:text-slate-700 dark:text-slate-400"
        onClick={() => {
          setOpen(false)
          setError(null)
        }}
      >
        Cancel
      </button>
      {error && (
        <p className="absolute mt-14 max-w-md rounded-lg border border-red-200/50 bg-red-500/5 px-3 py-1.5 text-xs text-red-600 shadow-sm dark:border-red-500/20 dark:bg-slate-950 dark:text-red-400">
          {error}
        </p>
      )}
    </form>
  )
}

const JOB_STATUS_TEXT = {
  queued: 'Queued…',
  processing: 'Reading the repo and drafting documentation — this can take a minute for larger repos.',
  done: 'Done.',
  failed: 'Failed.',
}

function JobStatusCard({ job, onDismiss }) {
  const inProgress = job.status === 'queued' || job.status === 'processing'

  return (
    <div className="glass-panel mb-6 flex items-center gap-4 rounded-2xl border border-slate-200/60 p-4 dark:border-slate-800/40">
      {inProgress ? (
        <div className="h-5 w-5 flex-shrink-0 animate-spin rounded-full border-2 border-brand-indigo border-t-transparent dark:border-brand-cyan"></div>
      ) : job.status === 'done' ? (
        <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
            <path
              fillRule="evenodd"
              d="M16.7 5.3a1 1 0 010 1.4l-7.5 7.5a1 1 0 01-1.4 0l-3.5-3.5a1 1 0 111.4-1.4l2.8 2.8 6.8-6.8a1 1 0 011.4 0z"
              clipRule="evenodd"
            />
          </svg>
        </div>
      ) : (
        <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-red-500/15 text-red-600 dark:text-red-400">
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm-1-9a1 1 0 012 0v3a1 1 0 11-2 0V9zm1-4a1.25 1.25 0 100 2.5A1.25 1.25 0 0010 5z"
              clipRule="evenodd"
            />
          </svg>
        </div>
      )}

      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-slate-900 dark:text-white">{job.full_name}</div>
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
          {job.status === 'failed' ? job.error_message || 'Something went wrong.' : JOB_STATUS_TEXT[job.status]}
          {job.status === 'done' && job.pending_approvals != null && (
            <> {job.pending_approvals} change{job.pending_approvals === 1 ? '' : 's'} ready for review.</>
          )}
        </p>
      </div>

      {job.status === 'done' && job.repo_id != null && (
        <Link
          to={`/repos/${job.repo_id}`}
          onClick={onDismiss}
          className="flex-shrink-0 rounded-lg bg-gradient-to-r from-brand-indigo to-brand-violet px-3 py-1.5 text-xs font-bold text-white shadow-sm"
        >
          View Repo
        </Link>
      )}

      {!inProgress && (
        <button
          type="button"
          onClick={onDismiss}
          className="flex-shrink-0 text-xs font-semibold text-slate-500 hover:text-slate-700 dark:text-slate-400"
        >
          Dismiss
        </button>
      )}
    </div>
  )
}

export default function ProjectsIndex() {
  const [repos, setRepos] = useState(null)
  const [error, setError] = useState(null)
  const { job, start, dismiss } = useAddRepoJob()

  const load = () => {
    api.listRepos().then(setRepos).catch((err) => setError(err.message))
  }

  useEffect(load, [])

  useEffect(() => {
    if (job?.status === 'done') load()
  }, [job?.status])

  if (error) {
    return (
      <div className="rounded-xl border border-red-200/50 bg-red-500/5 p-4 text-sm text-red-600 dark:border-red-500/20 dark:text-red-400">
        Failed to load projects: {error}
      </div>
    )
  }

  if (repos === null) {
    return (
      <div className="flex h-48 items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-indigo border-t-transparent dark:border-brand-cyan"></div>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Projects
          </h1>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            Onboarded repositories synced automatically to Confluence spaces.
          </p>
        </div>
        <div className="relative">
          <AddRepoForm onStart={start} disabled={job != null && job.status !== 'done' && job.status !== 'failed'} />
        </div>
      </div>

      {job && <JobStatusCard job={job} onDismiss={dismiss} />}

      {repos.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-200 p-12 text-center dark:border-slate-800">
          <p className="text-sm text-slate-500 dark:text-slate-400">No projects onboarded yet.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {repos.map((repo) => (
            <RepoCard
              key={repo.id}
              repo={repo}
              onDeleted={(id) => setRepos((current) => current.filter((r) => r.id !== id))}
            />
          ))}
        </div>
      )}
    </div>
  )
}
