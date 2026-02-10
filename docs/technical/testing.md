# Testing Guide

Comprehensive guide to running and writing tests for lit-critic.

---

## Overview

lit-critic has test suites for all components:
- **Python tests** (pytest) — Server, CLI, Web
- **TypeScript tests** (mocha) — VS Code Extension

---

## Quick Start

### Run All Tests

```bash
npm test
```

This runs both Python and TypeScript tests in sequence.

---

### Python Tests Only

```bash
pytest
# OR
npm run test:python
```

---

### TypeScript Tests Only

```bash
npm run test:ts
# OR
cd vscode-extension && npm test
```

---

## Python Testing

### Framework

- **pytest** Test runner
- **pytest-asyncio** Async test support
- **pytest-cov** Coverage reporting

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── server/
│   ├── test_api.py
│   ├── test_config.py
│   ├── test_discussion.py
│   ├── test_learning.py
│   ├── test_models.py
│   ├── test_prompts.py
│   ├── test_session.py
│   └── test_utils.py
├── cli/
│   └── test_interface.py
└── web/
    └── test_routes.py
```

---

### Running Python Tests

#### All Python Tests

```bash
pytest
```

#### Specific Module

```bash
pytest tests/server/
pytest tests/cli/
pytest tests/web/
```

#### Specific File

```bash
pytest tests/server/test_api.py
```

#### Specific Test

```bash
pytest tests/server/test_api.py::test_run_lens
```

#### With Verbose Output

```bash
pytest -v
```

#### With Coverage

```bash
pytest --cov=server --cov=cli --cov=web
```

#### Coverage HTML Report

```bash
pytest --cov=server --cov=cli --cov=web --cov-report=html
# Open htmlcov/index.html in browser
```

---

### Python Test Examples

#### Test with Mock

```python
import pytest
from unittest.mock import Mock, AsyncMock, patch
from server.api import run_lens

@pytest.mark.asyncio
async def test_run_lens_success():
    """Test successful lens execution."""
    # Mock Anthropic client
    mock_client = Mock()
    mock_response = Mock()
    mock_response.content = [Mock(text="Finding 1: ...")]
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    
    # Run lens
    result = await run_lens(
        mock_client,
        "prose",
        "Scene text here",
        {"CANON": "Canon content"},
        model="sonnet"
    )
    
    # Assertions
    assert result.lens_name == "prose"
    assert result.error is None
    assert result.raw_output == "Finding 1: ..."
    mock_client.messages.create.assert_called_once()
```

#### Test with Fixture

```python
@pytest.fixture
def sample_finding():
    """Create a sample Finding for testing."""
    from server.models import Finding
    return Finding(
        number=1,
        severity="major",
        lens="prose",
        location="L042-L045",
        line_start=42,
        line_end=45,
        evidence="Test evidence",
        impact="Test impact",
        options=["Option 1", "Option 2"]
    )

def test_finding_to_dict(sample_finding):
    """Test Finding.to_dict()."""
    data = sample_finding.to_dict()
    assert data["number"] == 1
    assert data["severity"] == "major"
    assert data["lens"] == "prose"
```

#### Test Exception Handling

```python
@pytest.mark.asyncio
async def test_coordinator_retry_on_failure():
    """Test coordinator retries on transient failure."""
    mock_client = Mock()
    mock_client.messages.create = AsyncMock(
        side_effect=[
            Exception("Temporary failure"),
            Exception("Temporary failure"),
            Mock(content=[Mock(type="tool_use", name="report_findings",
                              input={"findings": [], "glossary_issues": [],
                                     "summary": {}})])
        ]
    )
    
    # Should succeed after 2 retries
    result = await run_coordinator(mock_client, [], "scene", max_retries=3)
    
    assert result is not None
    assert mock_client.messages.create.call_count == 3
```

---

### Python Test Fixtures (conftest.py)

```python
import pytest
from pathlib import Path
from server.models import Finding, SessionState
from anthropic import AsyncAnthropic

@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory with index files."""
    (tmp_path / "CANON.md").write_text("# Canon\n")
    (tmp_path / "CAST.md").write_text("# Cast\n")
    (tmp_path / "GLOSSARY.md").write_text("# Glossary\n")
    (tmp_path / "STYLE.md").write_text("# Style\n")
    (tmp_path / "THREADS.md").write_text("# Threads\n")
    (tmp_path / "TIMELINE.md").write_text("# Timeline\n")
    
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    
    return tmp_path

@pytest.fixture
def sample_scene():
    """Sample scene text with @@META header."""
    return """@@META
ID: 01.01.01
Part: 01
Chapter: 01
Scene: 01
Chrono: D0-Morning
POV: Amelia
Tense: Past
Location: Sanctuary
Cast: Amelia
Objective: Opening scene
Threats: None
Secrets: None
ContAnchors: None
Terms: None
Threads: None
Prev: None
Next: 01.01.02
@@END

Scene text here.
"""

@pytest.fixture
def mock_anthropic_client():
    """Mock AsyncAnthropic client."""
    from unittest.mock import Mock, AsyncMock
    client = Mock(spec=AsyncAnthropic)
    client.messages.create = AsyncMock()
    return client
```

---

## TypeScript Testing

### Framework

- **mocha** Test runner
- **@types/mocha** TypeScript types
- **sinon** Mocking/stubbing (optional)

### Test Structure

```
tests/vscode-extension/
├── fixtures.ts           # Shared mocks and test data
├── test_apiClient.ts
├── test_diagnosticsProvider.ts
├── test_discussionPanel.ts
├── test_extension.ts
├── test_findingsTreeProvider.ts
├── test_serverManager.ts
└── test_statusBar.ts
```

---

### Running TypeScript Tests

#### All TypeScript Tests

```bash
cd vscode-extension
npm test
```

#### Watch Mode (Development)

```bash
cd vscode-extension
npm test -- --watch
```

#### Specific Test File

```bash
cd vscode-extension
npm test -- --grep "ApiClient"
```

---

### TypeScript Test Examples

#### Test with Mock

```typescript
import * as assert from 'assert';
import { ApiClient } from '../src/apiClient';
import { mockFetch, mockVscode } from './fixtures';

describe('ApiClient', () => {
    it('should start analysis successfully', async () => {
        const client = new ApiClient('http://localhost:8000');
        
        // Mock fetch
        global.fetch = mockFetch({
            '/api/analyze': {
                status: 'success',
                total_findings: 5
            }
        });
        
        const result = await client.startAnalysis(
            '/path/to/scene.txt',
            '/path/to/project/',
            'sk-ant-key',
            'sonnet'
        );
        
        assert.strictEqual(result.status, 'success');
        assert.strictEqual(result.total_findings, 5);
    });
    
    it('should handle API errors', async () => {
        const client = new ApiClient('http://localhost:8000');
        
        global.fetch = mockFetch({
            '/api/analyze': { error: 'API error' }
        }, 500);
        
        await assert.rejects(
            client.startAnalysis('/scene.txt', '/project/', 'key', 'sonnet'),
            /API error/
        );
    });
});
```

#### Test VS Code Integration

```typescript
import * as vscode from 'vscode';
import { DiagnosticsProvider } from '../src/diagnosticsProvider';
import { mockFinding } from './fixtures';

describe('DiagnosticsProvider', () => {
    let diagnosticCollection: vscode.DiagnosticCollection;
    let provider: DiagnosticsProvider;
    
    beforeEach(() => {
        diagnosticCollection = {
            set: (uri, diagnostics) => { /* mock */ },
            clear: () => { /* mock */ }
        } as any;
        provider = new DiagnosticsProvider(diagnosticCollection);
    });
    
    it('should convert finding to diagnostic', () => {
        const finding = mockFinding({
            severity: 'critical',
            line_start: 42,
            line_end: 45,
            evidence: 'Test evidence'
        });
        
        const diagnostic = provider.createDiagnostic(finding);
        
        assert.strictEqual(diagnostic.severity, vscode.DiagnosticSeverity.Error);
        assert.strictEqual(diagnostic.range.start.line, 41); // 0-based
        assert.strictEqual(diagnostic.range.end.line, 44);
    });
});
```

---

### TypeScript Test Fixtures (fixtures.ts)

```typescript
import { Finding } from '../src/types';

export function mockFinding(overrides?: Partial<Finding>): Finding {
    return {
        number: 1,
        severity: 'major',
        lens: 'prose',
        location: 'L042-L045',
        line_start: 42,
        line_end: 45,
        evidence: 'Test evidence',
        impact: 'Test impact',
        options: ['Option 1'],
        flagged_by: ['prose'],
        ambiguity_type: null,
        stale: false,
        status: 'pending',
        author_response: '',
        discussion_turns: [],
        revision_history: [],
        outcome_reason: '',
        ...overrides
    };
}

export function mockFetch(responses: Record<string, any>, status = 200) {
    return async (url: string, options: any) => {
        const path = new URL(url).pathname;
        const response = responses[path];
        
        return {
            ok: status >= 200 && status < 300,
            status,
            json: async () => response,
            text: async () => JSON.stringify(response)
        };
    };
}

export const mockVscode = {
    window: {
        showInformationMessage: () => Promise.resolve(),
        showErrorMessage: () => Promise.resolve(),
        createOutputChannel: () => ({
            appendLine: () => {},
            show: () => {}
        })
    },
    DiagnosticSeverity: {
        Error: 0,
        Warning: 1,
        Information: 2,
        Hint: 3
    }
};
```

---

## Test Coverage

### Current Coverage

Run with coverage reporting:

```bash
pytest --cov=server --cov=cli --cov=web --cov-report=term-missing
```

### Coverage Goals

- **Server:** >80%
- **CLI:** >70%
- **Web:** >70%
- **VS Code Extension:** >60%

### Viewing Coverage Reports

**Terminal:**
```bash
pytest --cov=server --cov-report=term-missing
```

**HTML:**
```bash
pytest --cov=server --cov-report=html
open htmlcov/index.html  # macOS
start htmlcov/index.html  # Windows
```

---

## Mocking Strategies

### Mock Anthropic API

```python
from unittest.mock import AsyncMock, Mock

mock_client = Mock()
mock_client.messages.create = AsyncMock(
    return_value=Mock(content=[Mock(text="Response")])
)
```

### Mock File I/O

```python
from unittest.mock import patch, mock_open

with patch('builtins.open', mock_open(read_data="file content")):
    # Test code that reads files
    pass
```

### Mock HTTP Requests (TypeScript)

```typescript
global.fetch = async (url, options) => ({
    ok: true,
    status: 200,
    json: async () => ({status: 'success'})
});
```

---

## Writing New Tests

### Python Test Template

```python
import pytest
from unittest.mock import Mock, AsyncMock
from server.module import function_to_test

def test_function_basic_case():
    """Test basic functionality."""
    result = function_to_test(input_data)
    assert result == expected_output

@pytest.mark.asyncio
async def test_async_function():
    """Test async function."""
    result = await async_function()
    assert result is not None

def test_function_error_handling():
    """Test error cases."""
    with pytest.raises(ValueError):
        function_to_test(invalid_input)
```

### TypeScript Test Template

```typescript
import * as assert from 'assert';
import { functionToTest } from '../src/module';

describe('Module', () => {
    describe('functionToTest', () => {
        it('should handle basic case', () => {
            const result = functionToTest(inputData);
            assert.strictEqual(result, expectedOutput);
        });
        
        it('should handle error case', () => {
            assert.throws(
                () => functionToTest(invalidInput),
                /Error message/
            );
        });
    });
});
```

---

## Continuous Integration

### GitHub Actions (Example)

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install Python dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio
      
      - name: Run Python tests
        run: pytest --cov=server --cov=cli --cov=web
      
      - name: Set up Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '16'
      
      - name: Install TypeScript dependencies
        run: |
          cd vscode-extension
          npm install
      
      - name: Run TypeScript tests
        run: |
          cd vscode-extension
          npm test
```

---

## Best Practices

### 1. Test Naming

- **Python:** `test_<function_name>_<scenario>`
- **TypeScript:** `should <expected behavior>`

### 2. Arrange-Act-Assert Pattern

```python
def test_example():
    # Arrange
    input_data = create_test_data()
    
    # Act
    result = function(input_data)
    
    # Assert
    assert result == expected_value
```

### 3. One Assertion Per Test (Generally)

```python
# Good
def test_finding_number():
    finding = create_finding()
    assert finding.number == 1

def test_finding_severity():
    finding = create_finding()
    assert finding.severity == "major"

# Avoid (unless assertions are closely related)
def test_finding():
    finding = create_finding()
    assert finding.number == 1
    assert finding.severity == "major"
    assert finding.lens == "prose"
```

### 4. Use Fixtures for Reusable Setup

```python
@pytest.fixture
def session_state(temp_project_dir):
    """Create SessionState for testing."""
    # Setup
    state = create_state(temp_project_dir)
    yield state
    # Teardown (if needed)
    cleanup(state)
```

### 5. Test Edge Cases

- Empty inputs
- None values
- Very large inputs
- Invalid types
- Concurrent operations

---

## Debugging Tests

### Python

```bash
# Run with debugger on failure
pytest --pdb

# Run specific test with verbose output
pytest -v -s tests/server/test_api.py::test_run_lens
```

### TypeScript

Add `debugger;` statement in test, then:

```bash
cd vscode-extension
npm test -- --inspect-brk
```

Open `chrome://inspect` in Chrome.

---

## See Also

- **[Architecture Guide](architecture.md)** Understanding the system for effective testing
- **[API Reference](api-reference.md)** Endpoint behavior to test
- **[Installation Guide](installation.md)** Setup test environment
