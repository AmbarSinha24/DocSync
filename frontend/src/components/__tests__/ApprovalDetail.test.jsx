import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ApprovalDetail from '../ApprovalDetail'
import { api } from '../../api'

vi.mock('../../api', () => ({
  api: {
    getApproval: vi.fn(),
    editApproval: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
    regenerate: vi.fn(),
  },
}))

const baseDetail = {
  id: 7,
  path: 'src/services/billing',
  change_type: 'content_edit',
  proposed_name: null,
  pr_context: '- Add tax to invoice',
  current_content: '<p>old content</p>',
  proposed_content: '<p>new content</p>',
  status: 'pending',
}

describe('ApprovalDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getApproval.mockResolvedValue(baseDetail)
  })

  it('renders the current and proposed content side by side', async () => {
    render(<ApprovalDetail approvalId={7} onResolved={() => {}} />)

    expect(await screen.findByText('<p>old content</p>')).toBeInTheDocument()
    expect(screen.getByText('<p>new content</p>')).toBeInTheDocument()
  })

  it('renders the why-flagged pr_context', async () => {
    render(<ApprovalDetail approvalId={7} onResolved={() => {}} />)
    expect(await screen.findByText('- Add tax to invoice')).toBeInTheDocument()
  })

  it('falls back to a snapshot-mode message when pr_context is absent', async () => {
    api.getApproval.mockResolvedValue({ ...baseDetail, pr_context: null })
    render(<ApprovalDetail approvalId={7} onResolved={() => {}} />)

    expect(
      await screen.findByText('No PR context available (one-time snapshot mode).')
    ).toBeInTheDocument()
  })

  it('calls api.approve with the approval id and actor on Approve click', async () => {
    api.approve.mockResolvedValue({})
    const onResolved = vi.fn()
    render(<ApprovalDetail approvalId={7} onResolved={onResolved} />)

    await screen.findByText('<p>old content</p>')
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(api.approve).toHaveBeenCalledWith(7, 'reviewer'))
    expect(onResolved).toHaveBeenCalled()
  })

  it('calls api.reject with the approval id and actor on Reject click', async () => {
    api.reject.mockResolvedValue({})
    render(<ApprovalDetail approvalId={7} onResolved={() => {}} />)

    await screen.findByText('<p>old content</p>')
    await userEvent.click(screen.getByRole('button', { name: 'Reject' }))

    await waitFor(() => expect(api.reject).toHaveBeenCalledWith(7, 'reviewer'))
  })

  it('shows a feedback box and calls api.regenerate with the typed feedback', async () => {
    api.regenerate.mockResolvedValue({})
    render(<ApprovalDetail approvalId={7} onResolved={() => {}} />)

    await screen.findByText('<p>old content</p>')
    await userEvent.click(screen.getByRole('button', { name: 'Regenerate' }))

    const input = screen.getByPlaceholderText('What should change about this proposal?')
    await userEvent.type(input, 'Make it shorter')
    await userEvent.click(screen.getByRole('button', { name: 'Submit' }))

    await waitFor(() =>
      expect(api.regenerate).toHaveBeenCalledWith(7, 'reviewer', 'Make it shorter')
    )
  })

  it('calls api.editApproval with edited content on save', async () => {
    api.editApproval.mockResolvedValue({})
    render(<ApprovalDetail approvalId={7} onResolved={() => {}} />)

    await screen.findByText('<p>old content</p>')
    await userEvent.click(screen.getByRole('button', { name: 'edit' }))

    const textarea = screen.getByDisplayValue('<p>new content</p>')
    await userEvent.clear(textarea)
    await userEvent.type(textarea, '<p>edited by reviewer</p>')
    await userEvent.click(screen.getByRole('button', { name: 'save' }))

    await waitFor(() =>
      expect(api.editApproval).toHaveBeenCalledWith(7, {
        actor: 'reviewer',
        proposed_content: '<p>edited by reviewer</p>',
      })
    )
  })

  it('does not show a Regenerate button for DELETE records', async () => {
    api.getApproval.mockResolvedValue({ ...baseDetail, change_type: 'delete', proposed_content: null })
    render(<ApprovalDetail approvalId={7} onResolved={() => {}} />)

    await screen.findByText('delete')
    expect(screen.queryByRole('button', { name: 'Regenerate' })).not.toBeInTheDocument()
  })
})
