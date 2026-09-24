import type { Analysis, Ownership } from './types'
import type { CorpusTest, CourseworkState, GrammarAnalysis, LexicalReport, LexicalStatistics, ParseResult, TokenCount } from './courseworkTypes'

export interface AnalyzerState {
  grammar: string
  grammar_ownership: Ownership
  lexical_spec: CourseworkState['lexical_spec']
  stats: { total: number; sentences: number }
}

export interface AnalyzerResult {
  text: string
  lexical: Analysis & {
    slang_expressions: string[]
    statistics: LexicalStatistics
  }
  grammar: GrammarAnalysis
  parse: ParseResult
  approval: VocabularyApproval
  corpus: {
    lexical: LexicalReport
    tests: CorpusTest[]
    summary: { accepted: number; rejected: number; total: number }
  }
}

export interface VocabularyApproval {
  basis: 'no_unknown_tokens'
  accepted: boolean
  unknown_count: number
}

export interface RecordedTest extends Omit<AnalyzerResult, 'corpus'> {
  id: string
  ownership: Ownership
  created_at: string
  grammar_source: string
  metadata: {
    topics: string[]
    languages: string[]
    matching_entries: number
  }
}

export interface RecordedTestSummary {
  id: string
  ownership: Ownership
  created_at: string
  text: string
  accepted: boolean
  token_count: number
  error: string | null
  unknown_count: number
  grammar_accepted: boolean
  grammar_error: string | null
}

export interface TestTotals {
  total: number
  accepted: number
  rejected: number
  acceptance_rate: number | null
}

export interface TestReport {
  approval_basis: 'no_unknown_tokens'
  summary: TestTotals
  grammar_summary: TestTotals
  statistics: LexicalStatistics & {
    raw_frequencies: TokenCount[]
    normalized_frequencies: TokenCount[]
  }
  unknown_review: { token: string; count: number; tests: number; forms: string[] }[]
  topic_counts: Record<string, number>
  language_counts: Record<string, number>
  tests: RecordedTestSummary[]
  offset: number
  limit: number
}
