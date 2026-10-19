import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { validateProductionApiUrl } from './api-url-policy.mjs'

function parseEnvValue(content, key) {
  const line = content.split(/\r?\n/).find(row => row.trim().startsWith(`${key}=`))
  if (!line) return undefined
  const value = line.slice(line.indexOf('=') + 1).trim()
  return value.replace(/^(['"])(.*)\1$/, '$2')
}

let configured = process.env.VITE_API_URL
if (configured === undefined) {
  for (const name of ['.env.production.local', '.env.local', '.env.production']) {
    try {
      const candidate = parseEnvValue(await readFile(resolve(name), 'utf8'), 'VITE_API_URL')
      if (candidate !== undefined) { configured = candidate; break }
    } catch (error) {
      if (error?.code !== 'ENOENT') throw error
    }
  }
}

validateProductionApiUrl(configured)
