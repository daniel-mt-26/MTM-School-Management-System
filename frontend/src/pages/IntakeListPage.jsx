import SortableTable from '../components/SortableTable.jsx'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  intakeTypes,
  intakeError,
  listIntake,
  searchIntakePage,
} from '../api/intake'

export default function IntakeListPage({ kind }) {
  const type = intakeTypes[kind]
  const [status, setStatus] = useState(''),
    [page, setPage] = useState(1),
    [query, setQuery] = useState(''),
    [revision, setRevision] = useState(0)
  return (
    <main className="student-page intake-page">
      <header className="student-page-header">
        <div>
          <Link to="/school" className="dashboard-link">
            Back to School Dashboard
          </Link>
          <h1>{type.title} Management</h1>
          <p>Online-only records for your school.</p>
        </div>
      </header>
      <div className="student-filters intake-filters">
        <label>
          Search this page
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={
              kind === 'applications'
                ? 'Student name or application reference'
                : 'Sender name, subject or enquiry reference'
            }
          />
        </label>
        <label>
          Status
          <select
            aria-label="Status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value)
              setPage(1)
              setQuery('')
            }}
          >
            <option value="">All statuses</option>
            {Object.entries(type.statuses).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="secondary-button"
          onClick={() => setRevision((value) => value + 1)}
        >
          Refresh
        </button>
      </div>
      <p className="intake-help">
        Search applies only to the current page, not all server records. Status
        filters apply across your school's records.
      </p>
      <IntakeRows
        key={`${kind}:${status}:${page}:${revision}`}
        kind={kind}
        page={page}
        status={status}
        query={query}
        changePage={(value) => {
          setQuery('')
          setPage(value)
        }}
      />
    </main>
  )
}

function IntakeRows({ kind, page, status, query, changePage }) {
  const [data, setData] = useState(null),
    [error, setError] = useState('')
  const type = intakeTypes[kind]
  useEffect(() => {
    const controller = new AbortController()
    listIntake(kind, { page, status, signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return
        if (!Array.isArray(result?.results) || !Number.isInteger(result.count))
          throw new Error('Invalid list response')
        setData(result)
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(intakeError(failure))
      })
    return () => controller.abort()
  }, [kind, page, status])
  if (error)
    return (
      <section className="student-state" role="alert">
        <p>{error}</p>
        <p>Use Refresh to try again.</p>
      </section>
    )
  if (!data)
    return (
      <section className="student-state" role="status">
        Loading {type.title.toLowerCase()}...
      </section>
    )
  const rows = searchIntakePage(kind, data.results, query)
  const application = kind === 'applications'
  return (
    <>
      <div
        className="student-table-wrap"
        tabIndex={0}
        role="region"
        aria-label={`${type.title} records; scroll horizontally on small screens`}
      >
        <SortableTable className="student-table intake-table">
          <caption>
            {type.title}: page {page}, {data.count} total records in this status
            filter
          </caption>
          <thead>
            <tr>
              <th scope="col">Reference</th>
              <th scope="col">
                {application ? 'Student name' : 'Sender name'}
              </th>
              {application ? (
                <>
                  <th scope="col">Grade requested</th>
                  <th scope="col">Parent or guardian</th>
                </>
              ) : (
                <th scope="col">Subject</th>
              )}
              <th scope="col">Contact number</th>
              <th scope="col">Submitted</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <Link to={`${type.route}/${row.id}`}>{row.reference}</Link>
                </td>
                <td>{application ? row.student_name : row.full_name}</td>
                {application ? (
                  <>
                    <td>{row.grade}</td>
                    <td>{row.guardian_name}</td>
                  </>
                ) : (
                  <td>{row.subject}</td>
                )}
                <td>{row.phone}</td>
                <td>{formatIntakeDate(row.created_at)}</td>
                <td>
                  <span className={`status-badge intake-status ${row.status}`}>
                    {type.statuses[row.status] || row.status}
                  </span>
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td className="empty-cell" colSpan={application ? 7 : 6}>
                  {query
                    ? 'No matches on this page. Clear search or use another page.'
                    : `No ${type.title.toLowerCase()} are available in this status filter.`}
                </td>
              </tr>
            )}
          </tbody>
        </SortableTable>
      </div>
      <nav className="intake-pagination" aria-label={`${type.title} pages`}>
        <button
          type="button"
          className="secondary-button"
          disabled={!data.previous}
          onClick={() => changePage(page - 1)}
        >
          Previous page
        </button>
        <span>Page {page}</span>
        <button
          type="button"
          className="secondary-button"
          disabled={!data.next}
          onClick={() => changePage(page + 1)}
        >
          Next page
        </button>
      </nav>
    </>
  )
}

function formatIntakeDate(value) {
  return value
    ? new Date(value).toLocaleString('en-GB', { timeZone: 'Africa/Harare' })
    : 'Not recorded'
}
