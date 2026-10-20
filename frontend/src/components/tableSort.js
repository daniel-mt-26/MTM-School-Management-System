export function compareValues(a, b) {
  if (a == null || a === '') return b == null || b === '' ? 0 : 1
  if (b == null || b === '') return -1
  const left = String(a).trim(), right = String(b).trim()
  const numeric = value => /^(?:(?:USD|ZWL|ZAR)\s+)?[\s$€£]*-?[\d,.]+\s*%?$/.test(value) ? Number(value.replace(/[^\d.-]/g, '')) : NaN
  const x = numeric(left), y = numeric(right)
  if (Number.isFinite(x) && Number.isFinite(y)) return x - y
  if (/^\d{4}-\d{2}-\d{2}/.test(left) && /^\d{4}-\d{2}-\d{2}/.test(right)) return Date.parse(left) - Date.parse(right)
  return left.localeCompare(right, undefined, { numeric: true, sensitivity: 'base' })
}

export function sortRows(rows, getter, direction = 'asc') {
  return rows.map((row, index) => ({ row, index })).sort((a, b) => compareValues(getter(a.row), getter(b.row)) * (direction === 'asc' ? 1 : -1) || a.index - b.index).map(({ row }) => row)
}
