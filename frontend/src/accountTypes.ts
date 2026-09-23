export interface Account {
  id: string
  email: string
  display_name: string
  email_verified: boolean
  google_linked: boolean
}

export interface Session {
  user: Account | null
  csrf_token: string | null
  google_enabled: boolean
  email_enabled: boolean
  development_mail: boolean
}

export interface Project {
  id: string
  name: string
  created_at: string
}

export interface ProjectsResult {
  projects: Project[]
  default_project_id: string
  shared: true
  registered_users: number
}

export interface SavedTranslation {
  source_text: string
  source_language: 'fr' | 'en' | 'francanglais' | 'pidgin'
  target_language: 'fr' | 'en' | 'francanglais' | 'pidgin'
  translation: string
  explanation: string
  note: string
}

export interface SavedConversation {
  messages: { role: 'user' | 'assistant'; content: string }[]
}

export interface HistorySummary {
  id: string
  kind: 'translation' | 'conversation'
  title: string
  created_at: string
  updated_at: string
}

export type HistoryItem = HistorySummary & (
  { kind: 'translation'; content: SavedTranslation } |
  { kind: 'conversation'; content: SavedConversation }
)
