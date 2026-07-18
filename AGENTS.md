# Project notes

Keep the server localhost-only and preserve Python 3.9 compatibility. Never log secrets or add telemetry, runtime CDNs, generic file tools, or generic shell tools. Keep REST mutations and MCP tools typed and return `{success, data, summary, error}` shaped responses. Preserve user SQLite data through migrations. Run `scripts/test.ps1` before publishing changes, and update the GitHub Actions matrix when supported Python versions change.
