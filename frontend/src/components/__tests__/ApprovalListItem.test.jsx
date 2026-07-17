import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ApprovalListItem from '../ApprovalListItem'

const approval = {
  id: 42,
  path: 'src/services/billing',
  change_type: 'content_edit',
  proposed_name: null,
}

describe('ApprovalListItem', () => {
  it('renders the path and change type', () => {
    render(<ApprovalListItem approval={approval} isSelected={false} onSelect={() => {}} />)
    expect(screen.getByText('src/services/billing')).toBeInTheDocument()
    expect(screen.getByText('content_edit')).toBeInTheDocument()
  })

  it('prefers the proposed name over change_type when present', () => {
    render(
      <ApprovalListItem
        approval={{ ...approval, proposed_name: 'Billing Service' }}
        isSelected={false}
        onSelect={() => {}}
      />
    )
    expect(screen.getByText('Billing Service')).toBeInTheDocument()
  })

  it('calls onSelect with the approval id when clicked', async () => {
    const onSelect = vi.fn()
    render(<ApprovalListItem approval={approval} isSelected={false} onSelect={onSelect} />)

    await userEvent.click(screen.getByRole('button'))

    expect(onSelect).toHaveBeenCalledWith(42)
  })
})
