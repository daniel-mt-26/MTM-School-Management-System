import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient, apiDownload } from '../api/client'

export default function ParentReportsPage() {
  const [cards, setCards] = useState([])
  const [error, setError] = useState('')
  useEffect(() => { apiClient('/parent/report-cards/').then(setCards).catch(() => setError('Published reports could not be loaded.')) }, [])
  return <main className="student-page"><Link to="/parent">Back to Parent Portal</Link><h1>Published Report Cards</h1>{error && <p role="alert">{error}</p>}{cards.map(card => <section className="profile-section" key={card.id}><h2>{card.student_name} · {card.term_name}</h2>{card.comments.map((comment, i) => <p key={i}>{comment}</p>)}{card.download_url && <button onClick={() => apiDownload(card.download_url, `report-card-${card.id}.pdf`).catch(() => setError('Report download failed.'))}>Download Report Card</button>}</section>)}{!cards.length && <p>No published report cards are available.</p>}</main>
}
