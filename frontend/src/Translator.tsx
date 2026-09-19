import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import { CopyButton, DictationButton, DictationStatus, ErrorNotice, EvidencePanel, Icon, LanguageToggle, OriginBadge, ReadButton, Spinner, TokenAnalysis, TranslationDirection } from './components'
import { isLocalOrigin, languageLabels, MAX_TEXT } from './types'
import type { IncomingText, Language, Tone, Translation, TranslationLanguage } from './types'
import { browserVoiceLanguage, useDictation } from './voice'
import type { ReadAloud } from './voice'
import { useRequest } from './useRequest'

const examples: Record<TranslationLanguage, { label: string; text: string }[]> = {
  fr: [
    { label: 'Retrouver des amis', text: 'Salut les amis, on se retrouve où ce soir ?' },
    { label: 'Au marché', text: 'Bonjour, est-ce que vous pouvez baisser un peu le prix ?' },
    { label: 'La vie au campus', text: 'Je dois réviser pour mon examen de demain, mais je suis fatigué.' },
  ],
  en: [
    { label: 'Meet up with friends', text: 'Hey friends, where are we meeting tonight?' },
    { label: 'At the market', text: 'Hello, could you lower the price a little, please?' },
    { label: 'Campus life', text: 'I need to study for my exam tomorrow, but I am tired.' },
  ],
  francanglais: [{ label: 'An expression to explore', text: 'On est ensemble.' }],
  pidgin: [{ label: 'A greeting to explore', text: 'How you dey?' }],
}

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
  const [useExamples, setUseExamples] = useState(false)
  const [allowAI, setAllowAI] = useState(true)
  const [importNotice, setImportNotice] = useState(false)
  const [tone, setTone] = useState<Tone>('everyday')
  const [result, setResult] = useState<Translation | null>(null)
  const [voiceLimit, setVoiceLimit] = useState(false)
  const { pending, error, run, cancel, clearError } = useRequest()
  const { stop } = speech
  const voiceLanguage = browserVoiceLanguage(source)
  const canTranslate = useDataset || useDictionary || useExamples || (allowAI && aiAvailable)

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
    if (incomingText.kind === 'examples') setUseExamples(true)
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
          use_dictionary: useDictionary, use_examples: useExamples,
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
        <div className="eyebrow"><span className="eyebrow-line" />CAMEROON FRANCANGLAIS & PIDGIN · LEARN BOTH WAYS</div>
        <h1 id="translator-title">Many words.<br /><em>More understanding.</em></h1>
        <p>Explore Francanglais and Cameroon Pidgin alongside French and English.<br className="desktop-break" /> Compare reviewed collection entries and source-labelled reference vocabulary.</p>
      </div>
      <div className="intro-note" aria-label="Learn with comparisons and human review">
        <div className="orbit-mark" aria-hidden="true"><span>fr</span><Icon name="sparkles" size={31} /><span>en</span></div>
        <p>Compare. Understand.<br /><strong>Review. Contribute.</strong></p>
        <span className="small-caps">DATASET FIRST · PEOPLE IN THE LOOP</span>
      </div>
    </div>

    {importNotice && <div className="notice notice-success" role="status"><Icon name="check" size={18} /><span>{incomingText?.kind === 'examples' ? 'A constructed example is in your draft and its source is enabled. This is practice, not fieldwork. Review it, then choose Translate; nothing has been submitted or saved.' : incomingText?.kind === 'dictionary' ? 'A reference word is in your draft, set to Francanglais → English. Review it, then choose Translate. Nothing has been submitted or saved.' : 'Imported text is in your draft. Check the source language and wording, then choose Translate. Nothing has been submitted or saved.'}</span></div>}
    <form className="translation-workspace" onSubmit={submit}>
      <div className="source-panel">
        <div className="panel-topline"><span className="small-caps">01 / YOUR WORDS</span><Icon name="globe" size={18} /></div>
        <div className="learning-source-controls">
          <TranslationDirection source={source} target={target} onChange={changeDirection} />
          <div className="translation-options">
            <div className="explanation-control"><span className="small-caps">EXPLAIN IN</span><LanguageToggle value={explanationLanguage} label="Explanation language" onChange={(next) => { invalidate(); setExplanationLanguage(next) }} /></div>
          <label className="tone-control"><span>Tone</span>
            <select value={tone} aria-label="Translation tone" onChange={(event) => {
              invalidate()
              setTone(event.target.value as Tone)
            }}>
              <option value="everyday">Everyday</option>
              <option value="polite">Polite</option>
              <option value="street">Street</option>
            </select>
          </label>
          </div>
          <div className="grounding-options">
            <label className="checkbox-label"><input type="checkbox" checked={useDataset} onChange={(event) => { invalidate(); setUseDataset(event.target.checked) }} />Use approved dataset matches</label>
            <label className="checkbox-label"><input type="checkbox" checked={useDictionary} onChange={(event) => { invalidate(); setUseDictionary(event.target.checked) }} />Use reference dictionary</label>
            <label className="checkbox-label"><input type="checkbox" checked={useExamples} onChange={(event) => { invalidate(); setUseExamples(event.target.checked) }} />Use constructed practice examples (not fieldwork)</label>
            <label className="checkbox-label"><input type="checkbox" checked={allowAI && aiAvailable} disabled={!aiAvailable} onChange={(event) => { invalidate(); setAllowAI(event.target.checked) }} />Allow AI suggestions for gaps</label>
            <p className="helper-text">Exact, unambiguous matches from enabled local sources need no AI key. The reference dictionary supplies English meanings, not French translations. If enabled, AI fallback receives your text and selected matches from the sources you enable.</p>
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
        <div className="panel-topline"><span className="small-caps">02 / COMPARE & LEARN</span><span className="language-badge">{languageLabels[target]}</span></div>
        {pending ? <div className="translation-loading" role="status">
          <div className="loading-symbol"><Icon name="sparkles" size={32} /></div>
          <h2>Finding the right words…</h2>
          <p>{useDataset || useDictionary || useExamples ? 'Checking enabled local sources first.' : 'Requesting a clearly labeled AI suggestion.'}</p>
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
          {result.explanation && <div className="result-explanation"><span className="small-caps">BEHIND THE EXPRESSION</span><p>{result.explanation}</p></div>}
        </div> : <div className="translation-empty">
          <div className="empty-spark" aria-hidden="true"><Icon name="sparkles" size={40} /><span className="tiny-spark">✦</span></div>
          <h2>A meaning to explore.<br /><em>A source to compare.</em></h2>
          <p>Your {languageLabels[target]} result will appear here.<br />Collection matches, reference meanings, and AI suggestions are labelled separately.</p>
          <span className="empty-dots" aria-hidden="true"><i /><i /><i /></span>
        </div>}
        <div className="result-footnote"><Icon name="leaf" size={15} /><span>Language is living. Context makes the difference.</span></div>
      </div>
    </form>

    <ErrorNotice message={error} />
    <div className="examples-row"><span className="small-caps">PRACTICE DRAFTS · NOT DATASET ATTESTATIONS</span>{examples[source].map((example) => <button className="example-chip" type="button" key={example.label} onClick={() => { cancelVoice(); updateText(example.text) }}>{example.label}<Icon name="arrow" size={14} /></button>)}</div>

    {result && <div className="translation-details">
      <EvidencePanel evidence={result.evidence ?? []} origin={result.origin} />
      {result.coverage && <section className="coverage-card" aria-labelledby="coverage-title">
        <div className="section-title"><Icon name="search" size={18} /><h2 id="coverage-title">What this lookup covered</h2></div>
        <dl className="coverage-summary">
          <div><dt>Matched in enabled local sources</dt><dd>{result.coverage.matched_terms.length ? result.coverage.matched_terms.join(' · ') : 'No matching terms reported'}</dd></div>
          <div><dt>Not matched in this lookup</dt><dd>{result.coverage.unmatched_terms.length ? result.coverage.unmatched_terms.join(' · ') : 'No unmatched terms reported—not a guarantee of full understanding'}</dd></div>
        </dl>
        {result.coverage.warnings.length > 0 && <ul className="coverage-warnings">{result.coverage.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
        <p className="helper-text">Missing matches are learning gaps, not proof that a word is invalid. Review with a speaker before adding an entry.</p>
      </section>}
      {result.vocabulary.length > 0 && <section className="vocabulary-card" aria-labelledby="vocabulary-title">
        <div className="section-title"><Icon name="collection" size={19} /><h2 id="vocabulary-title">A few words to take with you</h2></div>
        <dl className="vocabulary-grid">{result.vocabulary.map((word, index) => <div key={`${word.term}-${index}`}><dt>{word.term}</dt><dd>{word.meaning}</dd></div>)}</dl>
      </section>}
      {result.note && <div className="notice notice-subtle"><Icon name="info" /><p>{result.note}</p></div>}
      {result.analysis && <details className="analysis-details">
        <summary><Icon name="code" size={17} /><span>Look at the local lexer analysis</span><Icon name="chevron" size={15} /></summary>
        <TokenAnalysis analysis={result.analysis} />
      </details>}
      <p className="helper-text model-note">{isLocalOrigin(result.origin) ? `Local lookup · ${result.model}. No Gemini translation request was needed.` : `AI suggestion · ${result.model}. Retrieved evidence does not verify all generated wording; check cultural nuance with a speaker.`}</p>
    </div>}

    <div className="learning-next-steps">
      <div><strong>Turn a gap into something to learn.</strong><p>Keep Francanglais and Cameroon Pidgin distinct. Compare meanings, record real context, and approve only after your review.</p></div>
      <div className="learning-links"><a className="button button-secondary" href="#dictionary"><Icon name="search" size={17} />Browse dictionary</a><button type="button" className="button button-secondary" onClick={onOpenCollection}><Icon name="collection" size={17} />Review collection</button><button type="button" className="button button-secondary" onClick={onOpenImports}><Icon name="upload" size={17} />Import & learn</button></div>
    </div>
    <div className="translator-bottom-grid">
      <article className="culture-card">
        <div className="culture-illustration" aria-hidden="true"><span className="speech-tile tile-one">on est</span><span className="speech-tile tile-two">ensemble.</span><span className="culture-star">✳</span></div>
        <div><span className="small-caps">TWO LANGUAGES, MANY CONTEXTS</span><h2>Related conversations.<br />Distinct ways of speaking.</h2><p>Francanglais (Camfranglais) and Cameroon Pidgin are not interchangeable. Usage and spelling vary with speakers and places; this collection is never a complete dictionary.</p></div>
      </article>
      <button type="button" className="assistant-promo" onClick={onOpenAssistant}>
        <span className="promo-icon"><Icon name="sparkles" size={24} /></span>
        <span><span className="small-caps">GO BEYOND TRANSLATION</span><strong>Curious about an expression?</strong><span className="promo-description">Ask the assistant. Get the story behind the words.</span></span>
        <Icon name="arrow" size={21} />
      </button>
    </div>
    <p className="privacy-caption" id="translation-voice-privacy"><Icon name="shield" size={15} /><span>Exact local lookups do not call Gemini. When enabled and needed, AI fallback sends your submitted text and selected source-labelled matches—not collection contributor names, locations, notes, the full corpus, or the full dictionary. Optional dictation may send audio to your browser’s speech provider. Neither importing nor dictation submits automatically.</span></p>
  </section>
}
