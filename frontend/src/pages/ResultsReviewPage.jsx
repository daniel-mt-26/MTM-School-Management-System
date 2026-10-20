import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient } from '../api/client'
import SortableTable from '../components/SortableTable.jsx'

export default function ResultsReviewPage() {
  const [items, setItems] = useState([])
  const [error, setError] = useState('')
  useEffect(() => { apiClient('/school/result-review/').then(setItems).catch(() => setError('Could not load results.')) }, [])
  async function transition(item, status) {
    try { await apiClient(`/school/result-review/${item.id}/transition/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) }); setItems(await apiClient('/school/result-review/')) }
    catch { setError('This workflow transition could not be completed.') }
  }
  async function correct(item) {
    const reason = window.prompt('Enter a reason for reopening this published result. The official version will be preserved and its report retracted until republished.')
    if (!reason) return
    try { await apiClient(`/school/result-review/${item.id}/correction/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason }) }); setItems(await apiClient('/school/result-review/')) }
    catch { setError('Correction failed. Provide a reason of at least 10 characters.') }
  }
  return <main className="student-page"><Link to="/app">Back to School Dashboard</Link><h1>Results Approval</h1>{error && <p role="alert">{error}</p>}<SortableTable className="student-table"><thead><tr><th>Student Name</th><th>Class</th><th>Subject</th><th>Average %</th><th>Status</th><th>Actions</th></tr></thead><tbody>{items.map(item => <tr key={item.id}><td>{item.student_name}</td><td>{item.class_name}</td><td>{item.subject_name}</td><td>{item.percentage}</td><td>{item.status}</td><td>{item.status === 'submitted' && <><button onClick={() => transition(item, 'approved')}>Approve</button><button onClick={() => transition(item, 'draft')}>Return for Correction</button></>}{item.status === 'approved' && <><button onClick={() => transition(item, 'published')}>Publish</button><button onClick={() => transition(item, 'draft')}>Return for Correction</button></>}{item.status === "published" && <button onClick={() => correct(item)}>Reopen for Correction</button>}</td></tr>)}</tbody></SortableTable></main>
}
