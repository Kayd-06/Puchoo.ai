# Public domain metadata

Puchoo.si does not yet have a owned public domain. Until one is chosen and DNS is pointed at the deployment:

- Do not hardcode `canonical`, `og:url`, or absolute sitemap URLs in `frontend/index.html`, `frontend/public/robots.txt`, or structured data.
- After a domain is ready, add those fields back with the real origin (for example `https://example.com/`), publish a `sitemap.xml` for the public marketing routes, and reference it from `robots.txt`.
- Keep authenticated product routes (`/ask`, `/connect`, `/history`, `/settings`, and account forms) out of the sitemap.
