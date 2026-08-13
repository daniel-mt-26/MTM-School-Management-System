import { apiClient } from './client'

export function getSchoolProfile() {
  return apiClient('/school/profile/')
}

export function updateSchoolProfile(profile, logo) {
  if (logo) {
    const formData = new FormData()
    Object.entries(profile).forEach(([key, value]) => formData.append(key, value))
    formData.append('logo', logo)
    return apiClient('/school/profile/', { method: 'PATCH', body: formData })
  }

  return apiClient('/school/profile/', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  })
}
