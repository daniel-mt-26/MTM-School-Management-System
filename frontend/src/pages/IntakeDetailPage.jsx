import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getIntake,
  intakeError,
  intakeHistory,
  intakeTypes,
  reviewIntake,
} from '../api/intake'

export default function IntakeDetailPage({ kind }) {
  const { intakeId } = useParams()
  const [revision, setRevision] = useState(0)
  return (
    <IntakeRecord
      key={`${kind}:${intakeId}:${revision}`}
      kind={kind}
      id={intakeId}
      reload={() => setRevision((value) => value + 1)}
    />
  )
}
function IntakeRecord({ kind, id, reload }) {
  const type = intakeTypes[kind],
    application = kind === 'applications'
  const [record, setRecord] = useState(null),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('')
  const [note, setNote] = useState(''),
    [status, setStatus] = useState(''),
    [confirming, setConfirming] = useState(null)
  const [busy, setBusy] = useState(false),
    [blocked, setBlocked] = useState(false),
    [historyRevision, setHistoryRevision] = useState(0)
  const alive = useRef(false),
    lock = useRef(false),
    controller = useRef(null),
    dialog = useRef(null),
    opener = useRef(null)
  const noteField = useRef(null),
    reviewError = useRef(null),
    savingStatus = useRef(null)
  useEffect(() => {
    alive.current = true
    controller.current = new AbortController()
    getIntake(kind, id, controller.current.signal)
      .then((row) => {
        if (!alive.current) return
        if (
          row?.id !== id ||
          !Number.isInteger(row.version) ||
          !type.statuses[row.status]
        )
          throw new Error('Invalid record response')
        setRecord(row)
        setStatus(row.status)
      })
      .catch((failure) => {
        if (alive.current) setError(intakeError(failure))
      })
    return () => {
      alive.current = false
      controller.current?.abort()
    }
  }, [kind, id, type])
  useEffect(() => {
    if (confirming) {
      dialog.current?.showModal()
      dialog.current?.querySelector('button')?.focus()
    } else opener.current?.focus()
  }, [confirming])
  useEffect(() => {
    if (busy) savingStatus.current?.focus()
  }, [busy])
  function ask(nextStatus, event) {
    if (lock.current || blocked) return
    if (!nextStatus && !note.trim()) {
      noteField.current?.focus()
      return
    }
    opener.current =
      event.currentTarget.tagName === 'FORM'
        ? event.nativeEvent.submitter || document.activeElement
        : event.currentTarget
    setError('')
    setNotice('')
    setConfirming({
      status: nextStatus,
      note: note.trim(),
      version: record.version,
    })
  }
  async function save() {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    setError('')
    controller.current = new AbortController()
    try {
      const updated = await reviewIntake(
        kind,
        id,
        confirming,
        controller.current.signal,
      )
      if (!alive.current) return
      if (
        updated?.id !== id ||
        !Number.isInteger(updated.version) ||
        updated.version <= record.version ||
        !type.statuses[updated.status]
      )
        throw new Error('Invalid review response')
      setRecord(updated)
      setStatus(updated.status)
      setNote('')
      setNotice('Review saved by the backend.')
      setHistoryRevision((value) => value + 1)
    } catch (failure) {
      if (!alive.current) return
      setError(intakeError(failure))
      // A lost POST response may have committed. Require a fresh GET before another mutation.
      if (failure.status !== 400) setBlocked(true)
      requestAnimationFrame(() => reviewError.current?.focus())
    } finally {
      lock.current = false
      if (alive.current) {
        setBusy(false)
        setConfirming(null)
      }
    }
  }
  const header = (
    <header className="student-page-header">
      <div>
        <Link className="dashboard-link" to={type.route}>
          Back to {type.title}
        </Link>
        <h1>{type.singular} Details</h1>
        {record && <p className="intake-reference">{record.reference}</p>}
      </div>
      <button
        type="button"
        className="secondary-button"
        disabled={busy}
        onClick={reload}
      >
        Reload latest record
      </button>
    </header>
  )
  if (!record)
    return (
      <main className="student-page intake-page">
        {header}
        <section className="student-state" role={error ? 'alert' : 'status'}>
          {error || `Loading ${type.singular.toLowerCase()}...`}
        </section>
      </main>
    )
  const details = application
    ? [
        ['Student full name', record.student_name],
        ['Date of birth', record.date_of_birth],
        ['Grade requested', record.grade],
        ['Parent or guardian', record.guardian_name],
        ['Residential address', record.address],
        ['Previous school', record.previous_school || 'Not provided'],
        [
          'Additional information',
          record.additional_information || 'Not provided',
        ],
      ]
    : [
        ['Sender name', record.full_name],
        ['Subject', record.subject],
        ['Message', record.message],
      ]
  return (
    <main className="student-page intake-page">
      {header}
      <section className="profile-section">
        <h2>{type.singular} information</h2>
        <dl className="detail-grid">
          {details.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd className="intake-copy">{value}</dd>
            </div>
          ))}
          <div>
            <dt>Contact number</dt>
            <dd>{record.phone}</dd>
          </div>
          <div>
            <dt>Email address</dt>
            <dd>{record.email}</dd>
          </div>
          <div>
            <dt>Submitted</dt>
            <dd>
              {new Date(record.created_at).toLocaleString('en-GB', {
                timeZone: 'Africa/Harare',
              })}
            </dd>
          </div>
          <div>
            <dt>Current status</dt>
            <dd>
              <span className={`status-badge intake-status ${record.status}`}>
                {type.statuses[record.status]}
              </span>
            </dd>
          </div>
        </dl>
      </section>
      <section className="profile-section">
        <h2>{application ? 'Review application' : 'Handle enquiry'}</h2>
        {application && (
          <p>
            Approval records the review decision only. It does not create a
            student, parent or enrolment.
          </p>
        )}
        {notice && (
          <p className="form-success" role="status">
            {notice}
          </p>
        )}
        {error && (
          <p
            ref={reviewError}
            tabIndex={-1}
            className="form-error"
            role="alert"
          >
            {error}
          </p>
        )}
        {blocked && (
          <p>
            Reload the latest record before making another change. An
            interrupted update may already have been saved.
          </p>
        )}
        <form
          className="intake-review"
          onSubmit={(event) => {
            event.preventDefault()
            ask(application ? null : status, event)
          }}
        >
          {!application && (
            <label>
              Status
              <select
                aria-label="Status"
                value={status}
                disabled={busy || blocked}
                onChange={(event) => setStatus(event.target.value)}
              >
                {Object.entries(type.statuses).map(([value, label]) => (
                  <option value={value} key={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Internal {application ? 'review' : 'handling'} note
            <textarea
              ref={noteField}
              value={note}
              maxLength={2000}
              rows={4}
              disabled={busy || blocked}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <p className="field-help">
            Notes are private to authorised school administrators. Maximum 2000
            characters.
          </p>
          <div className="intake-actions">
            {application ? (
              <>
                <button
                  type="button"
                  disabled={busy || blocked || record.status === 'approved'}
                  onClick={(event) => ask('approved', event)}
                >
                  Approve Application
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy || blocked || record.status === 'rejected'}
                  onClick={(event) => ask('rejected', event)}
                >
                  Reject Application
                </button>
                <button
                  type="submit"
                  className="secondary-button"
                  disabled={busy || blocked || !note.trim()}
                >
                  Save review note
                </button>
              </>
            ) : (
              <button
                type="submit"
                disabled={
                  busy || blocked || (status === record.status && !note.trim())
                }
              >
                Save enquiry update
              </button>
            )}
          </div>
        </form>
      </section>
      <History key={historyRevision} kind={kind} id={id} />
      {confirming && (
        <dialog
          className="intake-dialog"
          ref={dialog}
          aria-labelledby="intake-confirm-title"
          aria-describedby="intake-confirm-description"
          onCancel={(event) => {
            event.preventDefault()
            if (!lock.current) setConfirming(null)
          }}
        >
          <h2 id="intake-confirm-title">
            Confirm {type.singular.toLowerCase()} review
          </h2>
          <p id="intake-confirm-description">
            {record.reference}:{' '}
            {confirming.status
              ? `change status to ${type.statuses[confirming.status]}`
              : 'save the internal review note'}
            ?
          </p>
          {application && (
            <p>No student record or enrolment will be created.</p>
          )}
          <div className="intake-actions">
            {busy && (
              <p ref={savingStatus} role="status" tabIndex={0}>
                Saving review. Please wait.
              </p>
            )}
            <button
              type="button"
              className="secondary-button"
              disabled={busy}
              onClick={() => setConfirming(null)}
            >
              Cancel
            </button>
            <button type="button" disabled={busy} onClick={save}>
              {busy ? 'Saving...' : 'Confirm review'}
            </button>
          </div>
        </dialog>
      )}
    </main>
  )
}
function History({ kind, id }) {
  const [page, setPage] = useState(1),
    [revision, setRevision] = useState(0)
  return (
    <section className="profile-section">
      <h2>{kind === 'applications' ? 'Review history' : 'Handling history'}</h2>
      <button
        className="secondary-button"
        type="button"
        onClick={() => setRevision((value) => value + 1)}
      >
        Refresh history
      </button>
      <HistoryRows
        key={`${page}:${revision}`}
        kind={kind}
        id={id}
        page={page}
        changePage={setPage}
      />
    </section>
  )
}
function HistoryRows({ kind, id, page, changePage }) {
  const [data, setData] = useState(null),
    [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    intakeHistory(kind, id, page, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        if (!Array.isArray(result?.results))
          throw new Error('Invalid history response')
        setData(result)
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(intakeError(failure))
      })
    return () => controller.abort()
  }, [kind, id, page])
  if (error)
    return (
      <p className="form-error" role="alert">
        {error} Use Refresh history to try again.
      </p>
    )
  if (!data) return <p role="status">Loading history...</p>
  const statuses = intakeTypes[kind].statuses
  return (
    <>
      <div className="intake-history">
        {data.results.length ? (
          data.results.map((row) => (
            <article key={row.id}>
              <h3>
                {statuses[row.from_status]} to {statuses[row.to_status]}
              </h3>
              <p>
                {new Date(row.created_at).toLocaleString('en-GB', {
                  timeZone: 'Africa/Harare',
                })}{' '}
                | Administrator ID: {row.actor_id} | Version: {row.version}
              </p>
              <p className="intake-copy">{row.note || 'No note recorded.'}</p>
            </article>
          ))
        ) : (
          <p>No history has been recorded.</p>
        )}
      </div>
      <nav className="intake-pagination" aria-label="History pages">
        <button
          type="button"
          className="secondary-button"
          disabled={!data.previous}
          onClick={() => changePage(page - 1)}
        >
          Previous history page
        </button>
        <span>History page {page}</span>
        <button
          type="button"
          className="secondary-button"
          disabled={!data.next}
          onClick={() => changePage(page + 1)}
        >
          Next history page
        </button>
      </nav>
    </>
  )
}
