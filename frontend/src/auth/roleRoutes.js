export const roleRoutes = {
  platform_admin: '/platform',
  school_admin: '/app',
  teacher: '/teacher',
  parent: '/parent',
}

export function routeForRole(role) {
  return roleRoutes[role] ?? '/login'
}
