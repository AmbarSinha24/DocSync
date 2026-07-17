import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TreeNode from '../TreeNode'

describe('TreeNode', () => {
  it('renders a node with its path and sync status', () => {
    const node = {
      id: 1,
      path: 'src/services',
      title: 'Services',
      sync_status: 'synced',
      is_promoted: false,
      children: [],
    }
    render(<TreeNode node={node} />)

    expect(screen.getByText('Services')).toBeInTheDocument()
    expect(screen.getByText('src/services')).toBeInTheDocument()
    expect(screen.getByText('synced')).toBeInTheDocument()
  })

  it('renders nested children recursively', () => {
    const node = {
      id: 1,
      path: 'src/services',
      title: 'Services',
      sync_status: 'synced',
      is_promoted: false,
      children: [
        {
          id: 2,
          path: 'src/services/auth',
          title: 'Auth Service',
          sync_status: 'pending',
          is_promoted: false,
          children: [],
        },
      ],
    }
    render(<TreeNode node={node} />)

    expect(screen.getByText('Auth Service')).toBeInTheDocument()
    expect(screen.getByText('pending')).toBeInTheDocument()
  })

  it('shows a promoted badge when the section has its own page', () => {
    const node = {
      id: 1,
      path: 'src/services/auth',
      title: 'Auth Service',
      sync_status: 'synced',
      is_promoted: true,
      children: [],
    }
    render(<TreeNode node={node} />)

    expect(screen.getByText('promoted')).toBeInTheDocument()
  })
})
