import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TestStatistics } from '../../src/TestStatistics'
import { retainedTestReport, testReport } from '../fixtures'
import type { TestReport } from '../../src/analyzerTypes'

function setup(report = retainedTestReport()) {
  const callbacks = { onInspect: vi.fn(), onRefresh: vi.fn(), onPage: vi.fn() }
  render(<TestStatistics report={report} busy={false} {...callbacks} />)
  return { ...callbacks, user: userEvent.setup() }
}

function rows(label: string) {
  return within(screen.getByRole('region', { name: label })).getAllByRole('row').slice(1).map((row) => row.textContent)
}

describe('all recorded test statistics', () => {
  it('shows exact totals, complete raw/normalized/category frequencies and unknown test counts', () => {
    setup()
    expect(screen.getByRole('group', { name: 'Tests recorded' })).toHaveTextContent('3')
    expect(screen.getByRole('group', { name: 'Accepted' })).toHaveTextContent('2')
    expect(screen.getByRole('group', { name: 'Rejected' })).toHaveTextContent('1')
    expect(screen.getByRole('group', { name: 'Acceptance rate' })).toHaveTextContent('66.7%')
    expect(screen.getByRole('group', { name: 'Grammar accepted' })).toHaveTextContent('1')
    expect(screen.getByRole('group', { name: 'Grammar rejected' })).toHaveTextContent('2')
    expect(screen.getByRole('group', { name: 'Grammar acceptance rate' })).toHaveTextContent('33.3%')
    expect(rows('Raw token frequency counts')).toEqual(['veux2', '+2', 'taxi2', 'VEUX1'])
    expect(rows('Normalized token frequency counts')).toEqual(['veux3', '+2', 'taxi2'])
    expect(rows('Grammatical category frequency counts')).toEqual(['VERB3', 'NOUN2', 'UNKNOWN2'])
    expect(rows('Unknown-word review counts')).toEqual(['++21'])
    expect(rows('Recorded topics counts')).toEqual(['Not recorded2', 'Taxi / Commuting1'])
    expect(rows('Declared input languages counts')).toEqual(['Not recorded2', 'francanglais1'])
    expect(screen.getByText(/not detected word origins/)).toBeVisible()
    expect(screen.getByText(/All completed tests by every user/)).toBeVisible()
    expect(screen.getAllByText(/Creator: Test user/)).toHaveLength(2)
    expect(screen.getByText(/Creator: Second user/)).toBeVisible()
    expect(screen.queryByRole('button', { name: /Edit|Delete/ })).not.toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('retains spelling variants and exact saved inputs without auto-inspecting or re-running', async () => {
    const { user, onInspect, onRefresh } = setup()
    await user.click(screen.getByText('Observed spelling variations - 1 groups'))
    expect(rows('Saved-test spelling variations')).toEqual(['veuxveux (2) / VEUX (1)'])
    const list = screen.getByRole('list')
    expect(within(list).getAllByRole('listitem')[2]?.querySelector('.test-record-source')?.textContent).toBe('  veux VEUX + +\t')
    expect(onInspect).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Inspect test 1' }))
    expect(onInspect).toHaveBeenCalledExactlyOnceWith(retainedTestReport().tests[2]?.id)
    await user.click(screen.getByRole('button', { name: 'Refresh saved tests' }))
    expect(onRefresh).toHaveBeenCalledOnce()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('paginates displayed tests without using page size as the overall statistics total', async () => {
    const base = retainedTestReport()
    const template = base.tests[0]
    if (!template) throw new Error('The synthetic report must contain a sample.')
    const report: TestReport = {
      ...base, summary: { total: 26, accepted: 25, rejected: 1, acceptance_rate: 2500 / 26 },
      tests: Array.from({ length: 25 }, (_, index) => ({ ...template, id: `test-${index}` })),
    }
    const { user, onPage } = setup(report)
    expect(screen.getByRole('group', { name: 'Tests recorded' })).toHaveTextContent('26')
    expect(screen.getByText('1-25 of 26 tests / statistics include all 26')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Previous tests' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Next tests' }))
    expect(onPage).toHaveBeenCalledExactlyOnceWith(25)
  })

  it('does not pretend zero tests have a zero-percent acceptance rate', () => {
    setup(testReport())
    expect(screen.getByRole('group', { name: 'Tests recorded' })).toHaveTextContent('0')
    expect(screen.getByRole('group', { name: 'Acceptance rate' })).toHaveTextContent('Not available')
    expect(screen.queryByText('0%')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'No saved tests yet' })).toBeVisible()
    expect(screen.getByText(/No one has recorded a test in the shared workspace yet/)).toBeVisible()
  })

  it('shows an explicit empty unknown review and keeps final-page controls bounded', () => {
    const report = retainedTestReport()
    setup({ ...report, unknown_review: [], offset: 2, limit: 2, tests: report.tests.slice(2) })
    expect(screen.getByText('No unknown tokens in the saved tests.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Previous tests' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Next tests' })).toBeDisabled()
  })
})
