import { apiClient } from './client.js'

let profileRequest = null

export function getSchoolProfile() {
  if (!profileRequest) {
    profileRequest = apiClient('/school/profile/').finally(() => { profileRequest = null })
  }
  return profileRequest
}

export function searchSchool(query) {
  return apiClient(`/school/search/?q=${encodeURIComponent(query)}`)
}

export function updateSchoolProfile(profile, logo) {
  profileRequest = null
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
