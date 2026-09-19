import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRef, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Modal } from '../../src/components'

describe('Modal', () => {
  function FocusFixture() {
    const [open, setOpen] = useState(false)
    const initialFocus = useRef<HTMLInputElement>(null)
    return <>
      <button onClick={() => setOpen(true)}>Open fixture</button>
      {open && <Modal title="Focus fixture" onClose={() => setOpen(false)} initialFocus={initialFocus}>
        <input ref={initialFocus} aria-label="Fixture input" />
        <button onClick={() => setOpen(false)}>Done</button>
      </Modal>}
    </>
  }

  it('focuses the requested field after opening and restores the trigger after unmount', async () => {
    const user = userEvent.setup()
    render(<FocusFixture />)
    const trigger = screen.getByRole('button', { name: 'Open fixture' })
    await user.click(trigger)
    expect(screen.getByRole('textbox', { name: 'Fixture input' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Done' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('wraps keyboard focus within the dialog in both directions', async () => {
    const user = userEvent.setup()
    render(<FocusFixture />)
    await user.click(screen.getByRole('button', { name: 'Open fixture' }))
    const close = screen.getByRole('button', { name: 'Close dialog' })
    await user.tab({ shift: true })
    expect(close).toHaveFocus()
    await user.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Done' })).toHaveFocus()
    await user.tab()
    expect(close).toHaveFocus()
  })

  it('opens a named native dialog and closes it when unmounted', () => {
    const open = vi.spyOn(HTMLDialogElement.prototype, 'showModal')
    const close = vi.spyOn(HTMLDialogElement.prototype, 'close')
    const { unmount } = render(<Modal title="Review fixture" onClose={vi.fn()}><p>Review first.</p></Modal>)
    expect(screen.getByRole('dialog', { name: 'Review fixture' })).toHaveAttribute('open')
    expect(open).toHaveBeenCalledOnce()
    unmount()
    expect(close).toHaveBeenCalledOnce()
  })

  it('blocks close and Escape during a mutation, then permits both when idle', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const { rerender } = render(<Modal title="Saving fixture" onClose={onClose} busy><p>Saving.</p></Modal>)
    const dialog = screen.getByRole('dialog', { name: 'Saving fixture' })
    const cancel = new Event('cancel', { cancelable: true })
    fireEvent(dialog, cancel)
    await user.click(screen.getByRole('button', { name: 'Close dialog' }))
    expect(cancel.defaultPrevented).toBe(true)
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Close dialog' })).toBeDisabled()

    rerender(<Modal title="Saving fixture" onClose={onClose}><p>Saved.</p></Modal>)
    fireEvent(dialog, new Event('cancel', { cancelable: true }))
    expect(onClose).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Close dialog' }))
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})
