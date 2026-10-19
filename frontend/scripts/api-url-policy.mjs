export function validateProductionApiUrl(value) {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error('Production builds require VITE_API_URL. Set it to / for the same-origin Cloudflare Worker or Nginx API proxy.')
  }
  if (value.trim() !== '/') {
    throw new Error('This deployment uses same-origin API requests. Set VITE_API_URL=/; external API origins require matching CORS and cross-site cookie configuration.')
  }
  return '/'
}
