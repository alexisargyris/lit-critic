# API Reference

Complete REST API documentation for the lit-critic FastAPI backend.

**Base URL:** `http://localhost:8000/api` (default)

---

## Overview

The lit-critic backend exposes a REST API that all interfaces (Web UI, VS Code Extension) use for communication. The CLI uses direct Python imports but could also use this API.

### Authentication

Currently, the API key is passed in request bodies (not in headers). This is suitable for local-only deployment.

### Content Type

All requests and responses use `application/json` unless otherwise specified.

---

## Endpoints

### Configuration

#### `GET /api/config`

Get available models and configuration.

**Request:** None

**Response:**
```json
{
  "api_key_configured": true,
  "api_keys_configured": {
    "anthropic": true,
    "openai": false
  },
  "available_models": {
    "opus": {"label": "Opus 4.6 (deepest analysis)", "provider": "anthropic"},
    "sonnet": {"label": "Sonnet 4.5 (balanced)", "provider": "anthropic"},
    "haiku": {"label": "Haiku 4.5 (fast & cheap)", "provider": "anthropic"},
    "gpt-4o": {"label": "GPT-4o (balanced)", "provider": "openai"},
    "gpt-4o-mini": {"label": "GPT-4o Mini (fast & cheap)", "provider": "openai"},
    "o3": {"label": "o3 (reasoning)", "provider": "openai"}
  },
  "default_model": "sonnet"
}
```

**Status Codes:**
- `200 OK` Success

---

### Analysis

#### `POST /api/analyze`

Start a new analysis session.

**Request Body:**
```json
{
  "scene_path": "/path/to/scene.txt",
  "project_path": "/path/to/project/",
  "api_key": "sk-ant-...",
  "model": "sonnet"
}
```

**Fields:**
- `scene_path` (string, required) — Absolute path to scene file
- `project_path` (string, required) — Absolute path to project directory
- `api_key` (string, optional) — API key for the model's provider. If omitted, resolved from environment (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`)
- `model` (string, optional) — Model short name (default: "sonnet"). See `GET /api/config` for available models

**Response:**
```json
{
  "status": "success",
  "total_findings": 12,
  "summary": {
    "prose": {"critical": 1, "major": 2, "minor": 3},
    "structure": {"critical": 0, "major": 1, "minor": 1},
    "coherence": {"critical": 0, "major": 2, "minor": 2}
  },
  "current_finding": {
    "number": 1,
    "severity": "critical",
    "lens": "prose",
    "location": "L042-L045",
    "line_start": 42,
    "line_end": 45,
    "evidence": "The sentence spans 47 words...",
    "impact": "Readers may lose track...",
    "options": ["Break into two sentences", "..."],
    "flagged_by": ["prose"],
    "status": "pending"
  }
}
```

**Status Codes:**
- `200 OK` Analysis started successfully
- `400 Bad Request` Invalid request (missing fields, invalid paths)
- `500 Internal Server Error` Analysis failed

---

#### `GET /api/analyze/progress`

Stream analysis progress via Server-Sent Events (SSE).

**Request:** None (use after starting analysis)

**Response:** SSE stream

**Event Types:**

**1. Lens Progress**
```
event: lens_complete
data: {"lens": "prose", "message": "✓ prose lens complete"}
```

**2. Coordinator Progress**
```
event: coordinator
data: {"message": "Coordinating prose findings..."}
```

**3. Status Updates**
```
event: status
data: {"message": "Running 5 lenses in parallel..."}
```

**4. Warnings**
```
event: warning
data: {"message": "Coordinator chunk 'structure' failed: ..."}
```

**5. Completion**
```
event: complete
data: {"total_findings": 12}
```

**Status Codes:**
- `200 OK` Streaming started
- `404 Not Found` No active analysis

---

### Session Management

#### `POST /api/resume`

Resume a previously saved session.

**Request Body:**
```json
{
  "project_path": "/path/to/project/",
  "api_key": "sk-ant-...",
  "scene_path_override": "/path/to/moved/scene.txt"
}
```

**Fields:**
- `project_path` (string, required) — Absolute path to project directory
- `api_key` (string, optional) — API key for the analysis model provider. If omitted, resolved from environment
- `discussion_api_key` (string, optional) — API key for the discussion model provider when it differs from analysis provider
- `scene_path_override` (string, optional) — Correct scene path to use when the saved path no longer exists (e.g., project moved to another machine)

**Response:**
```json
{
  "status": "success",
  "message": "Session resumed",
  "total_findings": 12,
  "current_index": 5,
  "current_finding": { /* Finding object */ }
}
```

**Status Codes:**
- `200 OK` Session resumed
- `404 Not Found` No session file found
- `400 Bad Request` Session validation failed (scene modified)
- `409 Conflict` Saved scene path not found; response includes structured detail for recovery UIs

**409 Error Example:**
```json
{
  "detail": {
    "code": "scene_path_not_found",
    "message": "Saved scene file was not found. Provide scene_path_override to relink this session.",
    "saved_scene_path": "D:/old-machine/project/ch01.md",
    "attempted_scene_path": "D:/old-machine/project/ch01.md",
    "project_path": "D:/new-machine/project",
    "override_provided": false
  }
}
```

---

#### `POST /api/check-session`

Check if a saved session exists without loading it.

**Request Body:**
```json
{
  "project_path": "/path/to/project/"
}
```

**Response:**
```json
{
  "exists": true,
  "scene_path": "/path/to/scene.txt",
  "current_finding": 5,
  "total_findings": 12
}
```

**Status Codes:**
- `200 OK` Check complete

---

#### `GET /api/session`

Get current session information.

**Request:** None

**Response:**
```json
{
  "total_findings": 12,
  "current_index": 5,
  "skip_minor": false,
  "model": "sonnet",
  "scene_path": "/path/to/scene.txt",
  "project_path": "/path/to/project/"
}
```

**Status Codes:**
- `200 OK` Success
- `404 Not Found` No active session

---

### Session History and Management

#### `GET /api/sessions`

List all sessions for a project (active, completed, abandoned).

**Query Parameters:**
- `project_path` (string, required) — Path to project directory

**Request:** None

**Response:**
```json
{
  "sessions": [
    {
      "id": 3,
      "scene_path": "/path/to/scene.txt",
      "model": "sonnet",
      "status": "completed",
      "created_at": "2026-02-09T10:30:00",
      "completed_at": "2026-02-09T10:45:00",
      "total_findings": 12,
      "accepted_count": 5,
      "rejected_count": 3,
      "withdrawn_count": 1
    },
    {
      "id": 2,
      "scene_path": "/path/to/scene2.txt",
      "model": "opus",
      "status": "active",
      "created_at": "2026-02-09T09:00:00",
      "total_findings": 0
    }
  ]
}
```

**Status Codes:**
- `200 OK` Success
- `404 Not Found` Project directory not found

---

#### `GET /api/sessions/{session_id}`

Get detailed information about a specific session, including all findings.

This endpoint returns the persisted per-finding discussion thread so clients
can hydrate both active and historical views with full discussion context.

**Path Parameters:**
- `session_id` (int, required) — Session ID

**Query Parameters:**
- `project_path` (string, required) — Path to project directory

**Request:** None

**Response:**
```json
{
  "session": {
    "id": 3,
    "scene_path": "/path/to/scene.txt",
    "scene_hash": "abc123...",
    "model": "sonnet",
    "status": "completed",
    "created_at": "2026-02-09T10:30:00",
    "completed_at": "2026-02-09T10:45:00",
    "total_findings": 12,
    "accepted_count": 5,
    "rejected_count": 3,
    "withdrawn_count": 1
  },
  "findings": [
    {
      "number": 1,
      "severity": "major",
      "lens": "prose",
      "location": "L042-L045",
      "evidence": "...",
      "status": "accepted",
      "discussion_turns": [
        {"role": "user", "content": "I intended this ambiguity."},
        {"role": "assistant", "content": "Understood; revising severity."}
      ],
      "revision_history": [],
      "author_response": "",
      "outcome_reason": ""
    }
  ]
}
```

**Status Codes:**
- `200 OK` Success
- `404 Not Found` Project directory not found
- `404 Not Found` Session not found

---

#### `DELETE /api/sessions/{session_id}`

Delete a session and all its findings.

**Path Parameters:**
- `session_id` (int, required) — Session ID

**Query Parameters:**
- `project_path` (string, required) — Path to project directory

**Request:** None

**Response:**
```json
{
  "deleted": true,
  "session_id": 3
}
```

**Status Codes:**
- `200 OK` Session deleted
- `404 Not Found` Session not found

---

### Learning Data Management

#### `GET /api/learning`

Get all learning data for a project.

**Query Parameters:**
- `project_path` (string, required) — Path to project directory

**Request:** None

**Response:**
```json
{
  "id": 1,
  "project_name": "My Novel",
  "review_count": 12,
  "preferences": [
    {"id": 1, "description": "Author uses sentence fragments for pacing", "created_at": "2026-02-09T10:00:00"}
  ],
  "blind_spots": [
    {"id": 2, "description": "Author misses filter words", "created_at": "2026-02-09T10:05:00"}
  ],
  "resolutions": [],
  "ambiguity_intentional": [],
  "ambiguity_accidental": []
}
```

**Status Codes:**
- `200 OK` Success
- `404 Not Found` Project directory not found

---

#### `POST /api/learning/export`

Export learning data to LEARNING.md file.

**Request Body:**
```json
{
  "project_path": "/path/to/project/"
}
```

**Response:**
```json
{
  "exported": true,
  "path": "/path/to/project/LEARNING.md"
}
```

**Status Codes:**
- `200 OK` Exported successfully

---

#### `DELETE /api/learning`

Reset all learning data for a project (deletes all entries).

**Query Parameters:**
- `project_path` (string, required) — Path to project directory

**Request:** None

**Response:**
```json
{
  "reset": true
}
```

**Status Codes:**
- `200 OK` Learning data reset

---

#### `DELETE /api/learning/entries/{entry_id}`

Delete a single learning entry.

**Path Parameters:**
- `entry_id` (int, required) — Entry ID

**Query Parameters:**
- `project_path` (string, required) — Path to project directory

**Request:** None

**Response:**
```json
{
  "deleted": true,
  "entry_id": 5
}
```

**Status Codes:**
- `200 OK` Entry deleted
- `404 Not Found` Entry not found

---

### Scene Content

#### `GET /api/scene`

Get the current scene content.

**Request:** None

**Response:**
```json
{
  "content": "@@META\nID: 01.03.01\n..."
}
```

**Status Codes:**
- `200 OK` Success
- `404 Not Found` No active session

---

### Finding Navigation

#### `GET /api/finding`

Get the current finding.

**Request:** None

**Response:**
```json
{
  "number": 5,
  "severity": "major",
  "lens": "structure",
  "location": "L042-L045",
  "line_start": 42,
  "line_end": 45,
  "evidence": "...",
  "impact": "...",
  "options": ["...", "..."],
  "flagged_by": ["structure"],
  "status": "pending",
  "stale": false,
  "discussion_turns": [],
  "revision_history": []
}
```

**Status Codes:**
- `200 OK` Success
- `404 Not Found` No current finding (review complete or no session)

---

#### `POST /api/finding/continue`

Advance to the next finding.

**Request:** None

**Response:**
```json
{
  "status": "advanced",
  "scene_changed": false,
  "current_finding": { /* Finding object */ }
}
```

**If review is complete:**
```json
{
  "status": "complete",
  "message": "All findings reviewed"
}
```

**If scene changed:**
```json
{
  "status": "advanced",
  "scene_changed": true,
  "adjusted": 8,
  "stale": 2,
  "re_evaluated": [
    {"finding_number": 5, "status": "updated"},
    {"finding_number": 7, "status": "withdrawn", "reason": "..."}
  ],
  "current_finding": { /* Finding object */ }
}
```

**Status Codes:**
- `200 OK` Success
- `404 Not Found` No active session

---

#### `POST /api/finding/goto`

Jump to a specific finding by index.

**Request Body:**
```json
{
  "index": 5
}
```

**Response:**
```json
{
  "status": "success",
  "scene_changed": false,
  "current_finding": { /* Finding object */ }
}
```

**Status Codes:**
- `200 OK` Success
- `400 Bad Request` Invalid index
- `404 Not Found` No active session

---

### Finding Actions

#### `POST /api/finding/accept`

Accept the current finding.

**Request:** None

**Response:**
```json
{
  "status": "accepted",
  "next_finding": { /* Finding object */ }
}
```

**Status Codes:**
- `200 OK` Accepted
- `404 Not Found` No current finding

---

#### `POST /api/finding/reject`

Reject the current finding with optional reason.

**Request Body:**
```json
{
  "reason": "Intentional repetition for emphasis"
}
```

**Fields:**
- `reason` (string, optional) — Why you rejected it

**Response:**
```json
{
  "status": "rejected",
  "next_finding": { /* Finding object */ }
}
```

**Status Codes:**
- `200 OK` Rejected
- `404 Not Found` No current finding

---

#### `POST /api/finding/ambiguity`

Mark ambiguity finding as intentional or accidental.

**Request Body:**
```json
{
  "intentional": true
}
```

**Response:**
```json
{
  "status": "marked",
  "next_finding": { /* Finding object */ }
}
```

**Status Codes:**
- `200 OK` Marked
- `400 Bad Request` Not an ambiguity finding
- `404 Not Found` No current finding

---

### Discussion

#### `POST /api/finding/discuss`

Discuss the current finding (non-streaming).

**Request Body:**
```json
{
  "message": "This repetition is intentional for emphasis"
}
```

**Response:**
```json
{
  "response": "I understand your intent, but three occurrences...",
  "finding_updated": true,
  "changes": {
    "severity": "minor",
    "status": "revised"
  }
}
```

**Status Codes:**
- `200 OK` Discussion completed
- `404 Not Found` No current finding
- `500 Internal Server Error` Claude API error

---

#### `POST /api/finding/discuss/stream`

Discuss the current finding (streaming via SSE).

**Request Body:**
```json
{
  "message": "Why is this a problem?"
}
```

**Response:** SSE stream

**Event Types:**

**1. Token Stream**
```
event: token
data: {"token": "The "}
```

**2. Complete**
```
event: complete
data: {
  "full_response": "The sentence is 47 words...",
  "finding_updated": true,
  "changes": {"severity": "minor", "status": "revised"},
  "finding": {
    "number": 5,
    "status": "revised",
    "discussion_turns": [
      {"role": "user", "content": "Why is this a problem?"},
      {"role": "assistant", "content": "Because it interrupts pacing..."}
    ]
  }
}
```

`discussion_turns` is canonical backend state: clients should re-render from
this array after a discussion completes so active and historical views stay in sync.

**3. Error**
```
event: error
data: {"error": "Claude API error: ..."}
```

**Status Codes:**
- `200 OK` Streaming started
- `404 Not Found` No current finding

---

### Bulk Actions

#### `POST /api/skip/minor`

Skip all remaining minor-severity findings.

**Request:** None

**Response:**
```json
{
  "status": "skipped",
  "skipped_count": 5,
  "current_finding": { /* Next non-minor finding */ }
}
```

**Status Codes:**
- `200 OK` Skipped
- `404 Not Found` No active session

---

#### `POST /api/skip/{lens}`

Skip to the next finding from a specific lens.

**Path Parameters:**
- `lens` (string) — One of: `prose`, `structure`, `logic`, `clarity`, `continuity`

**Request:** None

**Response:**
```json
{
  "status": "skipped",
  "current_finding": { /* First finding from target lens */ }
}
```

**Status Codes:**
- `200 OK` Skipped
- `404 Not Found` No findings from target lens
- `400 Bad Request` Invalid lens name

---

### Learning

#### `POST /api/learning/save`

Save LEARNING.md to project directory.

**Request:** None

**Response:**
```json
{
  "status": "success",
  "path": "/path/to/project/LEARNING.md",
  "preferences_count": 12
}
```

**Status Codes:**
- `200 OK` Saved
- `404 Not Found` No active session

---

## Data Models

### Finding Object

```typescript
interface Finding {
  number: number;
  severity: "critical" | "major" | "minor";
  lens: "prose" | "structure" | "logic" | "clarity" | "continuity";
  location: string;                    // e.g., "L042-L045"
  line_start: number | null;           // 1-based line number
  line_end: number | null;
  evidence: string;
  impact: string;
  options: string[];                   // Suggestions for fixing
  flagged_by: string[];                // List of lenses that flagged this
  ambiguity_type: string | null;       // For clarity findings
  stale: boolean;                      // True if scene was edited
  
  // Discussion state
  status: "pending" | "accepted" | "rejected" | "revised" | "withdrawn" | "escalated" | "discussed";
  author_response: string;
  discussion_turns: {role: string, content: string}[];
  revision_history: RevisionRecord[];
  outcome_reason: string;
}
```

### Revision Record

```typescript
interface RevisionRecord {
  timestamp: string;
  reason: string;
  old_severity: string;
  new_severity: string;
  old_evidence: string;
  new_evidence: string;
}
```

### Summary Object

```typescript
interface Summary {
  prose: {critical: number, major: number, minor: number};
  structure: {critical: number, major: number, minor: number};
  coherence: {critical: number, major: number, minor: number};
}
```

---

## Error Handling

### Standard Error Response

```json
{
  "detail": "Error message here"
}
```

### Common HTTP Status Codes

- `200 OK` Request succeeded
- `400 Bad Request` Invalid request (missing fields, invalid values)
- `404 Not Found` Resource not found (no session, no finding, etc.)
- `500 Internal Server Error` Server-side error (Claude API failure, file I/O error)

---

## Server-Sent Events (SSE)

Two endpoints use SSE for streaming:

1. `/api/analyze/progress` Analysis progress
2. `/api/finding/discuss/stream` Discussion responses

### SSE Format

```
event: <event_type>
data: <json_payload>

```

### Client Example (JavaScript)

```javascript
const eventSource = new EventSource('/api/analyze/progress');

eventSource.addEventListener('lens_complete', (event) => {
  const data = JSON.parse(event.data);
  console.log(`Lens ${data.lens} complete`);
});

eventSource.addEventListener('complete', (event) => {
  const data = JSON.parse(event.data);
  console.log(`Analysis complete: ${data.total_findings} findings`);
  eventSource.close();
});
```

---

## Rate Limiting

No rate limiting is currently implemented. The API is designed for local use only.

---

## CORS

CORS is enabled for all origins in development. For production deployment, configure `allow_origins` in `web/app.py`.

---

## Deployment Notes

### Local Development

```bash
python lit-critic-web.py --reload
```

### Production

Not recommended for public deployment without:
- API key security (move to headers/environment)
- Authentication/authorization
- Rate limiting
- HTTPS/TLS

---

## See Also

- **[Architecture Guide](architecture.md)** System design and data flow
- **[Testing Guide](testing.md)** API testing
- **[Installation Guide](installation.md)** Setup for development
