import { describe, expect, it } from 'vitest'
import { validateProductionApiUrl } from '../scripts/api-url-policy.mjs'

describe('production API URL configuration', () => {
  it('accepts the explicit same-origin Worker or Nginx proxy path', () => {
    expect(validateProductionApiUrl('/')).toBe('/')
  })

  it('rejects missing and non-same-origin production URLs', () => {
    expect(() => validateProductionApiUrl(undefined)).toThrow(/require VITE_API_URL/)
    expect(() => validateProductionApiUrl('')).toThrow(/require VITE_API_URL/)
    expect(() => validateProductionApiUrl('http://localhost:8000')).toThrow(/same-origin API requests/)
    expect(() => validateProductionApiUrl('https://api.example.com')).toThrow(/same-origin API requests/)
  })
})
