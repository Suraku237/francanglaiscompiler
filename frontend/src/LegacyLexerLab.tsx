import { useEffect, useState } from 'react'
import { api } from './api'
import { ErrorNotice, Icon, Spinner, TokenAnalysis } from './components'
import { MAX_TEXT } from './types'
import type { Analysis } from './types'
import { useRequest } from './useRequest'

export function LegacyLexerLab({ active }: { active: boolean }) {
  const [text, setText] = useState('')
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const { pending, error, run, cancel, clearError } = useRequest()
  useEffect(() => { if (!active) cancel() }, [active, cancel])
  return <details className="lexer-lab">
    <summary><span className="lexer-icon"><Icon name="code" size={22} /></span><span><strong>Look inside the language</strong><span>Explore tokens with the local lexer. No AI, no external request.</span></span><span className="local-badge">LOCAL TOOL</span><Icon name="chevron" size={15} /></summary>
    <div className="lexer-content">
      <form onSubmit={(event) => {
        event.preventDefault()
        if (!text.trim() || pending) return
        setAnalysis(null)
        void run((signal) => api<Analysis>('/analyze', { method: 'POST', body: { text: text.trim() }, signal }), setAnalysis)
      }}>
        <div className="field"><label htmlFor="lexer-text">An expression to inspect</label><textarea id="lexer-text" rows={3} value={text} maxLength={MAX_TEXT} onChange={(event) => { cancel(); clearError(); setAnalysis(null); setText(event.target.value) }} placeholder="Paste a Francanglais expression..." /><span className="field-hint">{text.length.toLocaleString()} / 4,000 characters</span></div>
        <div className="lexer-submit"><p className="helper-text">Only sent to your local backend.</p><div className="submit-actions">{pending && <button type="button" className="text-button" onClick={cancel}>Cancel</button>}<button type="submit" className="button button-primary" disabled={!text.trim() || pending}>{pending ? <Spinner label="Analyzing expression" /> : <Icon name="code" size={18} />}{pending ? 'Analyzing...' : 'Analyze expression'}</button></div></div>
      </form>
      <ErrorNotice message={error} />
      {analysis && <TokenAnalysis analysis={analysis} />}
    </div>
  </details>
}
