import { afterAll, beforeAll, beforeEach, vi } from 'vitest'

export function setupAssistantBrowser() {
  const scrollDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollTo')
  beforeAll(() => Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() }))
  afterAll(() => {
    if (scrollDescriptor) Object.defineProperty(HTMLElement.prototype, 'scrollTo', scrollDescriptor)
    else Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo')
  })
  beforeEach(() => {
    vi.stubGlobal('matchMedia', vi.fn((media: string): MediaQueryList => ({
      media, matches: true, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(() => true),
    })))
  })
}
