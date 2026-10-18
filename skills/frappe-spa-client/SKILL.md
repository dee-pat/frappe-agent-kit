---
name: frappe-spa-client
description: Call Frappe whitelisted methods from a frappe-ui or Vue SPA and test that client. Use when building, changing or testing a frappe-ui / Vue single-page app that calls `/api/method` endpoints, maps their errors, or handles session expiry.
---

# Frappe SPA client

Rules for a frappe-ui / Vue SPA that calls a Frappe v16 app's whitelisted
methods through `/api/method/<dotted.path>`.

## Requests

- Write a small `fetch` wrapper per endpoint rather than frappe-ui's `useCall`.
  `useCall` drops the HTTP status, and v1 `/api/method` errors carry only
  `exc_type` (not frappe-ui's `errors[]`), so the client cannot tell a 401 from
  a server error, least of all over HTTP/2, which has no status text.
- Map the HTTP status first and `exc_type` second:
  1. 401, or `exc_type` `AuthenticationError`: session expired.
  2. 403, or `exc_type` `PermissionError`: denied. Frappe's v1 dispatcher
     rejects Guest with a `PermissionError` before the endpoint runs, so a 403
     while `document.cookie` holds `user_id=Guest` is session expiry; redirect
     to `/login?redirect-to=<current route>`.
  3. Anything else, a non-JSON body, a network failure or a success without
     `data` (or `message`, whichever the endpoint returns): a generic error.
  Throw an error class that carries only the mapped status behind a generic
  message; never show server text to the user.
- Send `X-Frappe-CSRF-Token` from `window.csrf_token` on every non-GET request,
  and skip it when the page left the `{{ csrf_token }}` placeholder unrendered.
  Send `X-Frappe-Site-Name: window.location.hostname` so the Vite dev proxy
  routes to the right site; send `Accept: application/json`.
- Build the query from defined parameters only, in snake_case, and send no
  query string when there are none.
- One `fetch` per call, with no shared resource object, so a failure can never
  return an earlier response's data.
- In a composable, take a per-request token (`const id = ++latest`) before
  awaiting, and drop the response, the error and the `loading` reset when
  `id !== latest`, so a stale response cannot overwrite newer state.

## Unit tests with Vitest

- Pin the Vitest 3.2.x line for Vite 5; Vitest 4 needs Vite 6 or newer. Check
  the ranges before pinning: `npm view vitest@<version> dependencies.vite
  peerDependencies`.
- Run in the `node` environment by default. Add `happy-dom` as a dev
  dependency and opt in per file with `// @vitest-environment happy-dom` only
  for composable tests that mount a Vue app.
- Test a composable that uses lifecycle hooks with the `withSetup` host-app
  pattern from Vue's composable testing guide: create an app whose `setup`
  calls the composable, mount it on a detached element, and unmount it in
  `afterEach`.
- Stub `fetch`, `window` and `document` with `vi.stubGlobal`, and set
  `clearMocks`, `restoreMocks` and `unstubGlobals` in `vitest.config.ts`.
  Return real `Response` objects, with v1 bodies such as
  `{ exc_type: "PermissionError", _server_messages: "[]" }`.
- Cover: each status mapping with and without status text, the Guest 403, the
  `exc_type` fallback, non-JSON and network failures, the CSRF placeholder,
  a failure after a success, and an older response resolving after a newer
  one, using deferred promises.
- Fix the clock's zone and locale in the test script so formatting tests agree
  everywhere: `"test": "TZ=UTC LC_ALL=en_GB.UTF-8 vitest run"`.
