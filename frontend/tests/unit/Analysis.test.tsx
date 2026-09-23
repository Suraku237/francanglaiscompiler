import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Analysis } from '../../src/Analysis'
import type { AnalyzerResult } from '../../src/analyzerTypes'
import { analyzerResult, analyzerState, tokenAnalysisResult } from '../fixtures'

function renderAnalysis(result: AnalyzerResult | null = tokenAnalysisResult()) {
  const onUseText = vi.fn()
  render(<Analysis result={result} lexicalSpec={analyzerState().lexical_spec} analyzing={false} onCancel={vi.fn()} onUseText={onUseText} />)
  return { user: userEvent.setup(), onUseText }
}

describe('separate token Analysis page', () => {
  it('shows every raw token and exact frequency, category, unknown and variation counts', async () => {
    const { user } = renderAnalysis()
    const statement = within(screen.getByRole('region', { name: 'Analyzed sentence' }))
    expect(statement.getByLabelText('Analyzed source text').textContent).toBe('  veux VEUX + +\t')
    const tokens = within(statement.getByRole('region', { name: 'Lexical tokens in source order' }))
    expect(tokens.getAllByRole('row').slice(1).map((row) => row.textContent)).toEqual([
      '1veuxVERB', '2VEUXVERB', '3+UNKNOWN', '4+UNKNOWN',
    ])
    const frequencies = within(statement.getByRole('region', { name: 'Observed token frequencies' }))
    expect(frequencies.getAllByRole('row').slice(1).map((row) => row.textContent)).toEqual(['veux2', '+2'])
    expect(statement.getByText('4 tokens · 2 distinct forms')).toBeVisible()
    const categories = within(statement.getByRole('region', { name: 'Token category frequencies' }))
    expect(categories.getAllByRole('row').slice(1).map((row) => row.textContent)).toEqual(['VERB2', 'UNKNOWN2'])
    await user.click(statement.getByText('Unknown tokens · 1 forms'))
    expect(within(statement.getByRole('region', { name: 'Unknown token frequencies' })).getAllByRole('row')[1]).toHaveTextContent('+2')
    expect(statement.getByRole('region', { name: 'Observed orthographic variation candidates' })).toHaveTextContent('veux (1) · VEUX (1)')
    expect(screen.getByRole('region', { name: 'Saved Collection results' })).not.toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('keeps saved Collection counts separate and hands off raw text only on an explicit click', async () => {
    const { user, onUseText } = renderAnalysis()
    await user.click(screen.getByText('Saved Collection - 1 records'))
    const corpus = within(screen.getByRole('region', { name: 'Saved Collection results' }))
    expect(corpus.getByText('2 tokens · 1 distinct forms')).toBeVisible()
    const frequencies = within(corpus.getByRole('region', { name: 'Observed token frequencies' }))
    expect(frequencies.getAllByRole('row').slice(1).map((row) => row.textContent)).toEqual(['taxi2'])
    const tests = within(corpus.getByRole('region', { name: 'Saved Collection parser results' }))
    await user.click(tests.getByText('taxi taxi'))
    expect(onUseText).not.toHaveBeenCalled()
    await user.click(tests.getByRole('button', { name: 'Use as analyzer input' }))
    expect(onUseText).toHaveBeenCalledExactlyOnceWith('  taxi taxi\n')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('retains rejection reasons, parser steps, grammar details and lexer rules behind disclosures', async () => {
    const { user } = renderAnalysis()
    const statement = within(screen.getByRole('region', { name: 'Analyzed sentence' }))
    expect(statement.getByRole('region', { name: 'Table-driven parser step trace' })).not.toBeVisible()
    await user.click(screen.getByText('Parser trace for this sentence'))
    expect(statement.getByText('REJECT', { exact: true })).toBeVisible()
    expect(statement.getByRole('region', { name: 'Table-driven parser step trace' })).toHaveTextContent('VERB VERB UNKNOWN UNKNOWN $')
    await user.click(screen.getByText('Transformations, FIRST/FOLLOW & LL(1) table'))
    expect(screen.getByRole('region', { name: 'Computed FIRST and FOLLOW sets' })).toBeVisible()
    expect(screen.getByRole('region', { name: 'LL(1) predictive parsing table, scroll horizontally' })).toBeVisible()
    await user.click(screen.getByText('Lexer rules & limitations'))
    expect(screen.getByRole('region', { name: 'Lexer regular expression rules' })).toBeVisible()
  })

  it('does not invent a sentence, statistics or parser verdict before the first run', () => {
    renderAnalysis(null)
    expect(screen.getByRole('heading', { name: 'No completed analysis' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Analyze a sentence' })).toHaveAttribute('href', '#compiler')
    expect(screen.queryByRole('heading', { name: 'Token statistics' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Analyzed sentence' })).not.toBeInTheDocument()
    expect(screen.queryByText('ACCEPT', { exact: true })).not.toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('shows an empty Collection without substituting the manually analyzed sentence', async () => {
    const { user } = renderAnalysis(analyzerResult())
    await user.click(screen.getByText('Saved Collection - 0 records'))
    const corpus = within(screen.getByRole('region', { name: 'Saved Collection results' }))
    expect(corpus.getByText('0 tokens · 0 distinct forms')).toBeVisible()
    expect(corpus.getByText('No token categories were observed.')).toBeVisible()
    expect(corpus.getByText(/No saved records/)).toBeVisible()
    expect(corpus.queryByText('Mbom')).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Analyzed sentence' })).toHaveTextContent('1 tokens · 1 distinct forms')
  })
})
