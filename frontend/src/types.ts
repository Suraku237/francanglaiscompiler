export type Language = 'fr' | 'en'
export type TranslationLanguage = Language | 'francanglais' | 'pidgin'
export type DatasetLanguage = 'francanglais' | 'pidgin' | 'mixed' | 'unspecified'
export type ReviewStatus = 'unreviewed' | 'approved'
export type AnswerOrigin = 'dataset' | 'dictionary' | 'examples' | 'local_sources' | 'ai_with_dataset' | 'ai_with_sources' | 'ai'
export type Tone = 'everyday' | 'polite' | 'street'
export type Page = 'translator' | 'assistant' | 'dictionary' | 'collection' | 'imports'

export function isLocalOrigin(origin?: AnswerOrigin): boolean {
  return origin === 'dataset' || origin === 'dictionary' || origin === 'examples' || origin === 'local_sources'
}

export interface IncomingText {
  id: number
  text: string
  source?: TranslationLanguage
  target?: TranslationLanguage
  kind?: 'dictionary' | 'examples'
}

export const translationLanguages: TranslationLanguage[] = ['fr', 'en', 'francanglais', 'pidgin']
export const languageLabels: Record<TranslationLanguage | DatasetLanguage, string> = {
  fr: 'French',
  en: 'English',
  francanglais: 'Cameroon Francanglais',
  pidgin: 'Cameroon Pidgin',
  mixed: 'Mixed languages',
  unspecified: 'Unspecified',
}

export interface DatasetEvidence {
  id: string
  text: string
  language: DatasetLanguage
  french_gloss: string
  english_gloss: string
  match_type: 'exact' | 'phrase' | 'token'
  source: 'dataset' | 'dictionary' | 'examples'
  source_document: string
  source_line: number | null
  aliases: string[]
}

export interface DictionaryEntry {
  id: string
  text: string
  aliases: string[]
  language: 'francanglais'
  english_gloss: string
  origin: string
  topic: string
  source_document: string
  source_line: number
}

export interface DictionaryResult {
  entries: DictionaryEntry[]
  total: number
  matched: number
  offset: number
  limit: number
  sources: string[]
}

export interface PracticeEntry {
  id: string
  text: string
  language: 'francanglais'
  french_gloss: string
  english_gloss: string
  topic: string
  notes: string
  source_document: string
  source_line: number
  constructed: true
}

export interface PracticeResult {
  entries: PracticeEntry[]
  total: number
  matched: number
  offset: number
  limit: number
  sources: string[]
}

export interface DatasetCoverage {
  matched_terms: string[]
  unmatched_terms: string[]
  warnings: string[]
}

export interface Health {
  status: 'ok'
  ai_configured: boolean
  model: string
}

export interface Analysis {
  tokens: { text: string; category: string }[]
  code_mixed_spans: string[]
  verb_phrases: string[]
}

export interface Translation {
  translation: string
  explanation: string
  vocabulary: { term: string; meaning: string }[]
  note: string
  source_language: TranslationLanguage
  target_language: TranslationLanguage
  origin: AnswerOrigin
  evidence: DatasetEvidence[]
  coverage: DatasetCoverage
  model: string
  analysis: Analysis
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatReply {
  reply: string
  model: string
  origin?: AnswerOrigin
  evidence?: DatasetEvidence[]
}

export interface DatasetEntry {
  id: string
  text: string
  entry_type: string
  language: DatasetLanguage
  review_status: ReviewStatus
  lexical_category: string
  french_gloss: string
  english_gloss: string
  category: string
  source_location: string
  notes: string
  audio_filename: string
  contributor: string
  timestamp: string
}

export type EditableEntry = Pick<
  DatasetEntry,
  | 'text'
  | 'entry_type'
  | 'language'
  | 'review_status'
  | 'lexical_category'
  | 'french_gloss'
  | 'english_gloss'
  | 'category'
  | 'source_location'
  | 'notes'
  | 'contributor'
>

export interface Dataset {
  entries: DatasetEntry[]
  total: number
  by_category: Record<string, number>
  by_type: Record<string, number>
  by_review_status?: Record<ReviewStatus, number>
}

export interface Metadata {
  categories: string[]
  entry_types: string[]
  dataset_languages: string[]
  lexical_categories: string[]
}

export const defaultMetadata: Metadata = {
  categories: [
    'Customer Service',
    'Sales',
    'Marketing',
    'Operations',
    'Logistics',
    'Finance',
    'Human Resources',
    'Product & Technical',
    'Legal & Compliance',
    'General Communication',
    'Other',
  ],
  entry_types: ['Word', 'Phrase', 'Sentence'],
  dataset_languages: ['francanglais', 'pidgin', 'mixed', 'unspecified'],
  lexical_categories: [],
}

export const MAX_TEXT = 4000
