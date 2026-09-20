import type { Page } from '@playwright/test'

declare global {
  interface Window {
    recordedTestBytes?: number
    syntheticAudioTracks?: MediaStreamTrack[]
  }
}

export async function installSyntheticMicrophone(page: Page) {
  await page.evaluate(() => {
    window.recordedTestBytes = 0
    window.syntheticAudioTracks = []
    const NativeRecorder = MediaRecorder
    window.MediaRecorder = class extends NativeRecorder {
      constructor(stream: MediaStream, options?: MediaRecorderOptions) {
        super(stream, options)
        this.addEventListener('dataavailable', (event) => {
          window.recordedTestBytes = (window.recordedTestBytes ?? 0) + event.data.size
        })
      }
    }
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        async getUserMedia() {
          const context = new AudioContext()
          const oscillator = context.createOscillator()
          const destination = context.createMediaStreamDestination()
          oscillator.connect(destination)
          oscillator.start()
          await context.resume()
          for (const track of destination.stream.getTracks()) {
            window.syntheticAudioTracks?.push(track)
            const originalStop = track.stop.bind(track)
            track.stop = () => {
              if (track.readyState === 'ended') return
              originalStop()
              oscillator.stop()
              void context.close()
            }
          }
          return destination.stream
        },
      },
    })
  })
}
