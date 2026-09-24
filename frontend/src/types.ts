export type Language = 'fr' | 'en'
export type TranslationLanguage = Language | 'francanglais' | 'pidgin'
export type DatasetLanguage = 'francanglais' | 'pidgin' | 'mixed' | 'unspecified'
export type ReviewStatus = 'unreviewed' | 'approved'
export type Page = 'compiler' | 'analysis' | 'dictionary' | 'examples' | 'collection'

export interface IncomingText {
  id: number
  text: string
  kind?: 'dictionary' | 'examples' | 'collection'
}

export interface Ownership {
  owner_id: string | null
  owner_name: string
  can_edit: boolean
}

export const languageLabels: Record<TranslationLanguage | DatasetLanguage, string> = {
  fr: 'French',
  en: 'English',
  francanglais: 'Cameroon Francanglais',
  pidgin: 'Cameroon Pidgin',
  mixed: 'Mixed languages',
  unspecified: 'Unspecified',
}

export interface DictionaryEntry {
  id: string
  text: string
  aliases: string[]
  language: 'francanglais' | 'fr' | 'en'
  part_of_speech?: string
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

export interface Health {
  status: 'ok'
  mode: 'compiler'
}

export interface Analysis {
  tokens: { text: string; category: string }[]
  code_mixed_spans: string[]
  verb_phrases: string[]
}

export interface DatasetEntry {
  id: string
  ownership: Ownership
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
  lexical_categories: ['NUMBER', 'PUNCTUATION', 'SLANG', 'PIDGIN_MARKER', 'NOUN', 'VERB', 'FRENCH_FUNCTION_WORD', 'ENGLISH_FUNCTION_WORD', 'ADJECTIVE', 'ADVERB', 'INTERJECTION', 'PRONOUN', 'PREPOSITION', 'CONJUNCTION', 'DETERMINER', 'PARTICLE', 'AMBIGUOUS', 'ENGLISH_VERB_LIKE', 'FRENCH_VERB_LIKE', 'UNKNOWN'],
}

export const MAX_TEXT = 4000
