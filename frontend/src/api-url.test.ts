import { describe, expect, it } from 'vitest'
import { validateProductionApiUrl } from '../scripts/api-url-policy.mjs'

describe('production API URL configuration', () => {
  it('accepts the explicit same-origin Worker or Nginx proxy path', () => {
    expect(validateProductionApiUrl('/')).toBe('/')
  })

  it('accepts a public HTTPS API origin', () => {
    expect(validateProductionApiUrl('https://api.example.com/')).toBe('https://api.example.com')
    expect(validateProductionApiUrl('https://devguard-api.onrender.com')).toBe('https://devguard-api.onrender.com')
  })

  it('rejects missing, insecure, local, and malformed production URLs', () => {
    expect(() => validateProductionApiUrl(undefined)).toThrow(/require VITE_API_URL/)
    expect(() => validateProductionApiUrl('')).toThrow(/require VITE_API_URL/)
    expect(() => validateProductionApiUrl('http://api.example.com')).toThrow(/public HTTPS origin/)
    expect(() => validateProductionApiUrl('https://localhost:8000')).toThrow(/public HTTPS origin/)
    expect(() => validateProductionApiUrl('https://127.0.0.1')).toThrow(/public HTTPS origin/)
    expect(() => validateProductionApiUrl('https://api.example.com/api')).toThrow(/public HTTPS origin/)
    expect(() => validateProductionApiUrl('https://user:pass@api.example.com')).toThrow(/public HTTPS origin/)
  })
})
