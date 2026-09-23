import type { Analysis } from './types'
import type { CorpusTest, CourseworkState, GrammarAnalysis, LexicalReport, LexicalStatistics, ParseResult } from './courseworkTypes'

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
