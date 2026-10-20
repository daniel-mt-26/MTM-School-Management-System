import { Children, Fragment, cloneElement, isValidElement, useState } from 'react'
import { sortRows } from './tableSort.js'

function textOf(node) {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join(' ')
  if (isValidElement(node)) return node.props['data-sort-value'] ?? textOf(node.props.children)
  return ''
}

function flatChildren(node) {
  return Children.toArray(node).flatMap(child => isValidElement(child) && child.type === Fragment ? flatChildren(child.props.children) : [child])
}

export default function SortableTable({ children, ...props }) {
  const [sort, setSort] = useState({ column: -1, direction: 'asc' })
  const toggle = column => setSort(old => ({ column, direction: old.column === column && old.direction === 'asc' ? 'desc' : 'asc' }))
  const parts = Children.map(children, part => {
    if (!isValidElement(part)) return part
    if (part.type === 'thead') return cloneElement(part, {}, Children.map(part.props.children, row => !isValidElement(row) ? row : cloneElement(row, {}, flatChildren(row.props.children).map((cell, column) => {
      if (!isValidElement(cell) || cell.type !== 'th' || cell.props.colSpan || /action/i.test(textOf(cell))) return cell
      return cloneElement(cell, { 'aria-sort': sort.column === column ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none' }, <button className="sort-heading" type="button" onClick={() => toggle(column)}>{cell.props.children}{sort.column === column ? (sort.direction === 'asc' ? ' ▲' : ' ▼') : ''}</button>)
    }))))
    if (part.type === 'tbody' && sort.column >= 0) {
      const rows = flatChildren(part.props.children)
      return cloneElement(part, {}, sortRows(rows, row => isValidElement(row) ? textOf(flatChildren(row.props.children)[sort.column]) : '', sort.direction))
    }
    return part
  })
  return <table {...props}>{parts}</table>
}
