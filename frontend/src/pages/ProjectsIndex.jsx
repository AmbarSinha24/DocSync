import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

function RepoIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5 text-accent-500">
      <path d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V8a2 2 0 00-2-2h-6.5a1 1 0 01-.8-.4L7.7 3.4A1 1 0 006.9 3H4z" />
    </svg>
  )
}

export default function ProjectsIndex() {
  const [repos, setRepos] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.listRepos().then(setRepos).catch((err) => setError(err.message))
  }, [])

  if (error) {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400">
        Failed to load projects: {error}
      </p>
    )
  }

  if (repos === null) {
    return <p className="text-sm text-ink-400 dark:text-paper-300">Loading projects…</p>
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-ink-900 dark:text-paper-50">Projects</h1>
        <p className="mt-1 text-sm text-ink-600 dark:text-paper-300">
          Repositories with docs synced to Confluence.
        </p>
      </div>

      {repos.length === 0 ? (
        <p className="text-sm text-ink-400 dark:text-paper-300">No projects onboarded yet.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {repos.map((repo) => (
            <Link
              key={repo.id}
              to={`/repos/${repo.id}`}
              className="group rounded-xl border border-cream-200 bg-white p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:border-accent-400 hover:shadow-md dark:border-charcoal-800 dark:bg-charcoal-900 dark:hover:border-accent-600"
            >
              <div className="flex items-start justify-between">
                <RepoIcon />
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                    repo.last_synced_sha
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400'
                      : 'bg-cream-100 text-ink-600 dark:bg-charcoal-800 dark:text-paper-300'
                  }`}
                >
                  {repo.last_synced_sha ? 'synced' : 'pending'}
                </span>
              </div>
              <div className="mt-3 font-medium break-all text-ink-900 group-hover:text-accent-600 dark:text-paper-50 dark:group-hover:text-accent-400">
                {repo.name}
              </div>
              <div className="mt-1 text-xs text-ink-400 dark:text-paper-300">
                {repo.source_type === 'github_app' ? 'GitHub App' : 'Public snapshot'}
              </div>
              <div className="mt-3 border-t border-cream-200 pt-3 text-xs text-ink-600 dark:border-charcoal-800 dark:text-paper-300">
                {repo.last_synced_sha ? (
                  <>
                    Last synced <code className="font-mono">{repo.last_synced_sha.slice(0, 7)}</code>
                  </>
                ) : (
                  'Not yet synced'
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
