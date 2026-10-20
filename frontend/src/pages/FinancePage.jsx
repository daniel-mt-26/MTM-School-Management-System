import { Link } from 'react-router-dom'
import StudentFeeNavigation from '../components/StudentFeeNavigation'
import SchoolFinancialNavigation from '../components/SchoolFinancialNavigation'

const sections = [['balances', 'Student Balances', 'Review student financial profiles.'], ['ledger', 'Student Ledger', 'Read original student ledger history.'], ['cashbook', 'Legacy Daily Cashbook', 'Retained daily payment and expense view.'], ['reports', 'Legacy Balance Review', 'Retained student balance overview.']]
export default function FinancePage() {
  return <main className="student-page"><header className="student-page-header"><div><Link to="/school" className="dashboard-link">Back to School Dashboard</Link><h1>Finance</h1><p>Billed fees, actual cash collected and outstanding receivables are reported separately.</p></div></header>
    <section className="profile-section"><h2>Student Fee Management</h2><StudentFeeNavigation /></section>
    <section className="profile-section"><h2>School Financial Management</h2><SchoolFinancialNavigation /><Link to="/school/finance/cash-received">Cash Received Report</Link><p>Bank Reconciliation = FUTURE</p></section>
    <section className="dashboard-navigation">{sections.map(([path, title, copy]) => <Link key={path} to={`/school/finance/${path}`} className="dashboard-card"><h2>{title}</h2><p>{copy}</p></Link>)}</section>
  </main>
}
