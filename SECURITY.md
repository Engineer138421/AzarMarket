# Security Policy

## Reporting a security issue

Please do not publish API keys, bot tokens, passwords, database files containing
private user data, or other secrets in GitHub Issues, Pull Requests, or public
commits.

If you discover a security vulnerability in Azar Market, report it privately
through the repository's configured security/contact channel.

## Secrets

Azar Market currently reads its runtime credentials from environment variables:

- `BOT_TOKEN`
- `GROQ_API_KEY`

The local file used by the current application is `gemini-code.env`. This file
must remain local and must never be committed to the public repository.

If a credential is accidentally committed:

1. Revoke/rotate the exposed credential immediately.
2. Remove it from the repository history if necessary.
3. Replace it with a new credential stored locally or in the deployment
   environment.
4. Check other logs, artifacts, and backups for the same secret.

## Local database

`market_history.db` is runtime data and is intentionally excluded from the
repository. A fresh installation can create its own SQLite database when the
application initializes it.

## Financial safety

Azar Market is a software project for market monitoring, information
aggregation, automation, and analysis. Its outputs are not financial,
investment, legal, or tax advice. Users are responsible for independently
verifying data and decisions.
