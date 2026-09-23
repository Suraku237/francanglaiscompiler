import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Analysis } from '../../src/Analysis'
import type { RecordedTest } from '../../src/analyzerTypes'
import { analyzerState, recordedTest, retainedTestReport, testReport, tokenAnalysisResult } from '../fixtures'

function renderAnalysis(result: RecordedTest | null = recordedTest()) {
  const actions = { onUseText: vi.fn(), onCancel: vi.fn(), onRefresh: vi.fn(), onPage: vi.fn(), onInspect: vi.fn(), onRetryInspect: vi.fn() }
  const props = {
    result, report: result ? retainedTestReport() : testReport(), lexicalSpec: analyzerState().lexical_spec,
    analyzing: false, loading: false, loadError: '', inspecting: false, inspectError: '', ...actions,
  }
  const view = render(<Analysis {...props} />)
  return { ...view, props, user: userEvent.setup(), ...actions }
}

describe('retained test Analysis page', () => {
  it('distinguishes all-test statistics from an inspected test and preserves raw source', async () => {
    const single = tokenAnalysisResult()
    const { user } = renderAnalysis(recordedTest({ text: single.text, lexical: single.lexical, parse: single.parse }))
    const all = within(screen.getByRole('region', { name: 'Test statistics' }))
    expect(all.getByRole('group', { name: 'Tests recorded' })).toHaveTextContent('3')
    expect(all.getByRole('group', { name: 'Acceptance rate' })).toHaveTextContent('66.7%')
    const selected = within(screen.getByRole('region', { name: 'Analyzed sentence or word' }))
    expect(selected.getByLabelText('Analyzed source text').textContent).toBe(single.text)
    expect(selected.getByRole('region', { name: 'Lexical tokens in source order' })).not.toBeVisible()
    await user.click(selected.getByText('Token details for this test'))
    expect(selected.getByText('4 tokens · 2 distinct forms')).toBeVisible()
    expect(selected.getByRole('region', { name: 'Lexical tokens in source order' })).toHaveTextContent('1veuxVERB2VEUXVERB3+UNKNOWN4+UNKNOWN')
    expect(all.getByRole('region', { name: 'Normalized token frequency counts' })).toHaveTextContent('veux3')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('opens saved grammar and parser evidence without recomputing and hands off exact input only on request', async () => {
    const raw = '  Mbom\t\n'
    const { user, onUseText } = renderAnalysis(recordedTest({ text: raw, grammar_source: 'S -> NOUN\nTail -> epsilon' }))
    const selected = within(screen.getByRole('region', { name: 'Analyzed sentence or word' }))
    await user.click(selected.getByText('Parser trace for this input'))
    expect(selected.getByRole('region', { name: 'Table-driven parser step trace' })).toBeVisible()
    await user.click(selected.getByText('Saved grammar, transformations & FIRST/FOLLOW'))
    expect(selected.getByText('S -> NOUN Tail -> epsilon')).toBeVisible()
    expect(selected.getByRole('region', { name: 'Computed FIRST and FOLLOW sets' })).toBeVisible()
    expect(onUseText).not.toHaveBeenCalled()
    await user.click(selected.getByRole('button', { name: 'Use as analyzer input' }))
    expect(onUseText).toHaveBeenCalledExactlyOnceWith(raw)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('shows an honest empty state without fabricating a recoverable earlier run', () => {
    renderAnalysis(null)
    expect(screen.getByRole('heading', { name: 'No saved tests yet' })).toBeVisible()
    expect(screen.getByText(/Earlier runs made before test storage/)).toBeVisible()
    expect(screen.getByRole('group', { name: 'Acceptance rate' })).toHaveTextContent('Not available')
    expect(screen.queryByLabelText('Analyzed source text')).not.toBeInTheDocument()
    expect(screen.queryByText('ACCEPT', { exact: true })).not.toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('shows loading and explicit report/detail recovery instead of stale statistics', async () => {
    const { user, rerender, props, onRefresh, onRetryInspect } = renderAnalysis(null)
    rerender(<Analysis {...props} report={null} loading />)
    expect(screen.getByText('Loading all-test statistics...')).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'No saved tests yet' })).not.toBeInTheDocument()
    rerender(<Analysis {...props} report={null} loadError="Cannot read recorded tests." />)
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Try again' }))
    expect(onRefresh).toHaveBeenCalledOnce()
    rerender(<Analysis {...props} report={null} inspectError="This saved test was not found." />)
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Try again' }))
    expect(onRetryInspect).toHaveBeenCalledOnce()
  })

  it('keeps current lexer rules distinct from immutable saved snapshots', async () => {
    const { user } = renderAnalysis()
    await user.click(screen.getByText('Lexer rules & limitations'))
    expect(screen.getByRole('heading', { name: 'Current token boundary regex' })).toBeVisible()
    expect(screen.getByRole('region', { name: 'Lexer regular expression rules' })).toBeVisible()
    expect(screen.getByText(/original results, not a new analysis/)).toBeVisible()
  })
})
