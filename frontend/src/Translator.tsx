import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import { CopyButton, DictationButton, DictationStatus, ErrorNotice, EvidencePanel, Icon, LanguageToggle, OriginBadge, ReadButton, Spinner, TranslationDirection } from './components'
import { isLocalOrigin, languageLabels, MAX_TEXT } from './types'
import type { IncomingText, Language, Tone, Translation, TranslationLanguage } from './types'
import { browserVoiceLanguage, useDictation } from './voice'
import type { ReadAloud } from './voice'
import { useRequest } from './useRequest'

export function Translator({ active, aiAvailable, speech, incomingText, onOpenAssistant, onOpenCollection, onOpenImports }: {
  active: boolean
  aiAvailable: boolean
  speech: ReadAloud
  incomingText?: IncomingText
  onOpenAssistant: () => void
  onOpenCollection: () => void
  onOpenImports: () => void
}) {
  const [text, setText] = useState('')
  const [source, setSource] = useState<TranslationLanguage>('fr')
  const [target, setTarget] = useState<TranslationLanguage>('francanglais')
  const [explanationLanguage, setExplanationLanguage] = useState<Language>('fr')
  const [useDataset, setUseDataset] = useState(true)
  const [useDictionary, setUseDictionary] = useState(true)
  const [allowAI, setAllowAI] = useState(true)
  const [importNotice, setImportNotice] = useState(false)
  const [tone, setTone] = useState<Tone>('everyday')
  const [result, setResult] = useState<Translation | null>(null)
  const [voiceLimit, setVoiceLimit] = useState(false)
  const { pending, error, run, cancel, clearError } = useRequest()
  const { stop } = speech
  const voiceLanguage = browserVoiceLanguage(source)
  const canTranslate = useDataset || useDictionary || (allowAI && aiAvailable)

  const invalidate = useCallback(() => {
    cancel()
    clearError()
    setResult(null)
    setVoiceLimit(false)
    stop()
  }, [cancel, clearError, stop])

  const voice = useDictation(voiceLanguage, (transcript) => {
    invalidate()
    setText((previous) => {
      const next = [previous.trimEnd(), transcript].filter(Boolean).join(' ')
      if (next.length > MAX_TEXT) setVoiceLimit(true)
      return next.slice(0, MAX_TEXT)
    })
  })
  const { cancel: cancelVoice } = voice

  useEffect(() => {
    if (!active) {
      cancel()
      cancelVoice()
    }
  }, [active, cancel, cancelVoice])

  useEffect(() => {
    if (!incomingText) return
    cancelVoice()
    invalidate()
    setText(incomingText.text.slice(0, MAX_TEXT))
    if (incomingText.source && incomingText.target && incomingText.source !== incomingText.target) {
      setSource(incomingText.source)
      setTarget(incomingText.target)
    }
    if (incomingText.kind === 'dictionary') setUseDictionary(true)
    setImportNotice(true)
  }, [incomingText, cancelVoice, invalidate])

  function updateText(next: string) {
    invalidate()
    setImportNotice(false)
    setText(next)
  }

  function changeDirection(nextSource: TranslationLanguage, nextTarget: TranslationLanguage) {
    if (nextSource === nextTarget) return
    cancelVoice()
    invalidate()
    setSource(nextSource)
    setTarget(nextTarget)
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!text.trim() || pending || !canTranslate || voice.listening || source === target) return
    cancelVoice()
    stop()
    setResult(null)
    void run(
      (signal) => api<Translation>('/translate', {
        method: 'POST',
        body: {
          text: text.trim(), source_language: source, target_language: target,
          explanation_language: explanationLanguage, tone, use_dataset: useDataset,
          use_dictionary: useDictionary,
          allow_ai: allowAI && aiAvailable,
        },
        signal,
        timeout: 60000,
      }),
      setResult,
    )
  }

  return <section aria-labelledby="translator-title" className="page translator-page">
    <div className="page-intro translator-intro">
      <div>
        <div className="eyebrow">LANGUAGE SERVICES</div>
        <h1 id="translator-title">Translate</h1>
        <p>Translate messages and business content with reviewed terminology and clearly identified sources.</p>
      </div>
      <button type="button" className="button button-secondary" onClick={onOpenImports}><Icon name="upload" size={18} />Import a document</button>
    </div>

    {importNotice && <div className="notice notice-success" role="status"><Icon name="check" size={18} /><span>{incomingText?.kind === 'dictionary' ? 'Dictionary entry loaded. Review the direction, then select Translate.' : 'Text loaded as a draft. Review the language direction before translating.'} Nothing has been submitted or saved.</span></div>}
    <form className="translation-workspace" onSubmit={submit}>
      <div className="source-panel">
        <div className="panel-topline"><span className="small-caps">SOURCE TEXT</span><Icon name="globe" size={18} /></div>
        <div className="learning-source-controls">
          <TranslationDirection source={source} target={target} onChange={changeDirection} />
          <div className="translation-options">
            <div className="explanation-control"><span className="small-caps">EXPLAIN IN</span><LanguageToggle value={explanationLanguage} label="Explanation language" onChange={(next) => { invalidate(); setExplanationLanguage(next) }} /></div>
          <label className="tone-control"><span>Tone</span>
            <select value={tone} aria-label="Translation tone" onChange={(event) => {
              invalidate()
              setTone(event.target.value as Tone)
            }}>
              <option value="everyday">Neutral</option>
              <option value="polite">Polite / professional</option>
              <option value="street">Informal</option>
            </select>
          </label>
          </div>
          <div className="grounding-options">
            <label className="checkbox-label"><input type="checkbox" checked={useDataset} onChange={(event) => { invalidate(); setUseDataset(event.target.checked) }} />Use approved terminology</label>
            <label className="checkbox-label"><input type="checkbox" checked={useDictionary} onChange={(event) => { invalidate(); setUseDictionary(event.target.checked) }} />Use reference dictionary</label>
            <label className="checkbox-label"><input type="checkbox" checked={allowAI && aiAvailable} disabled={!aiAvailable} onChange={(event) => { invalidate(); setAllowAI(event.target.checked) }} />Allow AI suggestions for gaps</label>
            <p className="helper-text">Exact local matches need no AI. The reference dictionary contains English meanings only. AI processing uses your submitted text and selected source matches.</p>
            {!canTranslate && <p className="helper-text">Enable a local source or available AI suggestions to translate.</p>}
          </div>
        </div>
        <label className="sr-only" htmlFor="translation-source">{languageLabels[source]} text to translate</label>
        <textarea id="translation-source" className="translation-input" value={text} maxLength={MAX_TEXT}
          lang={source === 'fr' || source === 'en' ? source : undefined} placeholder={`Write or paste ${languageLabels[source]} here…`}
          onChange={(event) => updateText(event.target.value)} aria-describedby="translation-limit translation-voice-note translation-voice-privacy"
        />
        <div className="input-bottom">
          <DictationButton voice={voice} language={voiceLanguage} disabled={pending} onStart={stop} />
          <div className="character-controls">
            {text && <button type="button" className="icon-button clear-input" aria-label="Clear source text" onClick={() => { cancelVoice(); updateText('') }}><Icon name="close" size={15} /></button>}
            <span id="translation-limit" className={`character-count ${text.length >= MAX_TEXT ? 'at-limit' : ''}`}>{text.length.toLocaleString()} <span>/ 4,000</span></span>
          </div>
        </div>
        <DictationStatus voice={voice} />
        <p className="helper-text" id="translation-voice-note">Dictation uses {voiceLanguage === 'fr' ? 'a French' : 'an English'} browser recognizer. Francanglais and Pidgin are approximations; review spellings before submitting.</p>
        {voiceLimit && <p className="helper-text" role="status">The 4,000-character limit was reached. Review the end of your text before translating.</p>}
        <div className="source-submit">
          <span className="helper-text">{pending ? 'Editing your text cancels this request.' : 'No automatic saves. Review every suggestion.'}</span>
          <div className="submit-actions">
            {pending && <button type="button" className="text-button" onClick={cancel}>Cancel</button>}
            <button type="submit" className="button button-primary" disabled={!text.trim() || pending || !canTranslate || voice.listening}>
              {pending ? <Spinner label="Translating" /> : <Icon name="sparkles" size={17} />}
              {pending ? 'Translating…' : 'Translate'}{!pending && <Icon name="arrow" size={18} />}
            </button>
          </div>
        </div>
      </div>

      <div className="result-panel" aria-busy={pending}>
        <div className="panel-topline"><span className="small-caps">TRANSLATION</span><span className="language-badge">{languageLabels[target]}</span></div>
        {pending ? <div className="translation-loading" role="status">
          <div className="loading-symbol"><Icon name="sparkles" size={32} /></div>
          <h2>Translating your content</h2>
          <p>{useDataset || useDictionary ? 'Checking selected sources first.' : 'Processing your AI request.'}</p>
          <div className="skeleton-lines" aria-hidden="true"><span /><span /><span /></div>
        </div> : result ? <div className="translation-result">
          <OriginBadge origin={result.origin} exact={result.origin === 'dataset' && Boolean(result.translation) && result.evidence?.some((entry) => entry.match_type === 'exact')} />
          <p className="result-text" aria-live="polite">{result.translation}</p>
          {!result.translation && <p className="result-explanation">No complete translation was found in the enabled local sources. Compare dictionary senses, add reviewed entries, or explicitly enable AI suggestions.</p>}
          {result.translation && <div className="result-actions">
            <ReadButton speech={speech} id="translation-result" text={result.translation} language={browserVoiceLanguage(result.target_language ?? target)} disabled={voice.listening} />
            <CopyButton text={result.translation} />
          </div>}
          <p className="helper-text pronunciation-note">{speech.supported ? `Uses ${browserVoiceLanguage(result.target_language ?? target) === 'fr' ? 'a French' : 'an English'} browser voice. Francanglais and Cameroon Pidgin pronunciation are approximations, not native voice models.` : 'Read-aloud isn’t available in this browser. You can still copy the translation.'}</p>
          {result.explanation && <div className="result-explanation"><span className="small-caps">TRANSLATION NOTES</span><p>{result.explanation}</p></div>}
        </div> : <div className="translation-empty">
          <div className="empty-spark" aria-hidden="true"><Icon name="translate" size={32} /></div>
          <h2>Your translation will appear here</h2>
          <p>Enter source text, select your languages and choose Translate. Results identify their sources and review status.</p>
        </div>}
        <div className="result-footnote"><Icon name="shield" size={15} /><span>Review wording and context before sharing externally.</span></div>
      </div>
    </form>

    <ErrorNotice message={error} />

    {result && <div className="translation-details">
      <EvidencePanel evidence={result.evidence ?? []} origin={result.origin} />
      {result.coverage && <section className="coverage-card" aria-labelledby="coverage-title">
        <div className="section-title"><Icon name="search" size={18} /><h2 id="coverage-title">What this lookup covered</h2></div>
        <dl className="coverage-summary">
          <div><dt>Matched in enabled local sources</dt><dd>{result.coverage.matched_terms.length ? result.coverage.matched_terms.join(' · ') : 'No matching terms reported'}</dd></div>
          <div><dt>Not matched in this lookup</dt><dd>{result.coverage.unmatched_terms.length ? result.coverage.unmatched_terms.join(' · ') : 'No unmatched terms reported—not a guarantee of full understanding'}</dd></div>
        </dl>
        {result.coverage.warnings.length > 0 && <ul className="coverage-warnings">{result.coverage.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
        <p className="helper-text">Missing matches indicate limited source coverage. Review meaning and context before approving new terminology.</p>
      </section>}
      {result.vocabulary.length > 0 && <section className="vocabulary-card" aria-labelledby="vocabulary-title">
        <div className="section-title"><Icon name="collection" size={19} /><h2 id="vocabulary-title">Key terminology</h2></div>
        <dl className="vocabulary-grid">{result.vocabulary.map((word, index) => <div key={`${word.term}-${index}`}><dt>{word.term}</dt><dd>{word.meaning}</dd></div>)}</dl>
      </section>}
      {result.note && <div className="notice notice-subtle"><Icon name="info" /><p>{result.note}</p></div>}
      <p className="helper-text model-note">{isLocalOrigin(result.origin) ? `Local lookup · ${result.model}. No Gemini translation request was needed.` : `AI suggestion · ${result.model}. Retrieved evidence does not verify all generated wording; check cultural nuance with a speaker.`}</p>
    </div>}

    <div className="workspace-shortcuts">
      <a className="button button-secondary" href="#dictionary"><Icon name="search" size={17} />Search dictionary</a>
      <button type="button" className="button button-secondary" onClick={onOpenCollection}><Icon name="collection" size={17} />Manage terminology</button>
      <button type="button" className="button button-secondary" onClick={onOpenAssistant}><Icon name="sparkles" size={17} />Ask the assistant</button>
    </div>
    <p className="privacy-caption" id="translation-voice-privacy"><Icon name="shield" size={15} /><span>Exact local lookups do not call Gemini. When enabled and needed, AI fallback sends your submitted text and selected source-labelled matches—not collection contributor names, locations, notes, the full corpus, or the full dictionary. Optional dictation may send audio to your browser’s speech provider. Neither importing nor dictation submits automatically.</span></p>
  </section>
}
