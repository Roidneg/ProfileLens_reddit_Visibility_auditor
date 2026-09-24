# Security Policy

## Supported Version

The latest version on the `main` branch receives security fixes.

## Secrets

Never commit Reddit credentials, `.env`, or `.streamlit/secrets.toml`. If a
credential is exposed, revoke it through Reddit and rotate it immediately.

ProfileLens does not need a Reddit password. The optional live-comparison mode
uses approved, read-only Data API credentials through PRAW.

## Reporting a Vulnerability

Open a private GitHub security advisory when available. Do not include account
credentials, complete archived comment exports, or another person's sensitive
information in a public issue.
