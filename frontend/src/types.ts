export type Language = 'fr' | 'en'
export type TranslationLanguage = Language | 'francanglais' | 'pidgin'
export type DatasetLanguage = 'francanglais' | 'pidgin' | 'mixed' | 'unspecified'
export type ReviewStatus = 'unreviewed' | 'approved'
export type AnswerOrigin = 'dataset' | 'ai_with_dataset' | 'ai'
export type Tone = 'everyday' | 'polite' | 'street'
export type Page = 'translator' | 'assistant' | 'collection' | 'imports' | 'coursework'

export interface IncomingText {
  id: number
  text: string
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
}

export interface Metadata {
  categories: string[]
  entry_types: string[]
  dataset_languages: string[]
  lexical_categories: string[]
}

export const defaultMetadata: Metadata = {
  categories: [
    'Taxi / Commuting',
    'Internet Connectivity',
    'Electricity Supply',
    'Market Bargaining',
    'Rainy Season',
    'Fuel Scarcity',
    'Roadside Business',
    'Bendskin Communication',
    'Security Checkpoint',
    'Campus Life',
    'Other',
  ],
  entry_types: ['Word', 'Phrase', 'Sentence'],
  dataset_languages: ['francanglais', 'pidgin', 'mixed', 'unspecified'],
  lexical_categories: [],
}

export const MAX_TEXT = 4000
