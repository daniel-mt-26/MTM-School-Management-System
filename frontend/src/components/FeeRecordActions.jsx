import { useEffect, useRef, useState } from 'react'

export default function FeeRecordActions({ record, recurring = false, onDelete, onDeactivate, onDeleted }) {
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dialog = useRef(null)
  useEffect(() => {
    if (confirming) dialog.current?.showModal()
  }, [confirming])

  async function remove() {
    setBusy(true); setError('')
    try { await onDelete(record.id); setConfirming(false); onDeleted(record.id) }
    catch (e) { setError(e.data?.detail || 'The fee could not be deleted. Please try again.') }
    finally { setBusy(false) }
  }
  async function deactivate() {
    setBusy(true); setError('')
    try { await onDeactivate(record.id, !record.is_active) }
    catch (e) { setError(e.data?.detail || 'The fee status could not be updated.') }
    finally { setBusy(false) }
  }
  return <>
    <button type="button" disabled={busy} onClick={deactivate}>{record.is_active ? 'Deactivate' : 'Activate'}</button>
    {record.can_delete && <button type="button" disabled={busy} onClick={() => { setError(''); setConfirming(true) }}>Delete permanently</button>}
    {!record.can_delete && <p>Financial history is preserved. Permanent deletion is unavailable.</p>}
    {error && !confirming && <p role="alert">{error}</p>}
    {confirming && <dialog ref={dialog} aria-labelledby={`delete-fee-${recurring ? 'template' : 'fee'}-${record.id}`} onCancel={(event) => { event.preventDefault(); if (!busy) setConfirming(false) }}>
      <h2 id={`delete-fee-${recurring ? 'template' : 'fee'}-${record.id}`}>{recurring ? 'Delete recurring fee permanently?' : 'Delete this fee permanently?'}</h2>
      <p>{record.name} — {record.currency} {record.amount}</p>
      <p>This should only be used for fees created by mistake. This action cannot be undone.</p>
      <p>{recurring ? 'If charges have already been generated, deletion will be blocked.' : 'If financial records exist, deletion will be blocked.'}</p>
      {error && <p role="alert">{error}</p>}
      <button type="button" autoFocus disabled={busy} onClick={() => setConfirming(false)}>Cancel</button>
      <button type="button" disabled={busy} onClick={remove}>{busy ? 'Deleting…' : 'Delete permanently'}</button>
    </dialog>}
  </>
}
