# Production handover checklist

Complete these checks with the system owner after MVP acceptance.

- Remove test accounts, destinations, tokens and passwords.
- Generate a new owner-controlled `SECRET_KEY`. Set the administrator's initial password and store only its Argon2 hash.
- [x] The password-change flow checks the current password, confirms the replacement, validates CSRF and invalidates previous sessions.
- Rotate provider and bot credentials and check Git, logs and screenshots for accidental exposure.
- Deploy with HTTPS, secure cookies and `DEBUG=false`.
- Restrict filesystem access to environment files, the database and private media.
- Test restoration of the database and uploaded files from backup.
- Review bot permissions, channel destinations, approval mode and the emergency publishing pause.
- Run the test suite and complete a controlled publishing check using owner-managed accounts.
