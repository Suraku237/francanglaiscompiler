import type { EditableEntry } from './types'

export interface ImportDraft {
  text: string
  entry_type: 'Word' | 'Phrase' | 'Sentence'
  language: 'francanglais' | 'pidgin' | 'mixed' | 'unspecified'
  french_gloss: string
  english_gloss: string
  lexical_category: string
  review_status: 'unreviewed'
  category?: string
  source_location?: string
  contributor?: string
  notes?: string
}

export interface ImportPreview {
  filename: string
  format: string
  method: 'local'
  text: string
  segments: string[]
  warnings: string[]
  drafts: ImportDraft[]
}

export interface ImportReview {
  key: string
  fields: Partial<EditableEntry>
}

export const IMPORT_ACCEPT = '.txt,.md,.csv,.json,.pdf,.docx'
export const MAX_IMPORT_BYTES = 12 * 1024 * 1024
