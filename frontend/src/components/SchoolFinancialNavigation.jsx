import { Link } from 'react-router-dom'

export default function SchoolFinancialNavigation() {
  return <nav className="academic-filters statement-controls" aria-label="School Financial Management">{[
    ['income', 'Income Records'], ['expenses', 'Expenses'], ['cash-books', 'Cash Books'],
    ['monthly', 'Monthly Financial Reports'], ['annual', 'Annual Financial Reports'], ['financial-dashboard', 'Financial Dashboard'],
  ].map(([path, title]) => <Link key={path} to={`/school/finance/${path}`}>{title}</Link>)}<Link to="/school/finance/configuration">Accounts and Categories</Link></nav>
}
