import { Link } from 'react-router-dom'

const studentFeeSections = [
  ['fee-management', 'Fee Structures'], ['charges', 'Student Charges'], ['payments', 'Payments'],
  ['receipts', 'Receipts'], ['invoices', 'Invoices'], ['statements', 'Student Financial Statements'],
  ['outstanding', 'Outstanding Balances'], ['ageing', 'Ageing Debtors'],
]

export default function StudentFeeNavigation() {
  return <nav className="academic-filters statement-controls" aria-label="Student Fee Management">{studentFeeSections.map(([path, title]) => <Link key={path} to={`/school/finance/${path}`}>{title}</Link>)}</nav>
}
