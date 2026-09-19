import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Modal } from '../../src/components'

describe('Modal', () => {
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
