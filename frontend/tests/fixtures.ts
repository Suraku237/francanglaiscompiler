import type { CourseworkAnalysis, CourseworkState, LexicalStatistics, ManualParse, Project } from '../src/courseworkTypes'
import type { AnalyzerResult, AnalyzerState, RecordedTest, TestReport, VocabularyApproval } from '../src/analyzerTypes'
import type { ImportPreview } from '../src/importTypes'
import { defaultMetadata } from '../src/types'
import type { Dataset, DatasetEntry, Health, Metadata, Ownership } from '../src/types'
import type { PublicSessionInfo } from '../src/PublicSession'

// All records are synthetic test data. They never come from, or write to, the research CSV.
export const metadata: Metadata = {
  categories: defaultMetadata.categories,
  entry_types: ['Word', 'Phrase', 'Sentence'],
  dataset_languages: ['francanglais', 'pidgin', 'mixed', 'unspecified'],
  lexical_categories: ['NOUN', 'VERB', 'SLANG'],
}

export function health(): Health {
  return { status: 'ok', mode: 'compiler' }
}

export function ownership(overrides: Partial<Ownership> = {}): Ownership {
  return { owner_id: null, owner_name: '', can_edit: false, ...overrides }
}

export function publicSession(): PublicSessionInfo {
  return {
    access_mode: 'public_read_only', csrf_token: 'test-csrf',
    capabilities: { analyze: true, save_tests: true, edit_collection: false, edit_grammar: false, edit_recordings: false },
  }
}

export function entry(overrides: Partial<DatasetEntry> = {}): DatasetEntry {
  return {
    id: 'fixture-record-1',
    ownership: ownership(),
    text: 'Fixture expression',
    entry_type: 'Sentence',
    language: 'francanglais',
    review_status: 'approved',
    lexical_category: '',
    french_gloss: 'Sens de test',
    english_gloss: 'Test meaning',
    category: 'Campus Life',
    source_location: '',
    notes: 'Synthetic automated-test record, not fieldwork.',
    audio_filename: '',
    contributor: '',
    timestamp: '2026-01-01T12:00:00Z',
    ...overrides,
  }
}

export function dataset(entries = [entry()]): Dataset {
  return {
    entries,
    total: entries.length,
    by_category: Object.fromEntries(metadata.categories.map((category) => [category, entries.filter((item) => item.category === category).length])),
    by_type: Object.fromEntries(metadata.entry_types.map((type) => [type, entries.filter((item) => item.entry_type === type).length])),
    by_review_status: {
      approved: entries.filter((item) => item.review_status === 'approved').length,
      unreviewed: entries.filter((item) => item.review_status === 'unreviewed').length,
    },
  }
}

export function importPreview(overrides: Partial<ImportPreview> = {}): ImportPreview {
  return {
    filename: 'fixture.txt',
    format: 'txt',
    method: 'local',
    text: 'First fixture passage.\nSecond fixture passage.',
    segments: ['First fixture passage.', 'Second fixture passage.'],
    warnings: ['Synthetic fixture; review before use.'],
    drafts: [{
      text: 'Imported fixture expression',
      entry_type: 'Sentence',
      language: 'pidgin',
      french_gloss: 'Sens importé de test',
      english_gloss: 'Imported test meaning',
      lexical_category: '',
      review_status: 'unreviewed',
    }],
    ...overrides,
  }
}

export function project(overrides: Partial<Project> = {}): Project {
  return {
    group_members: ['', '', ''],
    grammar: 'S -> NOUN',
    manual_transcription_confirmed: false,
    grammar_rationale: '',
    discussion: '',
    collection_method: '',
    limitations: '',
    ...overrides,
  }
}

export function courseworkState(savedProject = project()): CourseworkState {
  return {
    project: savedProject,
    brief: {
      title: 'Synthetic compiler coursework fixture',
      course: 'CS4110',
      due: '',
      group_size: 3,
      statement_target: [100, 150],
      report_pages: [25, 30],
      presentation_minutes: 10,
      per_student_minutes: 3,
    },
    requirements: [{
      id: 'research',
      title: 'Document your own observations',
      marks: 10,
      status: 'needs_input',
      detail: 'Fixture data is not authentic fieldwork.',
      section: 'Research',
    }],
    lexical_spec: {
      token_pattern: '\\w+',
      regex_rules: [{ category: 'NUMBER', pattern: '\\d+' }],
      verb_phrases: [],
      slang_phrases: [],
      classification_order: ['Exact lexicon match', 'Regex rules', 'Unknown token'],
      limitations: ['Synthetic test specification.'],
    },
    stats: { total: 0, sentences: 0, topic_counts: {}, missing_topics: defaultMetadata.categories.filter((topic) => topic !== 'Other') },
    screenshots: [],
  }
}

export function courseworkAnalysis(): CourseworkAnalysis {
  return {
    grammar: {
      original: { S: [['NOUN']] },
      transformed: { S: [['NOUN']] },
      start_symbol: 'S',
      terminals: ['NOUN'],
      nonterminals: ['S'],
      steps: [],
      first: { S: ['NOUN'] },
      follow: { S: ['$'] },
      table: { S: { NOUN: ['NOUN'] } },
      conflicts: [],
      is_ll1: true,
      warnings: [],
    },
    lexical: {
      statements: [],
      frequencies: [],
      category_counts: {},
      variations: [],
      unknown_tokens: [],
      total_tokens: 0,
    },
    tests: [],
    summary: { accepted: 0, rejected: 0, total: 0 },
    requirements: [],
  }
}

export function manualParse(): ManualParse {
  return {
    tokens: [],
    parse: {
      accepted: true,
      error: null,
      consumed: 0,
      trace: [{ stack: ['$', 'S'], remaining: ['$'], action: 'S → epsilon' }],
    },
  }
}

export function analyzerState(grammar = 'S -> NOUN', grammarOwnership = ownership()): AnalyzerState {
  return { grammar, grammar_ownership: grammarOwnership, lexical_spec: courseworkState().lexical_spec, stats: { total: 0, sentences: 0 } }
}

export function lexicalStatistics(overrides: Partial<LexicalStatistics> = {}): LexicalStatistics {
  return { frequencies: [], category_counts: {}, variations: [], unknown_tokens: [], total_tokens: 0, ...overrides }
}

export function vocabularyApproval(unknownCount = 0): VocabularyApproval {
  return { basis: 'no_unknown_tokens', accepted: unknownCount === 0, unknown_count: unknownCount }
}

export function analyzerResult(overrides: Partial<AnalyzerResult> = {}): AnalyzerResult {
  const corpus = courseworkAnalysis()
  return {
    text: 'Mbom',
    approval: overrides.approval ?? vocabularyApproval(overrides.lexical?.tokens.filter((token) => token.category === 'UNKNOWN').length ?? 0),
    lexical: {
      tokens: [{ text: 'Mbom', category: 'NOUN' }], code_mixed_spans: [], verb_phrases: [], slang_expressions: [],
      statistics: lexicalStatistics({ frequencies: [{ token: 'mbom', count: 1 }], category_counts: { NOUN: 1 }, total_tokens: 1 }),
    },
    grammar: corpus.grammar,
    parse: {
      accepted: true, error: null, consumed: 1,
      trace: [
        { stack: ['$', 'S'], remaining: ['NOUN', '$'], action: 'S -> NOUN' },
        { stack: ['$', 'NOUN'], remaining: ['NOUN', '$'], action: 'match NOUN' },
        { stack: ['$'], remaining: ['$'], action: 'accept' },
      ],
    },
    corpus: { lexical: corpus.lexical, tests: corpus.tests, summary: corpus.summary },
    ...overrides,
  }
}

export function tokenAnalysisResult(): AnalyzerResult {
  const tokens = [
    { text: 'veux', category: 'VERB' }, { text: 'VEUX', category: 'VERB' },
    { text: '+', category: 'UNKNOWN' }, { text: '+', category: 'UNKNOWN' },
  ]
  const corpusStatistics = lexicalStatistics({
    frequencies: [{ token: 'taxi', count: 2 }], category_counts: { NOUN: 2 }, total_tokens: 2,
  })
  const result = analyzerResult({
    text: '  veux VEUX + +\t',
    lexical: {
      tokens, code_mixed_spans: [], verb_phrases: [], slang_expressions: [],
      statistics: lexicalStatistics({
        frequencies: [{ token: 'veux', count: 2 }, { token: '+', count: 2 }],
        category_counts: { VERB: 2, UNKNOWN: 2 },
        variations: [{ normalized: 'veux', forms: [{ text: 'veux', count: 1 }, { text: 'VEUX', count: 1 }] }],
        unknown_tokens: [{ token: '+', count: 2 }], total_tokens: 4,
      }),
    },
    parse: {
      accepted: false, error: 'No rule for S with lookahead VERB.', consumed: 0,
      trace: [{ stack: ['$', 'S'], remaining: ['VERB', 'VERB', 'UNKNOWN', 'UNKNOWN', '$'], action: 'No rule for S with lookahead VERB.' }],
    },
  })
  return {
    ...result,
    corpus: {
      lexical: {
        ...corpusStatistics,
        statements: [{
          id: 'frequency-fixture', text: '  taxi taxi\n', category: 'Other',
          tokens: [{ text: 'taxi', category: 'NOUN' }, { text: 'taxi', category: 'NOUN' }],
          code_mixed_spans: [], verb_phrases: [], slang_expressions: [],
        }],
      },
      tests: [{
        id: 'frequency-fixture', text: '  taxi taxi\n', accepted: false,
        consumed: 1, error: 'Unexpected trailing token NOUN.',
        trace: [{ stack: ['$'], remaining: ['NOUN', '$'], action: 'Unexpected trailing token NOUN.' }],
      }],
      summary: { accepted: 0, rejected: 1, total: 1 },
    },
  }

}

export function recordedTest(overrides: Partial<RecordedTest> = {}): RecordedTest {
  const result = analyzerResult()
  return {
    id: '4fbc8606-4d79-44f9-9d87-87c0e386ebc0',
    ownership: ownership(),
    created_at: '2026-09-23T12:00:00Z',
    grammar_source: 'S -> NOUN',
    approval: overrides.approval ?? vocabularyApproval(overrides.lexical?.tokens.filter((token) => token.category === 'UNKNOWN').length ?? 0),
    metadata: { topics: [], languages: [], matching_entries: 0 },
    text: result.text, lexical: result.lexical, grammar: result.grammar, parse: result.parse,
    ...overrides,
  }
}

export function testReport(overrides: Partial<TestReport> = {}): TestReport {
  return {
    approval_basis: 'no_unknown_tokens',
    summary: { total: 0, accepted: 0, rejected: 0, acceptance_rate: null },
    grammar_summary: overrides.grammar_summary ?? overrides.summary ?? { total: 0, accepted: 0, rejected: 0, acceptance_rate: null },
    statistics: { ...lexicalStatistics(), raw_frequencies: [], normalized_frequencies: [] },
    unknown_review: [], topic_counts: {}, language_counts: {}, tests: [], offset: 0, limit: 25,
    ...overrides,
  }
}

export function retainedTestReport(): TestReport {
  const frequencies = [{ token: 'veux', count: 3 }, { token: '+', count: 2 }, { token: 'taxi', count: 2 }]
  return testReport({
    summary: { total: 3, accepted: 2, rejected: 1, acceptance_rate: 200 / 3 },
    grammar_summary: { total: 3, accepted: 1, rejected: 2, acceptance_rate: 100 / 3 },
    statistics: {
      frequencies, normalized_frequencies: frequencies,
      raw_frequencies: [{ token: 'veux', count: 2 }, { token: '+', count: 2 }, { token: 'taxi', count: 2 }, { token: 'VEUX', count: 1 }],
      category_counts: { VERB: 3, UNKNOWN: 2, NOUN: 2 }, total_tokens: 7,
      unknown_tokens: [{ token: '+', count: 2 }],
      variations: [{ normalized: 'veux', forms: [{ text: 'veux', count: 2 }, { text: 'VEUX', count: 1 }] }],
    },
    unknown_review: [{ token: '+', count: 2, tests: 1, forms: ['+'] }],
    topic_counts: { 'Not recorded': 2, 'Taxi / Commuting': 1 },
    language_counts: { 'Not recorded': 2, francanglais: 1 },
    tests: [
      { id: '01270d9d-aa38-452d-9f51-546514425bca', ownership: ownership(), created_at: '2026-09-23T12:02:00Z', text: 'veux', accepted: true, token_count: 1, error: null, unknown_count: 0, grammar_accepted: true, grammar_error: null },
      { id: '2518c8e9-fd48-4452-bce3-6a7a039b2190', ownership: ownership({ owner_id: 'second-user', owner_name: 'Second user', can_edit: false }), created_at: '2026-09-23T12:01:00Z', text: '  taxi taxi\n', accepted: true, token_count: 2, error: null, unknown_count: 0, grammar_accepted: false, grammar_error: 'Unexpected trailing token NOUN.' },
      { id: recordedTest().id, ownership: ownership(), created_at: '2026-09-23T12:00:00Z', text: '  veux VEUX + +\t', accepted: false, token_count: 4, error: '2 UNKNOWN tokens.', unknown_count: 2, grammar_accepted: false, grammar_error: 'No rule for S with lookahead VERB.' },
    ],
  })
}
