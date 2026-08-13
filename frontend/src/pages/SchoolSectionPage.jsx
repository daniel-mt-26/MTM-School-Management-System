import { Link } from 'react-router-dom'

export default function SchoolSectionPage({ title, description }) {
  return (
    <main className="school-section-page">
      <header className="school-section-header">
        <Link to="/school" className="dashboard-link">&larr; Back to School Dashboard</Link>
        <h1>{title}</h1>
      </header>

      <section className="school-section-content">
        <p>{description}</p>
      </section>
    </main>
  )
}
