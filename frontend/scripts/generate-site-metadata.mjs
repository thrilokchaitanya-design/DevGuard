import { writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const root = resolve('public')
const site = (process.env.VITE_SITE_URL || '').replace(/\/$/, '')
if (!site || !/^https:\/\//.test(site)) {
  await writeFile(resolve(root, 'robots.txt'), 'User-agent: *\nDisallow: /\n')
  await writeFile(resolve(root, 'sitemap.xml'), '<?xml version="1.0" encoding="UTF-8"?>\n<!-- Set VITE_SITE_URL to the verified HTTPS production origin to publish an indexable sitemap. -->\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>\n')
} else {
  const routes = ['/', '/about', '/contact', '/docs', '/privacy', '/terms']
  const entries = routes.map(path => `  <url><loc>${site}${path}</loc></url>`).join('\n')
  await writeFile(resolve(root, 'robots.txt'), `User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /login\nSitemap: ${site}/sitemap.xml\n`)
  await writeFile(resolve(root, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${entries}\n</urlset>\n`)
}
