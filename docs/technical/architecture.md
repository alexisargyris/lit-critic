This document provides a technical overview of the lit-critic system architecture.

---

## System Overview

lit-critic is a **multi-lens editorial review system** for fiction manuscripts. It uses LLM providers (Anthropic Claude, OpenAI GPT/o-series) to analyze novel scenes through five specialized "lenses," then coordinates the results into prioritized findings that authors review interactively.

### Key Design Principles

1. **Shared Backend** All interfaces (CLI, Web UI, VS Code) use the same FastAPI REST API
2. **Interoperable Sessions** Session files work across all interfaces
3. **Line-Number Precision** Findings include exact line ranges for editor integration
4. **Learning Over Time** The system adapts to author preferences via LEARNING.md
5. **Scene Change Detection** Authors can edit scenes mid-review without breaking the analysis
6. **Editorial Assistant, Not Ghostwriter** Findings provide conceptual guidance, never prose rewrites. Maximum suggestion: 2-3 example words. Tool validates against author-defined rules, never imposes external standards or generates content
7. **Multilingual Scene Analysis** Modern LLM providers support 100+ languages for scene text. Interface language is English because these models' comprehension of many languages exceeds their production capability. Scene text and index files can be in any language supported by your chosen provider (Greek, Japanese, Spanish, Arabic, Chinese, etc.)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interfaces                          │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │     CLI      │  │   Web UI     │  │  VS Code Extension │   │
│  │              │  │              │  │                    │   │
│  │ interface.py │  │ app.py       │  │  extension.ts      │   │
│  │              │  │ routes.py    │  │  (TypeScript)      │   │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬──────────┘   │
│         │                 │                     │              │
│         │ Direct          │ HTTP                │ HTTP         │
│         │ Import          │ (FastAPI)           │ (REST API)   │
└─────────┼─────────────────┼─────────────────────┼──────────────┘
          │                 │                     │
          │                 │                     │
          │        ┌────────▼─────────────────────▼────────┐
          │        │      FastAPI Backend (web/)           │
          │        │                                        │
          │        │  routes.py - REST endpoints            │
          │        │  session_manager.py - Web state        │
          │        └────────────────┬───────────────────────┘
          │                         │
          │                         │ Imports
          └─────────────────────────┤
                                    │
                          ┌─────────▼──────────┐
                          │   Server Layer     │
                          │   (server/)        │
                          │                    │
                          │  ┌──────────────┐  │
                          │  │   api.py     │  │ ◄─── LLM API calls
                          │  │              │  │      (via llm/ layer)
                          │  │ - run_lens() │  │
                          │  │ - coordinator│  │
                          │  └──────────────┘  │
                          │                    │
                          │  ┌──────────────┐  │
                          │  │ discussion.py│  │ ◄─── Multi-turn
                          │  │              │  │      dialogue
                          │  └──────────────┘  │
                          │                    │
                          │  ┌──────────────┐  │
                          │  │ learning.py  │  │ ◄─── Preference
                          │  │              │  │      tracking
                          │  └──────────────┘  │
                          │                    │
                          │  ┌──────────────┐  │
                          │  │ session.py   │  │ ◄─── Save/resume
                          │  │              │  │      & scene change
                          │  └──────────────┘  │
                          │                    │
                          │  ┌──────────────┐  │
                          │  │ models.py    │  │ ◄─── Data structures
                          │  │              │  │      (Finding, etc.)
                          │  └──────────────┘  │
                          │                    │
                          │  ┌──────────────┐  │
                          │  │ prompts.py   │  │ ◄─── Prompt templates
                          │  └──────────────┘  │
                          │                    │
                          │  ┌──────────────┐  │
                          │  │ utils.py     │  │ ◄─── Line mapping,
                          │  │              │  │      difflib
                          │  └──────────────┘  │
                          └────────────────────┘
                                    │
                                    │ Reads/Writes
                                    │
                          ┌─────────▼──────────┐
                          │   Data Layer       │
                          │   (Filesystem)     │
                          │                    │
                          │  ┌──────────────┐  │
                          │  │ Project Dir  │  │
                          │  │              │  │
                          │  │ - CANON.md   │  │
                          │  │ - CAST.md    │  │
                          │  │ - GLOSSARY   │  │
                          │  │ - STYLE.md   │  │
                          │  │ - THREADS    │  │
                          │  │ - TIMELINE   │  │
                          │  │ - LEARNING   │  │
                          │  │              │  │
                          │  │ - .literary_ │  │
                          │  │   critic_    │  │
                          │  │   session.   │  │
                          │  │   json       │  │
                          │  │              │  │
                          │  │ - text/      │  │
                          │  │   (scenes)   │  │
                          │  └──────────────┘  │
                          └────────────────────┘
```

---

## Component Overview

### User Interfaces (3)

#### 1. CLI (`cli/`)
**Purpose:** Terminal-based interface for keyboard-driven workflow.

**Key File:** `interface.py`

**Features:**
- Direct import of `server/` modules
- Interactive session with command parsing
- Streaming discussion responses to terminal
- Session save/resume

**Entry Point:** `python lit-critic.py`

---

#### 2. Web UI (`web/`)
**Purpose:** Browser-based visual interface.

**Key Files:**
- `app.py` - FastAPI application and static file serving
- `routes.py` - REST API endpoints
- `session_manager.py` - Web-specific session state management
- `templates/index.html` - Single-page application
- `static/js/app.js` - Frontend JavaScript

**Features:**
- Server-Sent Events (SSE) for progress streaming
- Responsive UI with live progress bars
- Session persistence in browser localStorage
- Streaming discussion via SSE

**Entry Point:** `python lit-critic-web.py`

---

#### 3. VS Code Extension (`vscode-extension/`)
**Purpose:** Native editor integration with squiggly underlines and sidebar.

**Key Files:**
- `src/extension.ts` - Entry point, command registration
- `src/serverManager.ts` - Spawns/manages FastAPI backend process
- `src/apiClient.ts` - Typed HTTP wrapper for REST API
- `src/diagnosticsProvider.ts` - Maps findings → VS Code diagnostics
- `src/findingsTreeProvider.ts` - Sidebar tree view
- `src/discussionPanel.ts` - Webview for interactive discussion
- `src/statusBar.ts` - Progress indicator

**Features:**
- Activates on `CANON.md` detection
- Auto-starts backend server as child process
- Real-time diagnostics (squiggly underlines)
- Click findings in sidebar to jump to location
- Interoperable with CLI/Web UI (same session files)

**Entry Point:** VS Code extension system (F5 in development)

---

### Server Layer (`server/`)

The **shared backend** used by all interfaces.

#### `llm/` Multi-Provider LLM Abstraction Layer

**Purpose:** Provider-agnostic async interface for LLM calls. All `api.py` and `discussion.py` functions use this layer instead of calling provider SDKs directly.

**Key Files:**
- `base.py` `LLMClient` abstract base class + `LLMResponse` / `LLMToolResponse` dataclasses
- `anthropic_client.py` `AnthropicClient(LLMClient)` wrapping `AsyncAnthropic`
- `openai_client.py` `OpenAIClient(LLMClient)` wrapping `AsyncOpenAI`
- `factory.py` `create_client(provider, api_key)` with lazy imports

**Three abstract methods:**
1. `create_message()` → `LLMResponse` (plain text)
2. `create_message_with_tool()` → `LLMToolResponse` (structured output via tool/function calling)
3. `stream_message()` → async generator yielding `str` chunks then final `LLMResponse`

**Tool schema translation:** Tool definitions use Anthropic format as the canonical format. Each provider implementation translates to its native format (e.g. OpenAI function-calling).

---

#### `api.py` LLM API Interaction

**Functions:**
- `run_lens()` Single lens analysis
- `run_coordinator_chunked()` Coordinate findings in 3 chunks (prose → structure → coherence)
- `run_coordinator()` Single-call coordinator (fallback)
- `run_analysis()` Orchestrates all lenses + coordinator
- `re_evaluate_finding()` Re-checks stale findings after scene edits

**Flow:**
1. **5 lenses run in parallel** (async)
2. **Coordinator runs** (chunked by default)
   - Each chunk handles one lens group
   - Results merged client-side
   - Cross-group duplicates removed
3. **Structured output** via tool/function calling (`report_findings`)
4. **Validation & defaults** applied to coordinator output

**Retry Logic:**
- Coordinator auto-retries up to 3 times on transient failures
- Exponential backoff: 2^attempt seconds

---

#### `models.py` Data Structures

**Classes:**
- `Finding` Single editorial finding
  - Fields: number, severity, lens, location, line_start/end, evidence, impact, options
  - Discussion state: status, author_response, discussion_turns, revision_history
  - Methods: `to_dict()`, `from_dict()`
- `LensResult` Output from one lens
- `SessionState` Full review session state
  - Properties: model_id, model_max_tokens, model_label
- `LearningData` Preference tracking data
- `CoordinatorError` Exception for coordinator failures

---

#### `discussion.py` Multi-Turn Dialogue

**Functions:**
- `handle_discussion()` Non-streaming discussion
- `handle_discussion_stream()` Streaming discussion (SSE/token-by-token)
- `parse_discussion_response()` Extract actions from Claude's response
- `apply_revision()` Update finding based on discussion
- `build_prior_outcomes_summary()` Cross-finding context for Claude

**Actions the AI Can Take:**
- **Defend** Stand behind the finding
- **Concede** Withdraw the finding
- **Revise** Update severity, evidence, suggestions
- **Escalate** Increase severity
- **Extract preference** Learn author's style

**Revision History:**
- Original finding preserved in `revision_history`
- Timestamp + reason recorded
- Allows undo/review of changes

---

#### `learning.py` Preference Tracking

**Functions:**
- `load_learning()` Read LEARNING.md from project
- `save_learning_to_file()` Write LEARNING.md
- `generate_learning_markdown()` Format as clean markdown
- `update_learning_from_session()` Extract patterns from session

**What Gets Learned:**
- Rejection patterns (findings author consistently rejects)
- Acceptance patterns (author's blind spots)
- Ambiguity preferences (intentional vs. accidental)
- Explicit preferences from discussion

**Confidence Tracking:**
- Tracks how many times a preference is confirmed
- Stronger preferences (6+ instances) have more influence

---

#### `session.py` Session Persistence

**Functions:**
- `save_session()` Serialize state to `.lit-critic-session.json`
- `load_session()` Deserialize from file
- `validate_session()` Check scene hash, file path
- `detect_and_apply_scene_changes()` Scene change detection & re-evaluation
- `compute_scene_hash()` SHA-256 of scene content

**Session File Contents:**
- Scene path, project path, content hash
- All findings with full state
- Current index, skip_minor flag
- Learning data (session-level)
- Model selection

**Scene Change Detection:**
1. Re-hash scene content before each finding
2. If hash differs: compute line mapping via `difflib.SequenceMatcher`
3. Adjust line numbers for findings in unchanged regions
4. Mark findings in edited regions as `stale=True`
5. Re-evaluate stale findings via `api.re_evaluate_finding()`
6. Claude updates or withdraws each stale finding

---

#### `prompts.py` Prompt Engineering

**Functions:**
- `get_lens_prompt()` Prompt for single lens
- `get_coordinator_prompt()` Single-call coordinator
- `get_coordinator_chunk_prompt()` Chunked coordinator
- `get_discussion_system_prompt()` Discussion system prompt
- `build_discussion_messages()` Format conversation history
- `get_re_evaluation_prompt()` Stale finding re-check

**Constants:**
- `COORDINATOR_TOOL` Anthropic tool definition for `report_findings`
- `LENS_GROUPS` Prose/Structure/Coherence groupings

**Line Numbering:**
- Scene text prepended with `L001:`, `L002:`, etc.
- Lenses instructed to emit `line_start` and `line_end`
- Coordinator preserves line numbers through deduplication

---

#### `utils.py` Line Mapping Utilities

**Functions:**
- `number_lines()` Prepend `L001:` prefix to each line
- `compute_line_mapping()` difflib-based old→new line mapping
- `adjust_finding_lines()` Apply mapping to a single finding
- `apply_scene_change()` Bulk adjust all findings

**Line Mapping Algorithm:**
1. `difflib.SequenceMatcher` compares old/new text line-by-line
2. Unchanged lines: map old line → new line
3. Changed/deleted lines: mark as "no mapping" (stale)
4. Findings in unmapped regions → `stale=True`
5. Findings in mapped regions → `line_start`/`line_end` adjusted

---

#### `config.py` Configuration

**Constants:**
- `DEFAULT_MODEL` "sonnet" (balanced, Anthropic)
- `AVAILABLE_MODELS` Dict of model configs with provider info (Anthropic: opus, sonnet, haiku; OpenAI: gpt-4o, gpt-4o-mini, o3)
- `API_KEY_ENV_VARS` Maps provider → env var name (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`)
- `MAX_TOKENS` Default output budget for lenses
- `COORDINATOR_MAX_TOKENS` Output budget for coordinator

**Functions:**
- `resolve_model()` Map short name (e.g., "sonnet") to full config dict (id, provider, max_tokens, label)
- `resolve_api_key()` Get API key for a provider (explicit key → env var → error)

---

## Data Flow

### Analysis Flow

```
1. User starts analysis
   ↓
2. Load index files (CANON, CAST, GLOSSARY, STYLE, THREADS, TIMELINE, LEARNING)
   ↓
3. Load scene text, prepend line numbers
   ↓
4. Run 5 lenses in parallel (async)
   - Each lens receives: scene + indexes + LEARNING
   - Each lens outputs: raw text findings
   ↓
5. Coordinator runs (chunked or single-call)
   - Merges findings from lenses
   - Deduplicates (line overlap detection)
   - Prioritizes (critical > major > minor)
   - Assigns finding numbers
   - Extracts glossary issues, conflicts, ambiguities
   ↓
6. Present findings one at a time
   - Check for scene changes before each finding
   - Re-evaluate stale findings if needed
   ↓
7. Author responds (accept/reject/discuss/skip)
   ↓
8. Loop until all findings reviewed
   ↓
9. Save session (optional) or save learning
```

---

### Discussion Flow

```
1. Author types message
   ↓
2. Build conversation history:
   - System prompt (finding details + scene + prior outcomes)
   - Previous discussion turns
   - New user message
   ↓
3. Call the LLM (streaming or non-streaming)
   ↓
4. Parse response:
   - Look for action directives (REVISE, WITHDRAW, ESCALATE, PREFERENCE)
   - Extract changes (severity, evidence, etc.)
   ↓
5. Apply changes:
   - Update finding (save old version to revision_history)
   - Track preference if PREFERENCE directive
   - Update status (revised, withdrawn, escalated)
   ↓
6. Return response to interface
   - Streaming: SSE token-by-token
   - Non-streaming: Full response
```

---

### Session Resume Flow

```
1. Load .lit-critic-session.json
   ↓
2. Validate:
   - Scene path matches
   - Scene content hash matches
   ↓
3. If valid:
   - Restore findings, current index, learning data
   - Continue from where user left off
   ↓
4. If invalid:
   - Error: scene modified or moved
   - User must start fresh review
```

---

## Key Algorithms

### 1. Coordinator Chunking Strategy

**Problem:** Large scenes generate too many findings for a single coordinator call (token limit).

**Solution:** Split coordinator into 3 chunks by lens group:

1. **Prose chunk** Prose + Clarity lenses
2. **Structure chunk** Structure lens
3. **Coherence chunk** Logic + Continuity lenses

Each chunk runs independently, then results are merged client-side:
- Findings concatenated
- Cross-group duplicates removed (line overlap > 50%)
- Findings renumbered sequentially

**Fallback:** If chunked coordinator fails, fall back to single-call mode.

---

### 2. Finding Deduplication

**Problem:** Multiple lenses may flag the same issue.

**Solution:** Overlap detection + merge:

1. Compare line ranges between findings
2. If overlap > 50% of smaller range: **duplicate**
3. Keep higher severity, merge `flagged_by` lists
4. Union suggestions from both findings

**Example:**
- Prose flags lines 42-45 (Major): "Repetitive phrasing"
- Clarity flags lines 43-46 (Critical): "Unclear pronoun reference"
- **Result:** Merge to lines 42-46 (Critical), `flagged_by: [prose, clarity]`

---

### 3. Line Mapping (Scene Change Detection)

**Problem:** User edits scene mid-review. Line numbers shift.

**Solution:** `difflib.SequenceMatcher` computes old→new mapping:

```python
matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
for tag, i1, i2, j1, j2 in matcher.get_opcodes():
    if tag == 'equal':
        # Lines unchanged: map old→new
        for offset in range(i2 - i1):
            mapping[i1 + offset + 1] = j1 + offset + 1
    elif tag in ('replace', 'delete'):
        # Lines changed/deleted: mark stale
        for old_line in range(i1 + 1, i2 + 2):
            mapping[old_line] = None  # Stale
```

**Result:**
- Findings in unchanged regions: line numbers adjusted
- Findings in changed regions: marked `stale=True`, re-evaluated

---

### 4. Re-Evaluation of Stale Findings

**Problem:** Finding references lines that were edited.

**Solution:** Send finding + new scene text to the LLM:

```
"This finding was flagged before the author edited the scene.
Re-evaluate it against the updated text.

If the issue still applies: return {"status": "updated", ...}
If the edit resolved it: return {"status": "withdrawn", ...}
```

The LLM responds with structured JSON. Finding updated or withdrawn accordingly.

---

## Design Patterns

### 1. Shared Backend Pattern

All three interfaces (CLI, Web UI, VS Code) use the same `server/` modules:
- **CLI:** Direct Python import
- **Web UI:** FastAPI HTTP endpoints
- **VS Code:** HTTP client calling same FastAPI endpoints

**Benefit:** Single source of truth, consistent behavior across interfaces.

---

### 2. Session State Pattern

`SessionState` dataclass holds all review state:
- Scene content, path, project path
- LLM client (provider-agnostic `LLMClient` instance)
- Index files (CANON, CAST, etc.)
- Findings list
- Learning data
- Model selection (includes provider info)

Passed between functions, serialized for save/resume.

**Benefit:** Clear state boundaries, easy serialization.

---

### 3. Streaming Pattern

Discussion responses stream token-by-token via:
- **CLI:** Print tokens as they arrive
- **Web UI:** Server-Sent Events (SSE)
- **VS Code:** SSE in webview

**Implementation:** `LLMClient.stream_message()` async generator yields tokens, forwarded to client. Each provider implementation (Anthropic, OpenAI) handles the native streaming API internally.

**Benefit:** Faster perceived response time, live feedback.

---

### 4. Tool Use Pattern

Coordinator uses forced tool/function calling for structured JSON output:

```python
# Via LLMClient abstraction — provider handles native format
response = await client.create_message_with_tool(
    model=model_id,
    max_tokens=max_tokens,
    messages=messages,
    tool_schema=COORDINATOR_TOOL,   # Anthropic format (canonical)
    tool_name="report_findings",
    system=system_prompt,
)
# response.tool_input is a parsed dict
```

Tool schemas are defined in Anthropic format. Each provider implementation translates:
- **Anthropic:** Native `tool_use` with `tool_choice`
- **OpenAI:** Translated to `functions` / `function_call` format

The model **must** respond with `report_findings` tool call containing JSON.

**Benefit:** Guaranteed structure, no manual JSON parsing failures.

---

## Extension Points

### Adding a New Lens

1. Add lens prompt template in `prompts.py`
2. Add lens to `run_analysis()` in `api.py`
3. Assign lens to a group in `LENS_GROUPS` (prompts.py)
4. Update coordinator prompt to expect new lens

---

### Adding a New Interface

1. Create new directory (e.g., `desktop-app/`)
2. Import `server/` modules or call FastAPI REST API
3. Implement finding presentation logic
4. Use `SessionState` for save/resume compatibility

---

### Adding a New Model

1. Add entry to `AVAILABLE_MODELS` in `config.py` (include `id`, `provider`, `max_tokens`, `label`)
2. If new provider: add env var to `API_KEY_ENV_VARS`
3. Test token limits, adjust `MAX_TOKENS` if needed
4. Update UI dropdowns (Web, VS Code)

### Adding a New LLM Provider

1. Create `server/llm/<provider>_client.py` implementing `LLMClient` ABC
2. Register in `server/llm/factory.py` (lazy import)
3. Add provider entry to `API_KEY_ENV_VARS` in `config.py`
4. Add at least one model entry to `AVAILABLE_MODELS`
5. Handle tool schema translation from Anthropic format → provider format

---

## Performance Considerations

### Async I/O
- All LLM API calls use async clients (`AsyncAnthropic`, `AsyncOpenAI`)
- Lenses run in parallel via `asyncio.gather()`
- Typical 3-4 page scene: 30-90 seconds total

### Token Budget
- Lens output: 8192 tokens each
- Coordinator output: 16384 tokens (chunked mode helps)
- Discussion: 4096 tokens per turn

### Caching
- Index files cached in `SessionState` (not re-read per finding)
- Scene content cached (only re-read when hash check fails)

---

## Security Considerations

### API Key
- Never committed to git
- Stored in environment variable or passed via CLI flag
- Web UI receives API key from frontend (user's responsibility to secure)

### Session Files
- Contain full scene text + findings
- Recommend `.gitignore` for `.lit-critic-session.json`
- No encryption (filesystem security)

### Input Validation
- Scene path validated (must exist, must be readable)
- Project path validated (must be directory)
- API key validated (non-empty)
- Model name validated (must be in `AVAILABLE_MODELS`)

---

## Future Architecture Improvements

### Planned
- **Configurable lenses** Enable/disable per session
- **Custom lenses** User-defined prompts
- **Batch mode** Review multiple scenes sequentially
- **Cross-scene analysis** Compare against previous scenes
- **MCP server** Expose as tool for Claude Code

### Under Consideration
- **Database backend** Replace JSON session files with SQLite
- **Distributed coordinator** Split work across multiple Claude calls
- **Lens caching** Cache lens results for unchanged scenes
- **Real-time collaboration** Multiple users reviewing same scene

---

## See Also

- **[API Reference](api-reference.md)** REST endpoint documentation
- **[Testing Guide](testing.md)** Running and writing tests
- **[Installation Guide](installation.md)** Developer setup
- **[Installation Guide](installation.md)** Developer setup
