export interface Project {
  group_members: string[]
  grammar: string
  manual_transcription_confirmed: boolean
  grammar_rationale: string
  discussion: string
  collection_method: string
  limitations: string
}

export interface Requirement {
  id: string
  title: string
  marks: number
  status: 'ready' | 'needs_input' | 'review'
  detail: string
  section: string
}

export interface Screenshot {
  id: string
  name: string
  url: string
}

export interface CourseworkState {
  project: Project
  brief: {
    title: string
    course: string
    due: string
    group_size: number
    statement_target: number[]
    report_pages: number[]
    presentation_minutes: number
    per_student_minutes: number
  }
  requirements: Requirement[]
  lexical_spec: {
    token_pattern: string
    regex_rules: { category: string; pattern: string }[]
    verb_phrases: string[]
    slang_phrases: string[]
    classification_order: string[]
    limitations: string[]
  }
  stats: {
    total: number
    sentences: number
    topic_counts: Record<string, number>
    missing_topics: string[]
  }
  screenshots: Screenshot[]
}

export type Rules = Record<string, string[][]>

export interface GrammarAnalysis {
  original: Rules
  transformed: Rules
  start_symbol: string
  terminals: string[]
  nonterminals: string[]
  steps: { operation: string; before: Rules; after: Rules; description: string }[]
  first: Record<string, string[]>
  follow: Record<string, string[]>
  table: Record<string, Record<string, string[]>>
  conflicts: { nonterminal: string; terminal: string; productions: string[][] }[]
  is_ll1: boolean
  warnings: string[]
}

export interface LexicalToken {
  text: string
  category: string
}

export interface TokenCount {
  token: string
  count: number
}

export interface LexicalReport {
  statements: {
    id: string
    text: string
    category: string
    tokens: LexicalToken[]
    code_mixed_spans: string[]
    verb_phrases: string[]
    slang_expressions: string[]
  }[]
  frequencies: TokenCount[]
  category_counts: Record<string, number>
  variations: { normalized: string; forms: { text: string; count: number }[] }[]
  unknown_tokens: TokenCount[]
  total_tokens: number
}

export interface ParseResult {
  accepted: boolean
  error: string | null
  consumed: number
  trace: { stack: string[]; remaining: string[]; action: string }[]
}

export interface CorpusTest extends ParseResult {
  id: string
  text: string
}

export interface CourseworkAnalysis {
  grammar: GrammarAnalysis
  lexical: LexicalReport
  tests: CorpusTest[]
  summary: { accepted: number; rejected: number; total: number }
  requirements: Requirement[]
}

export interface ManualParse {
  tokens: LexicalToken[]
  parse: ParseResult
}
