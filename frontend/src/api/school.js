import { apiClient } from './client'

export function getSchoolProfile() {
  return apiClient('/school/profile/')
}
