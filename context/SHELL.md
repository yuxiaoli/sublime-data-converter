# Shell Environment

- **OS**: Windows
- **Shell**: PowerShell
- **Shell Version**: 5.1.26100.8457
- **Print `$PATH`**: `$env:PATH -split ';'`

## Notes

- Use `;` to chain commands (PS 5.1 does not support `&&`).
- Use `curl.exe` explicitly for HTTP requests; `curl` aliases to `Invoke-WebRequest`.
- Access env vars via `$env:VAR_NAME`; set via `$env:VAR_NAME = "value"`.
- Use `Remove-Item -Recurse -Force` for recursive deletion.
