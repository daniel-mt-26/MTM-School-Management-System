import { useState } from 'react'
import { Link } from 'react-router-dom'
import StudentPicker from '../components/StudentPicker'
import StudentFeeNavigation from '../components/StudentFeeNavigation'

export default function StudentStatementsPage() {
  const [student, setStudent] = useState(null)
  return <main className="student-page"><h1>Student Financial Statements</h1><StudentFeeNavigation /><StudentPicker selected={student} onChange={setStudent} />{student && <Link to={`/school/finance/students/${student.id}/statement`}>View statement for {student.display_name || student.first_name}</Link>}</main>
}
