import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import TreeNode from '../components/TreeNode'

export default function ProjectTree() {
  const { repoId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setData(null)
    setError(null)
    api.getRepoTree(repoId).then(setData).catch((err) => setError(err.message))
  }, [repoId])

  if (error) {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400">
        Failed to load project: {error}
      </p>
    )
  }

  if (data === null) {
    return <p className="text-sm text-ink-400 dark:text-paper-300">Loading…</p>
  }

  return (
    <div>
      <Link
        to="/"
        className="text-xs font-medium text-ink-600 hover:text-accent-600 dark:text-paper-300 dark:hover:text-accent-400"
      >
        ← Projects
      </Link>
      <h1 className="mt-2 mb-6 text-2xl font-semibold break-all text-ink-900 dark:text-paper-50">
        {data.repo.name}
      </h1>
      {data.tree.length === 0 ? (
        <p className="text-sm text-ink-400 dark:text-paper-300">No pages yet.</p>
      ) : (
        <div className="rounded-xl border border-cream-200 bg-white p-3 shadow-sm dark:border-charcoal-800 dark:bg-charcoal-900">
          {data.tree.map((node) => (
            <TreeNode key={node.id} node={node} />
          ))}
        </div>
      )}
    </div>
  )
}
