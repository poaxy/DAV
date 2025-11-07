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

#### Option 1: Using pipx (Recommended for CLI tools)

`pipx` is the recommended way to install CLI applications on modern Linux systems:

```bash
# Install pipx if you don't have it
sudo apt install pipx  # Ubuntu/Debian
# or
brew install pipx      # macOS

# Ensure pipx is in PATH
pipx ensurepath

# Install Dav
pipx install git+https://github.com/poaxy/DAV.git
```

**Note**: `pipx` automatically manages virtual environments and adds the command to your PATH.

#### Option 2: Using pip with --user flag

For systems that don't have `pipx` or if you prefer pip:

```bash
pip install --user git+https://github.com/poaxy/DAV.git
```

Then add to PATH:
```bash
# Add to PATH for current session
export PATH="$HOME/.local/bin:$PATH"

# Or add permanently to your shell profile
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

#### Option 3: Using virtual environment

If you prefer a virtual environment:

```bash
python3 -m venv dav-env
source dav-env/bin/activate
pip install git+https://github.com/poaxy/DAV.git
```

**Note**: This requires `git` to be installed on your system. If you don't have git installed:
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
pipx install dav-ai
```

Or if you prefer pip:
```bash
pip install --user dav-ai
export PATH="$HOME/.local/bin:$PATH"
```

### Development Installation

For development, clone the repository and install in editable mode:

```bash
git clone https://github.com/poaxy/DAV.git
cd DAV
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Uninstallation

To completely remove Dav and all its data:

1. **Remove data files first** (while the package is still installed):
   ```bash
   dav --uninstall-data
   ```

2. **Uninstall the package**:
   
   If installed with pipx:
   ```bash
   pipx uninstall dav-ai
   ```
   
   If installed with pip:
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
# Auto-confirm execution without prompts (use with caution)
dav "remove .log files" --execute --yes
```

Dav requests a structured JSON command plan from the assistant when `--execute` is used.
The plan is validated (platform match, sudo usage, working directory) before each command runs.
Commands are displayed first; passing `--yes` skips the confirmation prompt.

### View History
```bash
dav --history
```

### Update Dav
```bash
# Update to the latest version (preserves your configuration)
dav --update
```

This will automatically detect your installation method (pipx, pip --user, or venv) and update accordingly.

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

# Input limits
# Maximum number of characters to read from piped stdin (default 32000)
DAV_MAX_STDIN_CHARS=32000
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

## Troubleshooting

### Externally-managed-environment error

If you see `error: externally-managed-environment` on Ubuntu 23.04+ or Debian 12+, use one of these solutions:

**Best option**: Use `pipx` (recommended for CLI tools):
```bash
sudo apt install pipx
pipx ensurepath
pipx install git+https://github.com/poaxy/DAV.git
```

**Alternative**: Use `--user` flag:
```bash
pip install --user git+https://github.com/poaxy/DAV.git
export PATH="$HOME/.local/bin:$PATH"
```

**Not recommended**: Override the protection (use at your own risk):
```bash
pip install --break-system-packages git+https://github.com/poaxy/DAV.git
```

### Command shows setup screen instead of running query

If running `dav "your question"` shows the setup screen instead of processing your query, you may need to reinstall:

If installed with pipx:
```bash
pipx reinstall git+https://github.com/poaxy/DAV.git
```

If installed with pip:
```bash
pip install --force-reinstall --user git+https://github.com/poaxy/DAV.git
```

This ensures the entry point is correctly configured.

### Command not found: `dav`

If you see `command not found: dav` after installation, the `dav` command is likely installed in `~/.local/bin` which is not on your PATH.

**Solution**: Add `~/.local/bin` to your PATH:

```bash
# For current session
export PATH="$HOME/.local/bin:$PATH"

# To make it permanent, add to your shell profile
# For bash:
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# For zsh:
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

After adding to PATH, verify the installation:
```bash
which dav
dav --help
```

### Empty .env file

If your `.env` file is empty or not being read:

1. Run `dav --setup` to recreate it
2. Or manually create/edit: `nano ~/.dav/.env`
3. Make sure the file contains at least:
   ```
   OPENAI_API_KEY=your_key_here
   DAV_BACKEND=openai
   ```

### Permission errors

If you encounter permission errors when creating files:

```bash
# Ensure .dav directory has correct permissions
mkdir -p ~/.dav
chmod 700 ~/.dav
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

