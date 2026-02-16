# Installation Guide (Developers)

This guide covers developer setup for lit-critic under the current architecture:

- **Core (`core/`)** stateless reasoning endpoints
- **Platform (`lit_platform/`)** workflow and persistence ownership
- **Clients (`cli/`, `web/`, `vscode-extension/`)** thin interaction layers

---

## Prerequisites

### Required

- Python 3.10+
- Node.js 16+ (VS Code extension)
- Git
- At least one provider API key:
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`

### Optional

- VS Code (extension development)
- virtualenv/conda/pyenv

---

## Quick Start

```bash
# 1) Clone
git clone https://github.com/alexisargyris/lit-critic.git
cd lit-critic

# 2) Virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3) Install dependencies
pip install -r requirements.txt

# 4) Configure provider key(s)
export ANTHROPIC_API_KEY="sk-ant-..."  # macOS/Linux
# or on Windows Command Prompt:
setx ANTHROPIC_API_KEY "sk-ant-..."

# 5) Run CLI help
python lit-critic.py --help

# 6) Run Web/API surface
python lit-critic-web.py

# 7) Install extension dependencies
cd vscode-extension && npm install
```

---

## Python Environment Options

### venv (recommended)

```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows
```

### conda

```bash
conda create -n lit-critic python=3.10
conda activate lit-critic
```

### pyenv

```bash
pyenv install 3.10.0
pyenv virtualenv 3.10.0 lit-critic
pyenv activate lit-critic
```

---

## Dependency Installation

```bash
pip install -r requirements.txt
```

Common dependencies include:

```text
anthropic>=0.34.0
openai>=1.0.0
fastapi>=0.115.0
uvicorn>=0.32.0
pydantic>=2.0.0
python-multipart
```

Dev/test extras:

```bash
pip install pytest pytest-cov pytest-asyncio
```

---

## API Key Configuration

Set key(s) for providers you use.

### Anthropic

```bash
# macOS/Linux
export ANTHROPIC_API_KEY="sk-ant-your-key"

# Windows Command Prompt
setx ANTHROPIC_API_KEY "sk-ant-your-key"

# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-your-key"
```

### OpenAI

```bash
# macOS/Linux
export OPENAI_API_KEY="sk-your-key"

# Windows Command Prompt
setx OPENAI_API_KEY "sk-your-key"

# Windows PowerShell
$env:OPENAI_API_KEY = "sk-your-key"
```

---

## Running Components

### CLI

```bash
python lit-critic.py --scene path/to/scene.txt --project path/to/project/
python lit-critic.py --scene scene.txt --project ~/novel/ --model sonnet
python lit-critic.py --resume --project ~/novel/
```

### Web/API surface

```bash
python lit-critic-web.py --reload
python lit-critic-web.py --port 3000
```

Open `http://localhost:8000`.

### VS Code extension

```bash
cd vscode-extension
npm install
npm run compile
```

Press **F5** in VS Code for extension development host.

---

## Project Structure (Current)

```text
lit-critic/
├── core/                   # Stateless reasoning service
├── lit_platform/           # Workflow + persistence owner
├── contracts/              # Versioned contracts
├── cli/                    # CLI UX layer
├── web/                    # HTTP API + web UI layer
├── vscode-extension/       # VS Code UX layer
├── tests/                  # Python + TypeScript tests
└── docs/                   # User and technical docs
```

---

## Development Workflow

```bash
# create branch
git checkout -b feature/my-change

# run python tests
pytest

# run extension tests
cd vscode-extension && npm test

# run coverage
pytest --cov=core --cov=lit_platform --cov=cli --cov=web --cov=contracts
```

---

## Common Tasks

### Lint/type-check/format

```bash
pip install flake8 mypy black

flake8 core/ lit_platform/ cli/ web/ contracts/
mypy core/ lit_platform/ cli/ web/ contracts/
black core/ lit_platform/ cli/ web/ contracts/
```

### Build extension

```bash
cd vscode-extension
npm run compile
npm run package
```

---

## Troubleshooting

### Module import errors

```bash
pip install -e .
```

### API key not found

Check environment variables and restart terminal session.

### Port already in use

Run on another port:

```bash
python lit-critic-web.py --port 3000
```

### VS Code extension not activating

- Ensure workspace contains `CANON.md`
- Check output channel (`lit-critic`)
- Confirm `literaryCritic.repoPath` when workspace is outside repo

---

## Database / Storage

Platform persists state in `.lit-critic.db`:

- sessions
- findings
- learning

`LEARNING.md` is export output, not canonical source of truth.

Recommended `.gitignore` entries:

```text
.lit-critic.db
__pycache__/
*.pyc
.pytest_cache/
venv/
node_modules/
```

---

## Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic model access | At least one provider key |
| `OPENAI_API_KEY` | OpenAI model access | At least one provider key |

---

## Next Steps

- [Architecture Guide](architecture.md)
- [API Reference](api-reference.md)
- [Testing Guide](testing.md)
- [Reliability Policy](reliability-policy.md)
- [Remote Core Security](security-remote-core.md)
