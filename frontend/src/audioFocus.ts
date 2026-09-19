export const AUDIO_FOCUS_EVENT = 'mboa:audio-focus'

export function claimAudioFocus(owner: object) {
  window.dispatchEvent(new CustomEvent(AUDIO_FOCUS_EVENT, { detail: owner }))
}

export function hasAudioFocus(event: Event, owner: object | null): boolean {
  return event instanceof CustomEvent && event.detail === owner
}
