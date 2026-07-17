import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ApprovalQueue from '../ApprovalQueue'
import { api } from '../../api'

vi.mock('../../api', () => ({
  api: {
    listApprovals: vi.fn(),
    getApproval: vi.fn(),
  },
}))

describe('ApprovalQueue grouping', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('splits records into structural vs content-edit groups', async () => {
    api.listApprovals.mockResolvedValue([
      { id: 1, path: 'src/services', change_type: 'create', proposed_name: 'Services' },
      { id: 2, path: 'src/services/billing', change_type: 'content_edit', proposed_name: null },
      { id: 3, path: 'src/old', change_type: 'delete', proposed_name: null },
    ])
    api.getApproval.mockResolvedValue({
      id: 1,
      path: 'src/services',
      change_type: 'create',
      proposed_name: 'Services',
      pr_context: null,
      current_content: null,
      proposed_content: '<p>x</p>',
    })

    render(<ApprovalQueue />)

    expect(await screen.findByText('Structural Changes')).toBeInTheDocument()
    expect(screen.getByText('(2)')).toBeInTheDocument()
    expect(screen.getByText('Content Edits')).toBeInTheDocument()
    expect(screen.getByText('(1)')).toBeInTheDocument()
  })

  it('shows an empty-state message when the queue is empty', async () => {
    api.listApprovals.mockResolvedValue([])
    render(<ApprovalQueue />)

    expect(await screen.findByText(/Nothing pending/)).toBeInTheDocument()
  })
})
