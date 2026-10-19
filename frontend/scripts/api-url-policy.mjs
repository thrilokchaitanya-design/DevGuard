import { isIP } from 'node:net'

export function validateProductionApiUrl(value) {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error('Production builds require VITE_API_URL. Set it to / for a same-origin API proxy, or to the verified public HTTPS origin of the API service.')
  }
  const configured = value.trim()
  if (configured === '/') return '/'

  let url
  try {
    url = new URL(configured)
  } catch {
    throw new Error('VITE_API_URL must be / or a valid public HTTPS API origin, such as https://api.example.com.')
  }
  const host = url.hostname.toLowerCase()
  const isLocalHost = host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local') || host === 'localhost.localdomain'
  if (url.protocol !== 'https:' || url.username || url.password || url.port || (url.pathname !== '' && url.pathname !== '/') || url.search || url.hash || isLocalHost || isIP(host) || !host.includes('.')) {
    throw new Error('VITE_API_URL must be a public HTTPS origin only (no credentials, port, path, query, or fragment).')
  }
  return url.origin
}
