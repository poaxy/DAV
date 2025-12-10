# Dav

An intelligent, context-aware AI assistant built directly into the Linux terminal.

**GitHub**: [https://github.com/poaxy/DAV](https://github.com/poaxy/DAV)

## Features

- **Context-Aware**: Automatically detects OS, current directory, and piped input
- **Multiple AI Backends**: OpenAI and Anthropic with real-time streaming
- **Interactive Mode**: Multi-turn conversations with `dav -i`
- **Command Execution**: Execute commands with `--execute` (with confirmation)
- **Session Persistence**: Maintain context across queries

## Installation

### Quick Install (Recommended)

```bash
# Install pipx if needed
sudo apt install pipx  # Ubuntu/Debian
brew install pipx      # macOS

# Install Dav
pipx install git+https://github.com/poaxy/DAV.git
```

### Alternative Methods

**Using pip:**
```bash
pip install --user git+https://github.com/poaxy/DAV.git
export PATH="$HOME/.local/bin:$PATH"  # Add to ~/.bashrc or ~/.zshrc for persistence
```

**Using virtual environment:**
```bash
python3 -m venv dav-env
source dav-env/bin/activate
pip install git+https://github.com/poaxy/DAV.git
```

**Note**: Requires `git` to be installed.

## Quick Start

1. **First-time setup (automatic):**
   After installation, simply run `dav` with any command. Setup will run automatically on first use:
   ```bash
   dav "how do I find large files in /var/log?"
   ```
   Or run `dav` with no arguments - setup will trigger automatically:
   ```bash
   dav
   ```
   
   The setup wizard will prompt you to:
   - Choose your AI backend (OpenAI or Anthropic)
   - Enter your API key
   - Configure default settings

2. **Manual setup (optional):**
   If you prefer to configure manually, run:
   ```bash
   dav --setup
   ```
   Or create `~/.dav/.env` manually:
   ```bash
   OPENAI_API_KEY=your_key_here
   DAV_BACKEND=openai
   DAV_DEFAULT_MODEL=gpt-4-turbo-preview
   ```

## Usage

### Basic Query
```bash
dav "how do I check disk usage?"
```

### Interactive Mode
```bash
dav -i
dav> show me running processes
dav> check disk space
dav> exit
```

### Execute Commands
```bash
# With confirmation
dav "list processes using port 80" --execute

# Auto-confirm (use with caution)
dav "update system packages" --execute --yes
```

### With Piped Input
```bash
tail -n 50 error.log | dav "analyze this"
cat /var/log/syslog | dav "what errors do you see?"
```

### Session Persistence
```bash
dav --session debug "what's in the current directory?"
dav --session debug "explain that file"
```

### Update
```bash
dav --update
```

## Configuration

Create `~/.dav/.env`:

```bash
# API Keys (required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Backend Selection
DAV_BACKEND=openai  # or "anthropic"

# Model Selection
DAV_DEFAULT_MODEL=gpt-4-turbo-preview
DAV_ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# Permissions
DAV_ALLOW_EXECUTE=false

# Sessions
DAV_SESSION_DIR=~/.dav/sessions

# Input Limits
DAV_MAX_STDIN_CHARS=32000
```

## Security

- **Shell Injection Protection**: Commands are parsed safely
- **Dangerous Command Detection**: Blocks harmful operations
- **Confirmation Required**: Always asks before executing
- **Input Validation**: Prevents token overflow

## Uninstallation

Remove all data files and uninstall the package in one command:

```bash
dav --uninstall
```

This will:
- Remove all data files and configuration (~/.dav directory)
- Uninstall the dav-ai package automatically
- Detect your installation method (pipx, pip, or venv) and use the appropriate uninstall command

**Note**: This is a complete uninstall. If you only want to remove data files while keeping the package installed, you'll need to manually delete the `~/.dav` directory.

## Troubleshooting

### Command not found: `dav`

Add `~/.local/bin` to your PATH:
```bash
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc  # or ~/.zshrc
```

### Externally-managed-environment error

Use `pipx` (recommended) or `pip install --user`:
```bash
sudo apt install pipx
pipx install git+https://github.com/poaxy/DAV.git
```

### Empty .env file

Run `dav --setup` or manually create `~/.dav/.env` with your API key.

## License

MIT

## Contributing

Contributions welcome! Please submit a Pull Request.
