# Chatting Room live chat

A browser-based live chat using regular HTTP requests, file sharing, and SQLite persistence.

## Local development

Activate the workspace virtual environment and install dependencies:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Start the development server (bound to localhost):

```powershell
python server.py
```

Open http://127.0.0.1:5000 in multiple browser tabs. User names, profile photos, selected groups, chat messages, and uploaded file contents persist in SQLite. The browser keeps only an opaque HttpOnly session cookie; data saved in older browser storage is migrated to SQLite once and then cleared. Existing uploads from earlier versions remain readable from `uploads/`. The latest 50 room messages load when you enter a group. Stop the server with Ctrl+C.

## Production deployment

The app runs as a native Windows service through `pywin32`, with Waitress as its WSGI server. Chat updates use ordinary HTTP polling every 2.5 seconds; no client CDN or third-party runtime API is required. Keep the app behind a TLS-terminating reverse proxy such as IIS with URL Rewrite and ARR, and use one application process because online presence is held in process memory.

1. Install the project dependencies in the virtual environment and prepare persistent directories:

	```powershell
	.venv\Scripts\Activate.ps1
	pip install -r requirements.txt
	New-Item -ItemType Directory -Force data, logs | Out-Null
	Copy-Item .env.example .env
	```
2. Edit `.env` and set `DATABASE_PATH` / `UPLOAD_DIR` to absolute paths under the project directory and `COOKIE_SECURE=true` when requests use HTTPS. Flask creates its signing key at `data/.flask_secret_key` if `SECRET_KEY_FILE` is not set.

3. Open **PowerShell as Administrator**, change to the project directory, and install/start the service:

	```powershell
	$project = (Resolve-Path .).Path
	$python = Join-Path $project ".venv\Scripts\python.exe"
	& $python (Join-Path $project "windows_service.py") --startup auto install
	& $python (Join-Path $project "windows_service.py") start
	sc.exe failure ChatSystem reset= 86400 actions= restart/5000/restart/15000/restart/60000
	```

To run production in the current console instead of installing the service, use `.venv\Scripts\python.exe windows_service.py` after creating `.env`. Press Ctrl+C to stop it.

The service initially runs as LocalSystem. For routine use, open `services.msc`, select **Chat System > Properties > Log On**, and change it to a dedicated non-administrator account. Grant that account read/execute access to the project, modify access to `data` and `logs`, and read access to `.env`; restrict `.env` so only administrators and the service account can read it. The server listens on `127.0.0.1:5000`; configure the reverse proxy for TLS. `GET /healthz` reports whether the database can be reached. Back up `data` regularly.

From an elevated PowerShell in the project directory, control or remove the service with:

	```powershell
	$python = (Resolve-Path ".venv\Scripts\python.exe").Path
	& $python windows_service.py stop
	& $python windows_service.py start
	& $python windows_service.py restart
	& $python windows_service.py stop
	& $python windows_service.py remove
	```

Review `logs\chat-service.log` and the Windows Application event log when troubleshooting.

Do not use Flask's development server in production. Configure TLS, request-size limits, backups, and monitoring at the reverse proxy/hosting layer.

## Security and limits

This is still an anonymous guest chat, not a secure public community service. Names are user-selected and associated with an anonymous browser session; there are no accounts or authorization boundaries. Anyone able to reach it can create a session, create groups, post content, and upload files. Do not expose it to untrusted users until account authentication, authorization, rate limiting, moderation, and an abuse-response process are implemented.

## How it works

- Flask serves `templates/index.html` and the browser assets in `static/`.
- `static/chat.js` uses JSON HTTP endpoints for chat actions and polls for updates; no socket connection or external browser script is required.
- `database.py` stores users, opaque session-token hashes, profiles, groups, messages, and uploaded file bytes in SQLite with parameterized SQL and short-lived connections for handler-thread safety.
- File uploads are limited to 10 MB and image, PDF, TXT, and CSV extensions. New file contents are SQLite BLOBs; legacy files are read from `uploads/`. Chat offers previews where supported and a download action.
- `SECRET_KEY_FILE`, `DATABASE_PATH`, `UPLOAD_DIR`, `MAX_CONTENT_LENGTH`, `PORT`, `HOST`, `WAITRESS_THREADS`, and `COOKIE_SECURE` can be configured through `.env`. If `SECRET_KEY_FILE` is unset, Flask creates a stable signing key in `data/.flask_secret_key`.
- `static/session.js` migrates old local profile values to SQLite once and removes them from browser storage; thereafter the browser holds only an opaque HttpOnly cookie.
- The browser renders message text with `textContent`, rather than interpreting it as HTML.
