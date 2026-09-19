import type { EditableEntry } from './types'

export interface ImportDraft {
  text: string
  entry_type: 'Word' | 'Phrase' | 'Sentence'
  language: 'francanglais' | 'pidgin' | 'mixed' | 'unspecified'
  french_gloss: string
  english_gloss: string
  lexical_category: string
  review_status: 'unreviewed'
}

export interface ImportPreview {
  filename: string
  format: string
  method: 'local' | 'gemini'
  text: string
  segments: string[]
  warnings: string[]
  drafts: ImportDraft[]
}

export interface ImportSuggestions {
  drafts: ImportDraft[]
  warnings: string[]
  model: string
}

export interface ImportReview {
  key: string
  fields: Partial<EditableEntry>
}

export const IMPORT_ACCEPT = '.txt,.md,.csv,.json,.pdf,.docx,.png,.jpg,.jpeg,.webp,.mp3,.wav,.m4a,.ogg,.flac,.mp4,.webm,.mov'
export const MAX_IMPORT_BYTES = 12 * 1024 * 1024
