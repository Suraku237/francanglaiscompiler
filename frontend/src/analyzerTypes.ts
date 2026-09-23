import type { Analysis } from './types'
import type { CorpusTest, CourseworkState, GrammarAnalysis, LexicalReport, LexicalStatistics, ParseResult, TokenCount } from './courseworkTypes'

export interface AnalyzerState {
  grammar: string
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
  corpus: {
    lexical: LexicalReport
    tests: CorpusTest[]
    summary: { accepted: number; rejected: number; total: number }
  }
}

export interface RecordedTest extends Omit<AnalyzerResult, 'corpus'> {
  id: string
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
  created_at: string
  text: string
  accepted: boolean
  token_count: number
  error: string | null
}

export interface TestReport {
  summary: {
    total: number
    accepted: number
    rejected: number
    acceptance_rate: number | null
  }
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
