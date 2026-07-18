import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import TreeNode from '../components/TreeNode'

export default function ProjectTree() {
  const { repoId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const load = () => {
    api.getRepoTree(repoId).then(setData).catch((err) => setError(err.message))
  }

  useEffect(() => {
    setData(null)
    setError(null)
    load()
  }, [repoId])

  if (error) {
    return (
      <div className="rounded-xl border border-red-200/50 bg-red-500/5 p-4 text-sm text-red-600 dark:border-red-500/20 dark:text-red-400">
        Failed to load project: {error}
      </div>
    )
  }

  if (data === null) {
    return (
      <div className="flex h-48 items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-indigo border-t-transparent dark:border-brand-cyan"></div>
      </div>
    )
  }

  return (
    <div>
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-brand-indigo transition-colors duration-200 dark:text-slate-400 dark:hover:text-brand-cyan"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
          <path fillRule="evenodd" d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z" clipRule="evenodd" />
        </svg>
        Back to Projects
      </Link>
      <h1 className="mt-3 mb-8 text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white break-all">
        {data.repo.name}
      </h1>
      {data.tree.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-200 p-12 text-center dark:border-slate-800">
          <p className="text-sm text-slate-500 dark:text-slate-400">No pages synced yet.</p>
        </div>
      ) : (
        <div className="glass-panel rounded-2xl border border-slate-200/60 p-6 shadow-sm dark:border-slate-800/40">
          <div className="flex flex-col gap-0.5">
            {data.tree.map((node) => (
              <TreeNode key={node.id} node={node} onPromoted={load} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

