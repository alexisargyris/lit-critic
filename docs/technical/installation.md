# Installation Guide (Developers)

This guide covers developer setup for contributing to lit-critic (short for Literary Critic).

---

## Prerequisites

### Required

- **Python 3.10+**
- **Node.js 16+** (for VS Code extension)
- **Git**
- **At least one LLM API key:** Anthropic (`ANTHROPIC_API_KEY`) or OpenAI (`OPENAI_API_KEY`)

### Optional

- **VS Code** (for extension development)
- **virtual environment tool** (venv, conda, pyenv)

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/alexisargyris/lit-critic.git
cd lit-critic

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Set API key
export ANTHROPIC_API_KEY="sk-ant-..."  # macOS/Linux
# OR
setx ANTHROPIC_API_KEY "sk-ant-..."    # Windows

# 5. Run CLI
python lit-critic.py --help

# 6. Run Web UI
python lit-critic-web.py

# 7. Install TypeScript dependencies (for VS Code extension)
cd vscode-extension
npm install
```

---

## Detailed Setup

### 1. Python Environment

#### Option A: venv (Recommended)

```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows
```

#### Option B: conda

```bash
conda create -n lit-critic python=3.10
conda activate lit-critic
```

#### Option C: pyenv

```bash
pyenv install 3.10.0
pyenv virtualenv 3.10.0 lit-critic
pyenv activate lit-critic
```

---

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

**Contents of requirements.txt:**
```
anthropic>=0.34.0
openai>=1.0.0
fastapi>=0.115.0
uvicorn>=0.32.0
pydantic>=2.0.0
python-multipart
```

**Development dependencies** (optional):
```bash
pip install pytest pytest-cov pytest-asyncio
```

---

### 3. API Key Configuration

You need at least one API key. Set the environment variable for whichever provider you want to use:

#### Option A: Environment Variable (Recommended)

**Anthropic (Claude models):**

```bash
# macOS/Linux
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
# Windows (Command Prompt)
setx ANTHROPIC_API_KEY "sk-ant-your-key-here"
# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-your-key-here"
```

**OpenAI (GPT/o-series models):**

```bash
# macOS/Linux
export OPENAI_API_KEY="sk-your-key-here"
# Windows (Command Prompt)
setx OPENAI_API_KEY "sk-your-key-here"
# Windows (PowerShell)
$env:OPENAI_API_KEY = "sk-your-key-here"
```

Add to your shell profile (`~/.bashrc`, `~/.zshrc`, PowerShell profile) to make it permanent.

#### Option B: CLI Flag

```bash
python lit-critic.py --api-key sk-ant-your-key-here ...
```

#### Option C: .env File (Not Implemented)

Currently not supported, but you could add python-dotenv if needed.

---

### 4. VS Code Extension Setup

The VS Code extension requires Node.js and TypeScript:

```bash
cd vscode-extension
npm install
```

**Development dependencies installed:**
- TypeScript
- @types/vscode
- @types/node
- esbuild
- mocha (for tests)

---

## Running the Components

### CLI

```bash
python lit-critic.py --scene path/to/scene.txt --project path/to/project/
```

**With specific model:**
```bash
python lit-critic.py --scene scene.txt --project ~/novel/ --model opus
```

**Resume session:**
```bash
python lit-critic.py --resume --project ~/novel/
```

---

### Web UI

**Development mode (with auto-reload):**
```bash
python lit-critic-web.py --reload
```

**Custom port:**
```bash
python lit-critic-web.py --port 3000
```

**Production mode:**
```bash
python lit-critic-web.py
```

Then open http://localhost:8000 in your browser.

---

### VS Code Extension

#### Development Mode (F5 Launch)

1. Open `vscode-extension/` folder in VS Code
2. Press **F5** to launch Extension Development Host
3. In the new window, open a novel project (with CANON.md)
4. Extension activates automatically
5. Press `Ctrl+Shift+L` to analyze a scene

#### Install as VSIX (For Testing)

```bash
cd vscode-extension
npm run package
code --install-extension lit-critic-0.2.0.vsix --force
```

---

## Project Structure

```
lit-critic/
├── cli/                    # CLI interface
│   ├── __init__.py
│   ├── __main__.py
│   └── interface.py
│
├── server/                 # Shared backend
│   ├── __init__.py
│   ├── api.py             # LLM API calls
│   ├── config.py          # Configuration
│   ├── discussion.py      # Multi-turn dialogue
│   ├── learning.py        # Preference tracking
│   ├── models.py          # Data structures
│   ├── prompts.py         # Prompt templates
│   ├── session.py         # Save/resume
│   ├── utils.py           # Line mapping
│   └── llm/               # Multi-provider LLM abstraction
│       ├── __init__.py
│       ├── base.py        # LLMClient ABC + response types
│       ├── anthropic_client.py  # Anthropic/Claude
│       ├── openai_client.py     # OpenAI/GPT
│       └── factory.py    # create_client()
│
├── web/                    # Web UI
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py             # FastAPI app
│   ├── routes.py          # REST endpoints
│   ├── session_manager.py
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── css/
│       └── js/
│
├── vscode-extension/       # VS Code extension
│   ├── src/
│   │   ├── extension.ts
│   │   ├── serverManager.ts
│   │   ├── apiClient.ts
│   │   ├── diagnosticsProvider.ts
│   │   ├── findingsTreeProvider.ts
│   │   ├── discussionPanel.ts
│   │   ├── statusBar.ts
│   │   └── types.ts
│   ├── package.json
│   └── tsconfig.json
│
├── tests/                  # Test suites
│   ├── server/
│   ├── cli/
│   ├── web/
│   └── vscode-extension/
│
├── docs/                   # Documentation
│   ├── user-guide/
│   └── technical/
│
├── lit-critic.py      # CLI entry point
├── lit-critic-web.py  # Web UI entry point
├── requirements.txt
├── package.json
└── README.md
```

---

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/my-new-feature
```

### 2. Make Changes

Edit files in your preferred editor. VS Code recommended for TypeScript work.

### 3. Run Tests

```bash
# Python tests
pytest

# TypeScript tests
cd vscode-extension && npm test
```

### 4. Test Manually

```bash
# CLI
python lit-critic.py --scene test-scene.txt --project test-project/

# Web UI
python lit-critic-web.py --reload

# VS Code
# Press F5 in vscode-extension/ folder
```

### 5. Commit

```bash
git add .
git commit -m "feat: add new feature"
```

### 6. Push and Create PR

```bash
git push origin feature/my-new-feature
```

Then create a pull request on GitHub.

---

## Common Development Tasks

### Running Tests

See **[Testing Guide](testing.md)** for comprehensive coverage.

**Quick test run:**
```bash
pytest
```

**With coverage:**
```bash
pytest --cov=server --cov=cli --cov=web
```

### Linting Python Code

```bash
# Install linters
pip install flake8 mypy

# Run flake8
flake8 server/ cli/ web/

# Run mypy (type checking)
mypy server/ cli/ web/
```

### Formatting Python Code

```bash
# Install formatter
pip install black

# Format code
black server/ cli/ web/
```

### Building VS Code Extension

```bash
cd vscode-extension
npm run compile    # TypeScript → JavaScript
npm run package    # Create .vsix file
```

### Watching for Changes

**Python (Web UI):**
```bash
python lit-critic-web.py --reload
```

**TypeScript:**
```bash
cd vscode-extension
npm run watch
```

---

## Troubleshooting

### "Module not found" errors

**Problem:** Python can't find `server`, `cli`, or `web` modules.

**Solution:** Install in development mode:
```bash
pip install -e .
```

Or ensure you're running from the project root.

---

### API key not found

**Problem:** `No API key provided` error.

**Solution:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# Verify:
echo $ANTHROPIC_API_KEY
```

On Windows, use `setx` and restart your terminal.

---

### Port already in use

**Problem:** `Address already in use` when starting Web UI.

**Solution:** Use a different port:
```bash
python lit-critic-web.py --port 3000
```

Or kill the process using port 8000:
```bash
# Find process
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill it
kill <PID>     # macOS/Linux
taskkill /PID <PID> /F  # Windows
```

---

### VS Code extension won't activate

**Problem:** Extension doesn't activate when opening a project.

**Solution:**
1. Ensure project has a `CANON.md` file (activation trigger)
2. Check Output panel (View → Output → "lit-critic")
3. Verify `literaryCritic.repoPath` setting if project is outside repo

---

### TypeScript compilation errors

**Problem:** `npm run compile` fails.

**Solution:**
```bash
cd vscode-extension
rm -rf node_modules package-lock.json
npm install
npm run compile
```

---

### Test failures

**Problem:** Tests fail with `ModuleNotFoundError`.

**Solution:** Install dev dependencies:
```bash
pip install pytest pytest-asyncio pytest-cov
```

---

## IDE Configuration

### VS Code

Recommended extensions:
- Python
- Pylance
- ESLint
- Prettier
- TypeScript and JavaScript Language Features

**Settings (.vscode/settings.json):**
```json
{
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "typescript.tsdk": "vscode-extension/node_modules/typescript/lib"
}
```

---

### PyCharm / IntelliJ

1. Mark `server/`, `cli/`, `web/` as source roots
2. Configure Python interpreter to use your virtual environment
3. Enable type checking (Preferences → Editor → Inspections → Python)

---

## Database / Storage

lit-critic uses **filesystem storage** (no database):

- **Session files:** `.lit-critic-session.json` in project directory
- **Learning files:** `LEARNING.md` in project directory
- **Index files:** CANON.md, CAST.md, etc. in project directory

**Add to .gitignore:**
```
.lit-critic-session.json
__pycache__/
*.pyc
.pytest_cache/
venv/
node_modules/
```

---

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `ANTHROPIC_API_KEY` | API key for Anthropic Claude models | At least one provider key required |
| `OPENAI_API_KEY` | API key for OpenAI GPT/o-series models | At least one provider key required |

The system automatically resolves which key to use based on the selected model's provider. You only need to set the key(s) for the provider(s) you plan to use.

---

## Next Steps

- **[Architecture Guide](architecture.md)** Understand the system design
- **[API Reference](api-reference.md)** REST endpoint documentation
- **[Testing Guide](testing.md)** Run and write tests
- **[Contributing Guide](contributing.md)** Contribution workflow
