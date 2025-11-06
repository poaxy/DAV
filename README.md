# Dav

An intelligent, context-aware AI assistant built directly into the Linux terminal. Designed for developers, system administrators, cybersecurity engineers, and networking professionals, Dav enables instant access to AI-powered guidance without ever leaving the command line.

**GitHub**: [https://github.com/poaxy/DAV](https://github.com/poaxy/DAV)

## Features

- **Context-Aware**: Automatically detects OS version, current directory, directory contents, and piped input
- **Multiple AI Backends**: Supports OpenAI and Anthropic with real-time streaming responses
- **Rich Terminal Output**: Beautiful markdown formatting, code blocks, and syntax highlighting
- **Interactive Mode**: Multi-turn conversations with `dav -i`
- **Session Persistence**: Maintain context across queries with `--session`
- **Secure Command Execution**: Execute commands with `--execute` (with confirmation and shell injection protection)
- **Query History**: View history with `--history`, stored locally in SQLite
- **Flexible Configuration**: Configure via `.env` file (API keys, permissions, default model)

## Installation

### Install from GitHub (Recommended)

Install directly from the GitHub repository with a single command:

```bash
pip install git+https://github.com/poaxy/DAV.git
```

**Note**: This requires `git` to be installed on your system. If you don't have git installed, you can install it with:
- **Ubuntu/Debian**: `sudo apt-get install git`
- **macOS**: `xcode-select --install` or install via [Homebrew](https://brew.sh)
- **Fedora/RHEL**: `sudo dnf install git`

### Install from PyPI (Coming Soon)

Once published to PyPI, you can install with:

```bash
pip install dav-ai
```

### Development Installation

For development, clone the repository and install in editable mode:

```bash
git clone https://github.com/poaxy/DAV.git
cd DAV
pip install -e .
```

## Quick Start

1. **Set up your API key** (create `~/.dav/.env` or `.env` in your project):

```bash
# For OpenAI
OPENAI_API_KEY=your_openai_api_key_here
DAV_BACKEND=openai
DAV_DEFAULT_MODEL=gpt-4-turbo-preview

# Or for Anthropic
ANTHROPIC_API_KEY=your_anthropic_api_key_here
DAV_BACKEND=anthropic
DAV_DEFAULT_MODEL=claude-3-5-sonnet-20241022
```

2. **Ask a question**:

```bash
dav "how do I find large files in /var/log?"
```

3. **Use with piped input**:

```bash
tail -n 50 error.log | dav "analyze this"
```

4. **Interactive mode**:

```bash
dav -i
```

5. **Execute commands** (with confirmation):

```bash
dav "list all processes using port 80" --execute
```

## Usage Examples

### Basic Query
```bash
dav "how do I check disk usage?"
```

### Interactive Mode
```bash
dav -i
dav> how do I find files modified in the last 24 hours?
dav> can you show me the disk usage for /var?
dav> exit
```

### Session Persistence
```bash
dav --session debug "what's in the current directory?"
dav --session debug "can you explain what that file does?"
```

### Command Execution
```bash
dav "show me running processes" --execute
```

### View History
```bash
dav --history
```

### Analyze Logs
```bash
cat /var/log/syslog | dav "what errors do you see?"
```

## Configuration

Create a `.env` file in `~/.dav/` or your current directory:

```bash
# API Keys (required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Backend Selection
DAV_BACKEND=openai  # or "anthropic"

# Model Selection
DAV_DEFAULT_MODEL=gpt-4-turbo-preview
DAV_OPENAI_MODEL=gpt-4-turbo-preview
DAV_ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# Permissions
DAV_ALLOW_EXECUTE=false  # Set to true to enable auto-execution (still requires confirmation)

# History
DAV_HISTORY_ENABLED=true
DAV_HISTORY_DB=~/.dav/history.db

# Sessions
DAV_SESSION_DIR=~/.dav/sessions
```

## Security Features

- **Shell Injection Protection**: Commands are parsed safely using `shlex`
- **Dangerous Command Detection**: Blocks potentially harmful operations (e.g., `rm -rf /`, fork bombs)
- **Confirmation Required**: Always asks for confirmation before executing commands
- **Input Validation**: Truncates large inputs to prevent token overflow
  - Directory listings limited to 15 files
  - Stdin input limited to 1000 characters
  - Path lengths limited to 200 characters

## Use Cases

- **Incident Response**: Quickly analyze logs and get remediation steps
- **Server Hardening**: Get security recommendations and execute fixes
- **Network Diagnostics**: Troubleshoot connectivity and configuration issues
- **Automated Maintenance**: Execute routine tasks with AI guidance
- **Development**: Get instant help with command-line tools and scripts

## Project Structure

```
dav/
├── __init__.py
├── cli.py           # Main CLI interface
├── config.py        # Configuration management
├── context.py       # Context detection and collection
├── ai_backend.py    # AI backend integration (OpenAI/Anthropic)
├── terminal.py      # Terminal formatting and rendering
├── history.py       # Query history management
├── session.py       # Session persistence
└── executor.py      # Secure command execution
```

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

