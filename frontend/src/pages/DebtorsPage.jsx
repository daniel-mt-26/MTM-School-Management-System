import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient, apiDownload } from '../api/client'
import StudentFeeNavigation from '../components/StudentFeeNavigation'
import SchoolLetterhead from '../components/SchoolLetterhead'

const buckets = [['not_due', 'Not Due'], ['days_0_30', '0–30 Days'], ['days_31_60', '31–60 Days'], ['days_61_90', '61–90 Days'], ['days_90_plus', '90+ Days']]
export default function DebtorsPage({ outstanding = false }) {
  const [filters, setFilters] = useState({ academic_year: '', term: '', school_class: '', reporting_date: '', search: '', sort: 'student_name' })
  const [data, setData] = useState(null), [error, setError] = useState('')
  const [loadedQuery, setLoadedQuery] = useState('')
  const base = `/school/finance/${outstanding ? 'outstanding' : 'ageing'}/`
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString()
  useEffect(() => { let active = true; apiClient(`${base}?${query}`).then(value => { if (active) { setData(value); setLoadedQuery(base + query); setError('') } }).catch(() => { if (active) { setData(null); setError('The debtor report could not be loaded.') } }); return () => { active = false } }, [base, query])
  const current = loadedQuery === base + query
  const set = (key, value) => setFilters(old => ({ ...old, [key]: value, ...(key === 'academic_year' ? { term: '' } : {}) }))
  const numeric = outstanding ? [['charges', 'Charges'], ['payments', 'Payments'], ['adjustments', 'Adjustments'], ['outstanding', 'Outstanding Balance']] : [['outstanding', 'Total Outstanding'], ...buckets]
  const columns = [['admission_number', 'Admission Number'], ['student_name', 'Student Name'], ['class_name', 'Class'], ['guardian', 'Parent / Guardian'], ...numeric]
  const sortColumn = key => set('sort', filters.sort === key ? `-${key}` : key)
  const money = value => `${data.currency} ${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  async function download(kind) { try { await apiDownload(`${base}?${query}&export=${kind}`, `debtors.${kind}`) } catch { setError('The report export failed.') } }
  return <main className="student-page"><Link to="/school/finance">Back to Finance</Link><h1>{outstanding ? 'Outstanding Balances' : 'Ageing Debtors'}</h1><StudentFeeNavigation />
    <div className="academic-filters statement-controls">{[['academic_year', 'Academic Year', data?.years || []], ['term', 'Term', (data?.terms || []).filter(x => !filters.academic_year || String(x.academic_year) === filters.academic_year)], ['school_class', 'Class / Grade', data?.classes || []]].map(([key, label, options]) => <label key={key}>{label}<select value={filters[key]} onChange={e => set(key, e.target.value)}><option value="">All</option>{options.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>)}
      <label>Reporting Date<input type="date" value={filters.reporting_date} onChange={e => set('reporting_date', e.target.value)} /></label><label>Search student<input value={filters.search} onChange={e => set('search', e.target.value)} /></label>
      <label>Sort by<select value={filters.sort} onChange={e => set('sort', e.target.value)}>{[['admission_number', 'Admission Number'], ['student_name', 'Student Name'], ['class_name', 'Class'], ['guardian', 'Guardian'], ...numeric].flatMap(([key, label]) => [<option key={key} value={key}>{label} ascending</option>, <option key={`-${key}`} value={`-${key}`}>{label} descending</option>])}</select></label>
      <button disabled={!data || !current} onClick={() => download('pdf')}>Export PDF</button><button disabled={!data || !current} onClick={() => download('xlsx')}>Export Excel</button><button disabled={!data || !current} onClick={() => window.print()}>Print</button>
    </div>{error && <p role="alert">{error}</p>}{data && current && <article className="statement-document"><SchoolLetterhead school={data.school} /><p>Reporting date: {data.reporting_date}</p><p>{data.note}</p><div className="student-table-wrap"><table className="student-table"><thead><tr>{columns.map(([key, label]) => <th key={key} aria-sort={filters.sort === key ? 'ascending' : filters.sort === `-${key}` ? 'descending' : 'none'}><button className="sort-heading" onClick={() => sortColumn(key)}>{label}</button></th>)}</tr></thead><tbody>{data.rows.map(row => <tr key={row.student}><td>{row.admission_number}</td><td><Link to={`/school/finance/students/${row.student}/statement`}>{row.student_name}</Link></td><td>{row.class_name}</td><td>{row.guardian}</td>{numeric.map(([key]) => <td key={key} data-sort-value={row[key]}>{money(row[key])}</td>)}</tr>)}</tbody><tfoot><tr><th colSpan="4">School totals for selected filters</th>{numeric.map(([key]) => <td key={key}>{money(data.totals[key])}</td>)}</tr></tfoot></table></div>{!data.rows.length && <p>No outstanding balances match these filters.</p>}<p>Charges represent billed income. Payments represent cash collected. Outstanding receivables are shown separately.</p></article>}</main>
}
