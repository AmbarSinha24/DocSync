import { test, expect } from '@playwright/test'

// Repeats the real Phase 2 scenario (push -> pending approval -> approve ->
// Confluence write) entirely through the UI -- every action here is a real
// click/type against the actual rendered app, talking to the real backend,
// real DeepSeek, and real Confluence. No direct API calls from this test.
//
// Requires a pending content-edit approval to already exist -- run
// `backend/scripts/seed_pending_approval.py` first.

test('reviewer can open a pending content edit, see the diff, and approve it through the UI', async ({
  page,
}) => {
  await page.goto('/approvals')

  await expect(page.getByText(/Content Edits \(\d+\)/)).toBeVisible()

  const contentEditItem = page.getByText('src/services/billing').first()
  await expect(contentEditItem).toBeVisible()
  await contentEditItem.click()

  // the detail panel loaded with a real diff from real Confluence content
  await expect(page.getByText('Why flagged')).toBeVisible()
  await expect(page.getByText('Current')).toBeVisible()
  await expect(page.getByText('Proposed')).toBeVisible()

  const approveButton = page.getByRole('button', { name: 'Approve' })
  await expect(approveButton).toBeVisible()
  await approveButton.click()

  // approving removes it from the pending queue -- this only happens after
  // a real write_approval() call succeeds against the real Confluence API
  await expect(page.getByText('src/services/billing')).toHaveCount(0, { timeout: 15_000 })
})

test('navigating from the projects index to a project tree shows real synced pages', async ({
  page,
}) => {
  await page.goto('/')

  const project = page.getByText('AmbarSinha24/docsync-fixture')
  await expect(project).toBeVisible()
  await project.click()

  await expect(page).toHaveURL(/\/repos\/\d+/)
  await expect(page.getByText('synced').first()).toBeVisible()
})
