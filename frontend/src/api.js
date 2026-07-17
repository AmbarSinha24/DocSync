const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  listRepos: () => request('/repos'),
  getRepoTree: (repoId) => request(`/repos/${repoId}/tree`),

  listApprovals: (status = 'pending') => request(`/approvals?status=${status}`),
  getApproval: (id) => request(`/approvals/${id}`),
  editApproval: (id, body) =>
    request(`/approvals/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  approve: (id, actor) =>
    request(`/approvals/${id}/approve`, { method: 'POST', body: JSON.stringify({ actor }) }),
  reject: (id, actor) =>
    request(`/approvals/${id}/reject`, { method: 'POST', body: JSON.stringify({ actor }) }),
  regenerate: (id, actor, feedback) =>
    request(`/approvals/${id}/regenerate`, {
      method: 'POST',
      body: JSON.stringify({ actor, feedback }),
    }),
}
