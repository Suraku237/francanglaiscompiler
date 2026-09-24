import type { VocabularyApproval } from './analyzerTypes'

export function VocabularyVerdict({ result, empty }: { result: VocabularyApproval; empty: boolean }) {
  return <div role="group" aria-label="Vocabulary approval">
    <p role="status"><span className={`lab-status ${result.accepted ? 'ready' : 'needs_input'}`}>{result.accepted ? 'ACCEPT' : 'REJECT'}</span></p>
    <p className="lab-copy">{result.accepted
      ? empty
        ? 'No tokens were entered, so there are no UNKNOWN tokens to reject. This does not make the empty input a grammatical sentence.'
        : 'No UNKNOWN tokens. Recognized slang and all other known lexer categories are accepted.'
      : `${result.unknown_count} UNKNOWN ${result.unknown_count === 1 ? 'token needs' : 'tokens need'} review. The classifications show which words or symbols were not recognized.`}</p>
    <p className="lab-copy">Vocabulary approval is not grammatical correctness. The CFG grammar check is shown separately in Analysis.</p>
  </div>
}
