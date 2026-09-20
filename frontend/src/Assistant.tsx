import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import { CopyButton, DictationButton, DictationStatus, ErrorNotice, EvidencePanel, Icon, LanguageToggle, OriginBadge, ReadButton, Spinner, TranslationDirection } from './components'
import { languageLabels, MAX_TEXT } from './types'
import type { AnswerOrigin, ChatMessage, ChatReply, DatasetEvidence, IncomingText, Language, TranslationLanguage } from './types'
import { browserVoiceLanguage, useDictation } from './voice'
import type { ReadAloud } from './voice'
import { useRequest } from './useRequest'

interface DisplayMessage extends ChatMessage {
  id: number
  language: Language
  source: TranslationLanguage
  target: TranslationLanguage
  origin?: AnswerOrigin
  evidence?: DatasetEvidence[]
  model?: string
}

const starters: { icon: 'translate' | 'collection' | 'globe'; title: string; subtitle: string; fr: string; en: string }[] = [
  { icon: 'collection', title: 'Clarify terminology', subtitle: 'Understand meaning and context.', fr: 'Explique le sens et les ambiguïtés de cette expression dans le contexte indiqué : ', en: 'Explain the meaning and ambiguity of this expression in its business context: ' },
  { icon: 'translate', title: 'Review a message', subtitle: 'Check tone, clarity and intent.', fr: 'Vérifie la clarté et le ton de ce message professionnel, sans changer les noms, nombres ou engagements : ', en: 'Review this business message for clarity and tone without changing names, numbers or commitments: ' },
  { icon: 'globe', title: 'Compare translations', subtitle: 'Identify differences before sharing.', fr: 'Compare ces traductions et indique les différences de sens et les points à vérifier : ', en: 'Compare these translations and identify differences in meaning and points requiring review: ' },
]

function makeHistory(messages: DisplayMessage[]): ChatMessage[] {
  const history = messages.slice(-12).map(({ role, content }) => ({ role, content: content.slice(0, MAX_TEXT) }))
  while (history.reduce((length, message) => length + message.content.length, 0) > 24000) {
    history.splice(0, 2)
  }
  return history
}

export function Assistant({ active, aiAvailable, speech, incomingText }: { active: boolean; aiAvailable: boolean; speech: ReadAloud; incomingText?: IncomingText }) {
  const [language, setLanguage] = useState<Language>('fr')
  const [source, setSource] = useState<TranslationLanguage>('francanglais')
  const [target, setTarget] = useState<TranslationLanguage>('fr')
  const [useDataset, setUseDataset] = useState(true)
  const [useDictionary, setUseDictionary] = useState(true)
  const [draft, setDraft] = useState('')
  const [importNotice, setImportNotice] = useState(false)
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [submittedText, setSubmittedText] = useState('')
  const [readReplies, setReadReplies] = useState(false)
  const [voiceLimit, setVoiceLimit] = useState(false)
  const { pending, error, run, cancel, clearError } = useRequest()
  const nextId = useRef(1)
  const readRepliesPreference = useRef(readReplies)
  const thread = useRef<HTMLDivElement>(null)
  const draftInput = useRef<HTMLTextAreaElement>(null)
  const voiceLanguage = browserVoiceLanguage(source)
  const { stop } = speech
  const voice = useDictation(voiceLanguage, (transcript) => {
    clearError()
    setDraft((previous) => {
      const next = [previous.trimEnd(), transcript].filter(Boolean).join(' ')
      if (next.length > MAX_TEXT) setVoiceLimit(true)
      return next.slice(0, MAX_TEXT)
    })
  })
  const { cancel: cancelVoice } = voice

  useEffect(() => {
    readRepliesPreference.current = readReplies
  }, [readReplies])

  useEffect(() => {
    if (!active) {
      cancel()
      cancelVoice()
    }
  }, [active, cancel, cancelVoice])

  useEffect(() => {
    if (!incomingText) return
    cancel()
    cancelVoice()
    stop()
    clearError()
    setDraft(incomingText.text.slice(0, MAX_TEXT))
    setVoiceLimit(false)
    setImportNotice(true)
  }, [incomingText, cancel, cancelVoice, stop, clearError])

  useEffect(() => {
    if (active && thread.current) {
      const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      thread.current.scrollTo({ top: thread.current.scrollHeight, behavior: reducedMotion ? 'instant' : 'smooth' })
    }
  }, [messages, pending, active])

  function clearConversation() {
    cancel()
    cancelVoice()
    speech.stop()
    clearError()
    setMessages([])
    setDraft('')
    setImportNotice(false)
    setVoiceLimit(false)
    draftInput.current?.focus()
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const content = draft.trim()
    if (!content || pending || !aiAvailable || voice.listening) return
    cancelVoice()
    speech.stop()
    setSubmittedText(content)
    const history = makeHistory(messages)
    void run(
      (signal) => api<ChatReply>('/chat', {
        method: 'POST',
        body: { message: content, language, history, use_dataset: useDataset, use_dictionary: useDictionary, source_language: source, target_language: target },
        signal, timeout: 60000,
      }),
      (response) => {
        const userId = nextId.current++
        const assistantId = nextId.current++
        setMessages((previous) => [
          ...previous,
          { id: userId, role: 'user', content, language, source, target },
          { id: assistantId, role: 'assistant', content: response.reply, language, source, target, model: response.model, origin: response.origin ?? 'ai', evidence: response.evidence ?? [] },
        ])
        setDraft('')
        setVoiceLimit(false)
        setImportNotice(false)
        if (readRepliesPreference.current) speech.speak(`assistant-${assistantId}`, response.reply, language)
        window.requestAnimationFrame(() => draftInput.current?.focus())
      },
    )
  }

  return <section className="page assistant-page" aria-labelledby="assistant-title">
    <div className="page-intro compact-intro">
      <div><div className="eyebrow">WRITING & LANGUAGE SUPPORT</div><h1 id="assistant-title">Assistant</h1><p>Review wording, clarify terminology and compare translations before using them in your business communications.</p></div>
      <span className="intro-badge"><Icon name="sparkles" size={18} />AI-assisted · Review required</span>
    </div>
    <div className="chat-workspace">
      <div className="chat-toolbar">
        <div><span className="small-caps">EXPLAIN IN</span><LanguageToggle value={language} label="Assistant explanation language" disabled={pending} onChange={(next) => { speech.stop(); setLanguage(next) }} /></div>
        <button type="button" className="action-button" onClick={clearConversation} disabled={!messages.length && !draft && !pending}><Icon name="refresh" size={17} />Clear conversation</button>
      </div>
      <div className="chat-learning-controls">
        <TranslationDirection source={source} target={target} disabled={pending} onChange={(nextSource, nextTarget) => {
          if (nextSource === nextTarget) return
          cancelVoice()
          speech.stop()
          clearError()
          setSource(nextSource)
          setTarget(nextTarget)
        }} />
        <label className="checkbox-label"><input type="checkbox" checked={useDataset} disabled={pending} onChange={(event) => { clearError(); setUseDataset(event.target.checked) }} />Use approved terminology for this answer</label>
        <label className="checkbox-label"><input type="checkbox" checked={useDictionary} disabled={pending} onChange={(event) => { clearError(); setUseDictionary(event.target.checked) }} />Use reference dictionary for this answer</label>
        <p className="helper-text">The direction guides translation questions; your explanation language is separate. Changing controls does not rewrite earlier answers.</p>
        {!aiAvailable && <p className="helper-text">The assistant requires AI configuration. <a href="#translator">Local translation</a> and <a href="#collection">terminology management</a> are still available.</p>}
      </div>
      <div className={`chat-thread ${!messages.length && !pending ? 'is-empty' : ''}`} ref={thread} role="log" aria-label="Conversation with the AI assistant" aria-live="polite" aria-relevant="additions">
        {!messages.length && !pending ? <div className="chat-welcome">
          <span className="assistant-avatar large-avatar"><Icon name="sparkles" size={34} /></span>
          <span className="small-caps">START A CONVERSATION</span>
          <h2>Get a second view on your wording</h2>
          <p>Add the text and business context you want reviewed. Suggested changes are not applied or saved automatically.</p>
          <div className="chat-starters">{starters.map((starter) => <button type="button" key={starter.title} onClick={() => {
            cancelVoice()
            clearError()
            setDraft(starter[language])
            setImportNotice(false)
            setVoiceLimit(false)
            draftInput.current?.focus()
          }}>
            <Icon name={starter.icon} size={21} /><strong>{starter.title}</strong><span>{starter.subtitle}</span><Icon name="arrow" size={16} />
          </button>)}</div>
        </div> : <>
          {messages.map((message) => <article className={`chat-message message-${message.role}`} key={message.id} aria-label={message.role === 'user' ? 'Your message' : 'Assistant reply'}>
            <span className={`message-avatar ${message.role === 'assistant' ? 'assistant-avatar' : ''}`}>{message.role === 'assistant' ? <Icon name="sparkles" size={19} /> : 'You'}</span>
            <div className="message-body">
              <div className="message-byline">{message.role === 'assistant' ? 'Mboa assistant' : 'You'}</div>
              {message.role === 'assistant' && <><OriginBadge origin={message.origin} /><div className="answer-direction">{languageLabels[message.source]} → {languageLabels[message.target]} · Explanations: {languageLabels[message.language]}</div></>}
              <p>{message.content}</p>
              {message.role === 'assistant' && <>
                <div className="message-actions"><ReadButton speech={speech} id={`assistant-${message.id}`} text={message.content} language={message.language} compact disabled={voice.listening} /><CopyButton text={message.content} compact /></div>
                <EvidencePanel evidence={message.evidence ?? []} origin={message.origin} compact />
                <div className="answer-model">{message.origin === 'dataset' ? 'Local lookup' : 'AI suggestion'} · {message.model || 'Model not reported'} · Nothing saved to the collection.</div>
              </>}
            </div>
          </article>)}
          {pending && <>
            <article className="chat-message message-user" aria-label="Your submitted message"><span className="message-avatar">You</span><div className="message-body"><div className="message-byline">You</div><p>{submittedText}</p></div></article>
            <div className="chat-message message-assistant"><span className="message-avatar assistant-avatar"><Icon name="sparkles" size={19} /></span><div className="message-body"><div className="message-byline">Mboa assistant</div><div className="typing-indicator" role="status"><span /><span /><span /><span className="sr-only">The assistant is thinking</span></div></div></div>
          </>}
        </>}
      </div>

      <div className="chat-compose-wrapper">
        {importNotice && <div className="notice notice-success" role="status"><Icon name="check" size={18} /><span>Imported text is a draft only. Your conversation is preserved. Review the text, direction, and recent history before pressing Send.</span></div>}
        <ErrorNotice message={error} />
        <form className="chat-compose" onSubmit={submit}>
          <label className="sr-only" htmlFor="chat-draft">Message for the assistant</label>
          <textarea id="chat-draft" ref={draftInput} value={draft} maxLength={MAX_TEXT} disabled={pending} rows={3}
            lang={language} placeholder={language === 'fr' ? 'Saisissez votre message et son contexte…' : 'Enter your message and its business context…'}
            aria-describedby="chat-privacy chat-keyboard-hint"
            onChange={(event) => { setDraft(event.target.value); clearError(); setVoiceLimit(false); setImportNotice(false) }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                event.currentTarget.form?.requestSubmit()
              }
            }}
          />
          <div className="chat-compose-bottom">
            <DictationButton voice={voice} language={voiceLanguage} disabled={pending} onStart={speech.stop} />
            <div className="submit-actions"><span className="character-count">{draft.length.toLocaleString()} <span>/ 4,000</span></span>
              {pending ? <button type="button" className="button button-secondary" onClick={cancel}><Icon name="stop" size={16} />Cancel</button> :
                <button type="submit" className="button button-primary" disabled={!draft.trim() || !aiAvailable || voice.listening}><span>Send</span><Icon name="send" size={17} /></button>}
              {pending && <Spinner label="Waiting for a reply" />}
            </div>
          </div>
        </form>
        <DictationStatus voice={voice} />
        {voiceLimit && <p className="helper-text" role="status">The 4,000-character limit was reached. Review the end of your message before sending.</p>}
        <div className="chat-preferences">
          <label className="checkbox-label"><input type="checkbox" checked={readReplies} disabled={!speech.supported} onChange={(event) => {
            readRepliesPreference.current = event.target.checked
            setReadReplies(event.target.checked)
            if (!event.target.checked) speech.stop()
          }} /><Icon name="headphones" size={16} />Read replies aloud</label>
          <span id="chat-keyboard-hint" className="helper-text">Enter to send · Shift + Enter for a new line</span>
        </div>
        <p className="helper-text">Dictation follows your source selection using {voiceLanguage === 'fr' ? 'a French' : 'an English'} recognizer. Review Francanglais and Pidgin spellings yourself. {speech.supported ? 'Read-aloud follows the explanation language, not a native Francanglais or Pidgin voice; pronunciation is approximate.' : 'Read-aloud is not supported in this browser.'}</p>
      </div>
    </div>
    <div className="learning-next-steps"><div><strong>Review AI output before external use.</strong><p>Confirm terminology and context before sharing. <a href="#collection">Manage approved terms</a> or <a href="#imports">import source content</a>. Replies are not saved automatically.</p></div></div>
    <div className="chat-context-note"><Icon name="info" size={16} /><span>Only successful exchanges are remembered. AI context includes up to 6 recent exchanges, within 24,000 characters. Clearing removes this browser conversation, not provider-side records. A changed direction applies to the next request; clear history explicitly if you want a fresh topic.</span></div>
    <p className="privacy-caption" id="chat-privacy"><Icon name="shield" size={15} /><span>Send shares your message, recent history and selected enabled source matches with Gemini. Stored contributor details and private notes are excluded from retrieved matches. Browser dictation may use an external speech service. Review sensitive content before submitting.</span></p>
  </section>
}
