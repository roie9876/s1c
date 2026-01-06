# GitHub login HAR (redacted)

This folder contains a **redacted** HAR capture used only to document the **high-level OAuth redirect chain** for the Infinity Portal "Login with GitHub" option.

## Why this exists
It helps confirm that the portal uses a standard browser-based OAuth flow:
- Check Point gateway endpoint initiates the flow (`/oauth/github`)
- Browser is redirected to GitHub OAuth authorize UI
- GitHub continues to account selection/login

## What was removed
The redacted file intentionally removes or strips:
- Request/response headers (including any cookies)
- Request query strings and fragments (URLs are kept as `scheme://host/path` only)
- Request post bodies (`postData`)
- Response bodies (`content.text`)

## Source
Original capture was taken locally and should **not** be committed if it contains tokens/cookies.
Use the redacted file for sharing/versioning.
