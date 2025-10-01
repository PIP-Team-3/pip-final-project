# Security & Secrets Policy

This repository does not store production secrets. Treat all credentials as sensitive and follow the guidelines below.

## Server-side secrets
The following variables belong in server-only environments and **must never** be committed to the repo or exposed to the client:
- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Store these values in deployment platforms or local `.env` files that stay outside version control.

## Client-side configuration
Only the following value may be exposed to the web client when required:
- `SUPABASE_ANON_KEY`

When bundling the web application, ensure that no server-side secret is referenced or injected into client bundles.

## Reporting
If you discover a security issue or accidental secret leak, report it to the maintainers immediately and rotate the affected keys.
