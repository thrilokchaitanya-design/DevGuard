import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import SitePages from './pages'
import Dashboard from './App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})

describe('public site routes', () => {
  it('renders a truthful product landing page and sign-in entry point', () => {
    window.history.replaceState({}, '', '/')
    render(<MemoryRouter initialEntries={['/']}><SitePages /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: /Understand the failure/i })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /open workspace/i }).every(link => link.getAttribute('href') === '/app')).toBe(true)
  })

  it('renders the contact route with the configured public profiles', () => {
    window.history.replaceState({}, '', '/contact')
    render(<MemoryRouter initialEntries={['/contact']}><SitePages /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: /Get in touch/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /GitHub profile/i })).toHaveAttribute('href', 'https://github.com/thrilokchaitanya-design')
  })

  it('renders the documentation route', () => {
    window.history.replaceState({}, '', '/docs')
    render(<MemoryRouter initialEntries={['/docs']}><SitePages /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: /Run DevGuard in your own environment/i })).toBeInTheDocument()
    expect(screen.getByText(/live demo runs on Cloudflare Workers with Cloudflare D1/i)).toBeInTheDocument()
  })

  it('shows an offline state if the API session cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('API unavailable')))
    render(<MemoryRouter initialEntries={['/app']}><Dashboard /></MemoryRouter>)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/Cannot connect to the DevGuard API/i))
    expect(screen.getByRole('alert')).not.toHaveTextContent(/\[object Object\]|port 8000/i)
  })
})
