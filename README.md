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

**After installation**, run the setup command to configure Dav:
```bash
dav --setup
```

This will create the necessary directories and guide you through API key configuration.

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

## Uninstallation

To completely remove Dav and all its data:

1. **Remove data files first** (while the package is still installed):
   ```bash
   dav --uninstall-data
   ```

2. **Uninstall the package**:
   ```bash
   pip uninstall dav-ai
   ```

**Note**: Run `dav --uninstall-data` before uninstalling the package, otherwise the `dav` command won't be available to clean up data files.

This will remove:
- Configuration files (`~/.dav/.env`)
- History database (`~/.dav/history.db`)
- Session files (`~/.dav/sessions/`)
- The entire `~/.dav/` directory

**Other uninstall commands:**
- `dav --list-data` - List all Dav data files and directories
- `dav --uninstall-info` - Show detailed uninstall instructions

## Quick Start

1. **Set up your API key**:

The `.dav` directory will be created automatically on first run. You need to create the `.env` file manually:

```bash
# Create the .dav directory (if it doesn't exist yet)
mkdir -p ~/.dav

# Create the .env file with your API key
# For OpenAI:
cat > ~/.dav/.env << EOF
OPENAI_API_KEY=your_openai_api_key_here
DAV_BACKEND=openai
DAV_DEFAULT_MODEL=gpt-4-turbo-preview
EOF

# Or for Anthropic:
cat > ~/.dav/.env << EOF
ANTHROPIC_API_KEY=your_anthropic_api_key_here
DAV_BACKEND=anthropic
DAV_DEFAULT_MODEL=claude-3-5-sonnet-20241022
EOF
```

**Alternative**: You can also use a text editor:
```bash
nano ~/.dav/.env
# or
vim ~/.dav/.env
```

Then add your configuration (see Configuration section below for full options).

**Quick Setup**: You can also use the interactive setup command:
```bash
dav --setup
```

This will create the `.dav` directory and guide you through creating the `.env` file.

**Note**: The `~/.dav` directory will be automatically created when you first run Dav, but you need to create the `.env` file manually (or use `dav --setup`) before using Dav.

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

### Uninstall Data
```bash
# List all data files
dav --list-data

# Remove all data files (with confirmation)
dav --uninstall-data

# Show uninstall instructions
dav --uninstall-info
```

### Analyze Logs
```bash
cat /var/log/syslog | dav "what errors do you see?"
```

## Configuration

Dav looks for configuration in a `.env` file. You can place it in:
- `~/.dav/.env` (recommended, user-specific)
- `.env` in your current working directory (project-specific)

**To create the configuration file:**

```bash
# Create directory if it doesn't exist
mkdir -p ~/.dav

# Create and edit the .env file
nano ~/.dav/.env
# or use your preferred editor
```

Then add your configuration:

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

