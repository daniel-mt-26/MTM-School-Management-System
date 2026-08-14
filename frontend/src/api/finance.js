import { apiClient } from './client'
import { tokenStorage } from './auth'

function queryString(params = {}) { const query = new URLSearchParams(); Object.entries(params).forEach(([key, value]) => { if (value !== '' && value !== undefined && value !== null) query.set(key, value) }); return query.toString() ? `?${query}` : '' }
export const getFinanceRecords = (resource, params) => apiClient(`/school/${resource}/${queryString(params)}`)
export const saveFinanceRecord = (resource, data, id) => apiClient(`/school/${resource}/${id ? `${id}/` : ''}`, { method: id ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
export const assignFeeToClass = (data) => apiClient('/school/fee-assignments/assign-to-class/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
export const getBalances = (params) => apiClient(`/school/finance/balances/${queryString(params)}`)
export const getLedgerTotals = (params) => apiClient(`/school/ledger/totals/${queryString(params)}`)
export const getDailyCashbook = (date) => apiClient(`/school/finance/cashbook/${queryString({ date })}`)
export const getStudentFinance = (studentId) => apiClient(`/school/finance/students/${studentId}/`)
export const getParentStudentFinance = (studentId) => apiClient(`/parent/students/${studentId}/finance/`)
export const reversePayment = (paymentId, reason) => apiClient(`/school/payments/${paymentId}/reverse/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason }) })
export const generateRecurringFees = (month) => apiClient('/school/recurring-fees/generate/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ month }) })
export async function downloadReceiptPdf(receiptId, parent = false) { const base = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api'; const response = await fetch(`${base}/${parent ? 'parent' : 'school'}/receipts/${receiptId}/pdf/`, { headers: { Authorization: `Bearer ${tokenStorage.getAccess()}` } }); if (!response.ok) throw new Error('Receipt download failed'); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `receipt-${receiptId}.pdf`; link.click(); URL.revokeObjectURL(url) }
