# Safety and Poka-Yoke

## Hard-Coding

- Do not hard-code values without a reason.
- Treat secrets, credentials, deployment URLs, identifiers, dates, money values, timeouts, retry limits, permissions, and file paths as configuration or contract data unless they are fixed by design.
- If a value is fixed by design, name it as a constant and explain why it is fixed.
- Keep values that may change in config, environment, or data files instead of scattering them through code.

## Guardrails

- Fail fast on malformed or unexpected input.
- Validate risky data before expensive work, allocation, or side effects.
- Prefer reversible or idempotent steps for destructive flows when possible.

## Debug and Temporary Code

- Do not leave debug logs, debug statements, commented-out code, or temporary bypasses behind.
- Do not keep TODOs that are really unfinished work.

## Exception Handling

- Do not broadly catch and silently discard exceptions.
- If an exception must be ignored, identify the exact exception, explain why ignoring it is safe, decide whether it must be logged, and preserve propagation for unexpected failures.

## Security and External Risk

- Do not guess on authentication, authorization, sessions, cookies, CSRF, XSS, SQL injection, SSRF, CORS, encryption, tokens, API keys, secrets, billing, payments, or money-related behavior.
- Treat personal data, file uploads, external URLs, webhooks, admin operations, and sensitive logs as high-risk surfaces.
- Verify before changing behavior in security-sensitive areas.

## Dependency Rule

- Add new dependencies only when the need is clear and the maintenance and security cost are acceptable.
- Prefer the standard library or existing project tools first.
- Before adding one, check its maintenance status, license, known security risk, bundle or runtime impact, and testability.
- Explain the reason for any new dependency and its relevant tradeoffs in the final report.

