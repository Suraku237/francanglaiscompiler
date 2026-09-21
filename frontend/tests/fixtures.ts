import type { CourseworkAnalysis, CourseworkState, ManualParse, Project } from '../src/courseworkTypes'
import type { ImportPreview, ImportSuggestions } from '../src/importTypes'
import type { ChatReply, Dataset, DatasetEntry, Health, Metadata, Translation } from '../src/types'

// All records are synthetic test data. They never come from, or write to, the research CSV.
export const metadata: Metadata = {
  categories: ['Campus Life', 'Other'],
  entry_types: ['Word', 'Phrase', 'Sentence'],
  dataset_languages: ['francanglais', 'pidgin', 'mixed', 'unspecified'],
  lexical_categories: ['NOUN', 'VERB', 'SLANG'],
}

export function health(aiConfigured = true): Health {
  return { status: 'ok', ai_configured: aiConfigured, model: 'fixture-model' }
}

export function chatReply(overrides: Partial<ChatReply> = {}): ChatReply {
  return { reply: 'Synthetic assistant reply.', model: 'fixture-model', origin: 'ai', evidence: [], ...overrides }
}

export function entry(overrides: Partial<DatasetEntry> = {}): DatasetEntry {
  return {
    id: 'fixture-record-1',
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

export function translation(overrides: Partial<Translation> = {}): Translation {
  const record = entry()
  return {
    translation: record.text,
    explanation: 'A synthetic local match for testing.',
    vocabulary: [],
    note: '',
    source_language: 'fr',
    target_language: 'francanglais',
    origin: 'dataset',
    evidence: [{
      id: record.id,
      text: record.text,
      language: record.language,
      french_gloss: record.french_gloss,
      english_gloss: record.english_gloss,
      match_type: 'exact',
      source: 'dataset',
      source_document: '',
      source_line: null,
      aliases: [],
    }],
    coverage: { matched_terms: ['Sens de test'], unmatched_terms: [], warnings: [] },
    model: 'local-dataset',
    analysis: { tokens: [], code_mixed_spans: [], verb_phrases: [] },
    ...overrides,
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

export function importSuggestions(): ImportSuggestions {
  return {
    drafts: [{
      text: 'AI fixture candidate',
      entry_type: 'Word',
      language: 'pidgin',
      french_gloss: 'Proposition de test',
      english_gloss: 'Suggested test meaning',
      lexical_category: 'NOUN',
      review_status: 'unreviewed',
    }],
    warnings: ['AI glosses need human review.'],
    model: 'fixture-model',
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
    stats: { total: 0, sentences: 0, topic_counts: {}, missing_topics: ['Campus Life'] },
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
