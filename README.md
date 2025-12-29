# Dav

**An intelligent, context-aware AI assistant built directly into your Linux and macOS terminal.**

Dav transforms your terminal into an AI-powered system administration assistant that understands your system context, executes commands safely, and helps you manage your infrastructure with natural language.

**GitHub**: [https://github.com/poaxy/DAV](https://github.com/poaxy/DAV)

---

## Table of Contents

- [What is Dav?](#what-is-dav)
- [What Can Dav Do?](#what-can-dav-do)
- [Dav vs. Other AI Assistants](#dav-vs-other-ai-assistants)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
- [Examples by Scenario](#examples-by-scenario)
- [Configuration](#configuration)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Uninstallation](#uninstallation)
- [Contributing](#contributing)
- [License](#license)

---

## What is Dav?

Dav is a terminal-based AI assistant designed specifically for system administrators, DevOps engineers, and power users. Unlike general-purpose AI chatbots, Dav is built with deep understanding of:

- **System Administration**: Linux/macOS system management, service configuration, troubleshooting
- **Cybersecurity**: Log analysis, threat detection, security hardening, vulnerability assessment
- **Network Administration**: Network configuration, monitoring, troubleshooting
- **Command Execution**: Safe, validated command execution with automatic feedback loops

Dav operates directly in your terminal, automatically detecting your operating system, current directory, and system context. It can execute commands (with your approval), analyze logs, troubleshoot issues, and automate repetitive tasks—all through natural language conversation.

### Key Philosophy

Dav follows a **security-first** approach: it analyzes requests, understands context, and asks for confirmation before executing potentially dangerous operations. It's designed to be a helpful assistant, not a blind executor.

---

## What Can Dav Do?

### Core Capabilities

1. **Context-Aware Assistance**
   - Automatically detects your OS, distribution, and current directory
   - Understands piped input from other commands
   - Maintains conversation context across multiple queries

2. **Multi-Provider AI Support**
   - **OpenAI** (GPT-4, GPT-4 Turbo)
   - **Anthropic** (Claude 3.5 Sonnet)
   - **Google Gemini** (Gemini 1.5 Pro)
   - Automatic failover if one provider is unavailable

3. **Command Execution**
   - Execute commands with confirmation prompts
   - Automatic feedback loops: analyzes command output and determines next steps
   - Platform-specific command generation (Linux vs macOS)
   - Dangerous command detection and blocking

4. **Interactive Conversations**
   - Multi-turn conversations with `dav -i`
   - Session persistence across terminal sessions
   - Command mode and interactive mode switching

5. **Log Analysis**
   - Deep analysis of system logs, application logs, security logs
   - Error pattern detection and root cause analysis
   - Actionable recommendations based on findings

6. **Automation & Scheduling**
   - Automation mode for non-interactive execution
   - Natural language cron job scheduling
   - Automated task logging and reporting

7. **Security Features**
   - Shell injection protection
   - Dangerous command detection
   - File permission validation
   - Input sanitization and validation

---

## Dav vs. Other AI Assistants

### Dav vs. ChatGPT/Claude Web Interface

| Feature | Dav | Web AI Assistants |
|---------|-----|------------------|
| **System Context** | ✅ Automatic (OS, directory, stdin) | ❌ Manual copy-paste |
| **Command Execution** | ✅ Direct execution with safety checks | ❌ Manual copy-paste only |
| **Terminal Integration** | ✅ Native terminal tool | ❌ Browser-based |
| **Session Persistence** | ✅ Automatic across sessions | ❌ Per-conversation only |
| **Piped Input** | ✅ Automatic detection | ❌ Manual input required |
| **Automation** | ✅ Cron scheduling, automation mode | ❌ Not available |
| **Feedback Loops** | ✅ Automatic command result analysis | ❌ Manual iteration |

### Dav vs. ShellGPT/AI Shell Tools

| Feature | Dav | Other Shell AI Tools |
|---------|-----|---------------------|
| **Multi-Provider** | ✅ OpenAI, Anthropic, Gemini with failover | ⚠️ Usually single provider |
| **Context Awareness** | ✅ Full system context (OS, directory, stdin) | ⚠️ Limited context |
| **Security** | ✅ Dangerous command detection, validation | ⚠️ Varies by tool |
| **Feedback Loops** | ✅ Automatic multi-step execution | ⚠️ Usually single-step |
| **Scheduling** | ✅ Natural language cron scheduling | ❌ Not available |
| **Session Management** | ✅ Persistent sessions across terminals | ⚠️ Limited or none |

### Dav vs. Traditional Shell Scripts

| Feature | Dav | Shell Scripts |
|---------|-----|---------------|
| **Natural Language** | ✅ Plain English requests | ❌ Requires scripting knowledge |
| **Adaptability** | ✅ Handles edge cases intelligently | ⚠️ Fixed logic |
| **Context Understanding** | ✅ Understands system state | ❌ Manual state checking |
| **Error Recovery** | ✅ Automatic retry and adaptation | ⚠️ Manual error handling |
| **Learning** | ✅ Learns from command outputs | ❌ Static behavior |

### Why Choose Dav?

- **Built for System Administration**: Designed specifically for sysadmin tasks, not general chat
- **Safety First**: Multiple layers of security validation before command execution
- **Intelligent Execution**: Automatic feedback loops analyze results and determine next steps
- **Production Ready**: Automation mode and scheduling for real-world infrastructure management
- **Multi-Provider Resilience**: Automatic failover ensures availability even if one AI provider is down

---

## Installation

### Prerequisites

- Python 3.8 or higher
- `git` (for installation from GitHub)
- An API key from at least one provider:
  - OpenAI API key ([get one here](https://platform.openai.com/api-keys))
  - Anthropic API key ([get one here](https://console.anthropic.com/))
  - Google Gemini API key ([get one here](https://makersuite.google.com/app/apikey))

### Quick Install (Recommended)

**Using pipx** (isolated installation, recommended):

```bash
# Install pipx if needed
sudo apt install pipx  # Ubuntu/Debian
brew install pipx      # macOS
sudo dnf install pipx  # Fedora

# Install Dav
pipx install git+https://github.com/poaxy/DAV.git
```

**Using pip** (user installation):

```bash
pip install --user git+https://github.com/poaxy/DAV.git
export PATH="$HOME/.local/bin:$PATH"  # Add to ~/.bashrc or ~/.zshrc for persistence
```

**Using virtual environment** (isolated environment):

```bash
python3 -m venv dav-env
source dav-env/bin/activate
pip install git+https://github.com/poaxy/DAV.git
```

### Verify Installation

```bash
dav --version  # Should show version information
dav            # Should trigger setup wizard
```

---

## Quick Start

### First-Time Setup

After installation, Dav will automatically prompt you to set up on first use:

```bash
dav "how do I check disk usage?"
```

Or run setup manually:

```bash
dav --setup
```

The setup wizard will:
1. Create `~/.dav` directory
2. Prompt for AI backend choice (OpenAI, Anthropic, or Gemini)
3. Ask for your API key
4. Create configuration file with secure permissions

### Manual Configuration

Alternatively, create `~/.dav/.env` manually:

```bash
mkdir -p ~/.dav
nano ~/.dav/.env
```

Add your configuration:

```bash
OPENAI_API_KEY=sk-your-key-here
DAV_BACKEND=openai
DAV_DEFAULT_MODEL=gpt-4-turbo-preview
```

Set secure permissions:

```bash
chmod 600 ~/.dav/.env
```

---

## Usage Guide

### Basic Query (Analysis Mode)

Get explanations and recommendations without executing commands:

```bash
dav "how do I check disk usage?"
dav "what's the difference between systemd and init?"
dav "explain this error: Permission denied"
```

### Execute Commands

Execute commands with confirmation:

```bash
# Single command execution
dav "list processes using port 80" --execute

# Auto-confirm (use with caution)
dav "update system packages" --execute --yes

# Multi-step tasks with automatic feedback loops
dav "check if nginx is running, if not start it" --execute
```

### Interactive Mode

Start a multi-turn conversation:

```bash
dav -i
```

In interactive mode:
- Type queries naturally
- Use `>` prefix to execute shell commands directly
- Use `/cmd` to switch to command mode
- Use `/dav <query>` to ask Dav questions in command mode
- Use `/int` to switch back to interactive mode
- Use `/clear` to clear session history
- Use `/exit` or `exit` to quit

Example session:

```
dav> check disk space
[Dav analyzes and shows disk usage]

dav> find large files in /var/log
[Dav finds and lists large files]

dav> > ls -lh /var/log
[Executes command directly]

dav> /cmd
[Switches to command mode]

> pwd
/home/user

> /dav what's in this directory?
[Dav analyzes current directory]

> /int
[Switches back to interactive mode]

dav> exit
```

### Session Persistence

Maintain context across multiple queries:

```bash
# Start a session
dav --session myproject "what's in the current directory?"

# Continue the same session later
dav --session myproject "analyze that log file we saw earlier"
dav --session myproject "fix the errors we found"
```

### Piped Input

Analyze output from other commands:

```bash
# Analyze log files
tail -n 100 /var/log/syslog | dav "what errors do you see?"

# Analyze command output
ps aux | dav "which processes are using the most memory?"

# Analyze file contents
cat error.log | dav "explain these errors"
```

### Automation Mode

Run non-interactive tasks with automatic execution:

```bash
# Automation mode (no confirmations, auto-execute, logging)
dav --automation "update system packages and clean cache"

# Automation mode with piped input
cat maintenance.sh | dav --automation "review and execute this script"
```

### Scheduling Tasks

Schedule tasks using natural language:

```bash
# Schedule a daily task
dav --schedule "update system packages every day at 3 AM"

# Schedule a weekly task
dav --schedule "clean log files every Sunday at midnight"

# Schedule a custom task
dav --schedule "check disk space every 6 hours"
```

View and manage cron jobs:

```bash
# View scheduled tasks
crontab -l

# Edit cron jobs manually
crontab -e
```

### Update Dav

Update to the latest version:

```bash
dav --update
```

This preserves your configuration while updating the package.

### Root Installation (for Automation)

Install Dav for root user (alternative to sudoers configuration):

```bash
dav --install-for-root
```

This allows Dav to run as root for automation tasks without sudoers configuration.

---

## Examples by Scenario

### Scenario 1: System Monitoring & Health Checks

**Check system health:**

```bash
# Basic system check
dav "check system health and show any issues"

# Detailed analysis
dav "analyze system logs for errors and warnings from the last 24 hours"

# Resource monitoring
dav "show CPU, memory, and disk usage"
```

**With execution:**

```bash
# Check and fix issues automatically
dav --execute "check system health and fix any problems found"

# Monitor and alert
dav --execute "check disk space, if above 80% send alert"
```

### Scenario 2: Log Analysis & Troubleshooting

**Analyze logs:**

```bash
# Analyze system logs
sudo journalctl -p err -n 100 | dav "analyze these errors and explain what's wrong"

# Analyze application logs
cat /var/log/nginx/error.log | dav "what errors are in this nginx log?"

# Analyze security logs
sudo tail -n 200 /var/log/auth.log | dav "check for suspicious login attempts"
```

**Troubleshoot issues:**

```bash
# Interactive troubleshooting
dav -i
dav> service nginx is not starting
dav> [Dav analyzes and provides solution]
dav> fix it
dav> [Dav executes fix commands]
```

### Scenario 3: Package Management & Updates

**Update systems:**

```bash
# Ubuntu/Debian
dav --execute "update, upgrade, and clean the system"

# Fedora/RHEL
dav --execute "update system packages using dnf"

# macOS
dav --execute "update homebrew packages"
```

**Install packages:**

```bash
# Install with dependencies
dav --execute "install nginx and configure it to start on boot"

# Install development tools
dav --execute "install build-essential and python3-dev"
```

### Scenario 4: Service Management

**Manage services:**

```bash
# Check service status
dav "check status of all systemd services"

# Start/stop services
dav --execute "restart nginx and verify it's running"

# Enable services
dav --execute "enable and start docker service"
```

**Troubleshoot services:**

```bash
# Diagnose service issues
dav "nginx service is failing, diagnose and fix"

# Service logs
sudo journalctl -u nginx -n 50 | dav "analyze nginx service logs"
```

### Scenario 5: Network Configuration & Troubleshooting

**Network diagnostics:**

```bash
# Check network connectivity
dav "test network connectivity to google.com and show route"

# Analyze network configuration
dav "show network interfaces and their configurations"

# Port analysis
dav "show what's listening on port 80 and 443"
```

**Firewall management:**

```bash
# Configure firewall
dav --execute "check if ufw is enabled, if not enable it and allow SSH"

# Port management
dav --execute "open port 8080 in firewall for web server"
```

### Scenario 6: Security Hardening

**Security analysis:**

```bash
# Security audit
dav "perform basic security check of this system"

# User account analysis
dav "list all user accounts and check for security issues"

# Permission analysis
dav "check file permissions in /etc for security issues"
```

**Security fixes:**

```bash
# Automated security hardening
dav --execute "apply basic security hardening to this system"

# SSH configuration
dav --execute "secure SSH configuration (disable root login, use key auth)"
```

### Scenario 7: File & Directory Management

**File operations:**

```bash
# Find files
dav "find all .log files larger than 100MB"

# Clean up
dav --execute "find and remove old log files older than 30 days"

# Organize files
dav --execute "organize downloads folder by file type"
```

**Directory management:**

```bash
# Analyze directory structure
dav "analyze current directory and suggest organization"

# Create project structure
dav --execute "create a project structure for a Python web app"
```

### Scenario 8: Database Management

**Database operations:**

```bash
# Database backup
dav --execute "create a backup of MySQL database 'mydb'"

# Database analysis
dav "show database sizes and table counts for all databases"

# Query analysis
mysql -e "SHOW PROCESSLIST" | dav "analyze running database queries"
```

### Scenario 9: Docker & Container Management

**Container management:**

```bash
# Container status
dav "show status of all Docker containers"

# Container operations
dav --execute "restart all stopped Docker containers"

# Image management
dav "list Docker images and show disk usage"
```

### Scenario 10: Automation & Scheduled Tasks

**One-time automation:**

```bash
# Maintenance task
dav --automation "update packages, clean cache, and remove old logs"

# Backup task
dav --automation "backup important files to /backup directory"
```

**Scheduled automation:**

```bash
# Daily updates
dav --schedule "update system packages every day at 3 AM"

# Weekly cleanup
dav --schedule "clean log files and temporary files every Sunday at 2 AM"

# Hourly monitoring
dav --schedule "check disk space every 6 hours and alert if above 90%"
```

**View automation logs:**

```bash
# Logs are saved to ~/.dav/logs/
ls ~/.dav/logs/
cat ~/.dav/logs/dav_20240101_030000.log
```

### Scenario 11: Development & DevOps

**Project setup:**

```bash
# Create development environment
dav --execute "set up a Python virtual environment and install dependencies from requirements.txt"

# Configure CI/CD
dav "show me how to set up GitHub Actions for this project"
```

**Code analysis:**

```bash
# Analyze code
cat script.py | dav "review this Python script for errors and improvements"

# Debug issues
python app.py 2>&1 | dav "analyze these Python errors and suggest fixes"
```

### Scenario 12: System Recovery & Emergency

**Emergency troubleshooting:**

```bash
# System won't boot - analyze from recovery mode
dav "system won't boot, analyze boot logs and suggest fixes"

# Disk space emergency
dav --execute "disk is full, find and remove largest files safely"

# Service recovery
dav --execute "critical service is down, diagnose and restore it"
```

---

## Configuration

### Configuration File Location

Main configuration: `~/.dav/.env`

### Configuration Options

```bash
# API Keys (at least one required)
OPENAI_API_KEY=sk-...           # OpenAI
ANTHROPIC_API_KEY=sk-ant-...    # Anthropic Claude
GEMINI_API_KEY=sk-gem-...       # Gemini (Google AI)
GOOGLE_API_KEY=sk-gem-...       # Alternative to GEMINI_API_KEY

# Backend Selection
DAV_BACKEND=openai  # Options: "openai", "anthropic", "gemini"

# Model Selection
DAV_DEFAULT_MODEL=gpt-4-turbo-preview
DAV_OPENAI_MODEL=gpt-4-turbo-preview
DAV_ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
DAV_GEMINI_MODEL=gemini-1.5-pro-latest

# Permissions
DAV_ALLOW_EXECUTE=false  # Set to "true" to allow execution without --execute flag

# Sessions
DAV_SESSION_DIR=~/.dav/sessions  # Directory for session files

# Context Management
DAV_MAX_STDIN_CHARS=32000        # Maximum stdin characters to capture
DAV_MAX_CONTEXT_TOKENS=80000     # Maximum tokens for context window
DAV_MAX_CONTEXT_MESSAGES=100     # Maximum messages to include in context

# Automation Settings
DAV_AUTOMATION_SUDO_METHOD=sudoers  # Options: "sudoers", "root"
DAV_AUTOMATION_LOG_DIR=~/.dav/logs  # Directory for automation logs
DAV_AUTOMATION_LOG_RETENTION_DAYS=30  # Days to retain automation logs
```

### Multi-Provider Setup (Failover)

Configure multiple providers for automatic failover:

```bash
# Primary provider
DAV_BACKEND=openai
OPENAI_API_KEY=sk-...

# Backup providers (for automatic failover)
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=sk-gem-...
```

If the primary provider fails, Dav automatically switches to available backup providers.

### Sudoers Configuration (for Automation)

For automation tasks requiring sudo, configure password-less sudo:

```bash
dav --cron-setup
```

This will:
- Check current sudoers configuration
- Optionally configure NOPASSWD for specific commands
- Provide instructions for manual configuration

---

## Security

### Built-in Security Features

1. **Dangerous Command Detection**
   - Blocks destructive commands (`rm -rf /`, `dd if=/dev/zero`, etc.)
   - Requires explicit user request for dangerous operations
   - Special checks for automation mode (blocks reboot/shutdown)

2. **Command Validation**
   - Shell injection protection
   - Command parsing and validation before execution
   - Platform-specific command verification

3. **File Security**
   - Secure file permissions on configuration files (600)
   - Permission validation before reading sensitive files
   - Warnings for insecure file permissions

4. **Input Validation**
   - Query length limits to prevent token overflow
   - Input sanitization
   - Prompt injection detection

5. **Confirmation Prompts**
   - Always asks for confirmation before executing commands (unless `--yes` or automation mode)
   - Shows command before execution
   - Clear warnings for potentially dangerous operations

### Security Best Practices

1. **API Keys**: Store API keys securely in `~/.dav/.env` with 600 permissions
2. **Automation**: Use automation mode only for trusted tasks
3. **Sudoers**: Configure sudoers carefully for automation (use specific commands when possible)
4. **Review Commands**: Always review commands before confirming execution
5. **Session Files**: Session files may contain sensitive information; keep `~/.dav/sessions` secure

### Dangerous Commands (Blocked by Default)

These commands are blocked unless explicitly requested:
- System reboot/shutdown: `reboot`, `shutdown`, `poweroff`, `halt`
- System file deletion: `rm -rf /etc`, `rm -rf /usr`, etc.
- Disk operations: `dd if=/dev/zero`, `mkfs`, `wipefs`
- Bootloader modification: `grub-install` with dangerous flags
- Root password changes: `passwd root`
- Security feature disabling: Turning off firewalls, SELinux, etc.

---

## Troubleshooting

### Command not found: `dav`

**Solution**: Add `~/.local/bin` to your PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc  # or ~/.zshrc
source ~/.bashrc  # or source ~/.zshrc
```

### Externally-managed-environment error

**Solution**: Use `pipx` (recommended) or `pip install --user`:

```bash
# Install pipx
sudo apt install pipx  # Ubuntu/Debian
brew install pipx      # macOS

# Install with pipx
pipx install git+https://github.com/poaxy/DAV.git
```

### Empty .env file or API key not found

**Solution**: Run setup wizard:

```bash
dav --setup
```

Or manually create `~/.dav/.env` with your API key.

### API errors (rate limits, authentication)

**Solution**: 
- Check your API key is correct
- Verify you have credits/quota with your provider
- Configure multiple providers for automatic failover
- Check network connectivity

### Commands not executing

**Solution**:
- Use `--execute` flag for command execution
- Check `DAV_ALLOW_EXECUTE` setting in config
- Review confirmation prompts (commands require approval)
- Check command validation errors

### Automation mode not working

**Solution**:
- Ensure password-less sudo is configured: `dav --cron-setup`
- Check automation logs: `~/.dav/logs/`
- Verify task syntax in cron: `crontab -l`
- Use `--install-for-root` for root user installation

### Session not persisting

**Solution**:
- Check `DAV_SESSION_DIR` in configuration
- Verify directory permissions: `ls -la ~/.dav/sessions`
- Use explicit session ID: `dav --session myid "query"`

### Provider failover not working

**Solution**:
- Ensure multiple API keys are configured
- Check provider priority in configuration
- Review failover logs in terminal output
- Verify API keys are valid

---

## Uninstallation

### Complete Uninstallation

Remove all data files and uninstall the package:

```bash
dav --uninstall
```

This will:
- Remove all data files and configuration (`~/.dav` directory)
- Uninstall the dav-ai package automatically
- Detect your installation method (pipx, pip, or venv) and use the appropriate uninstall command

**Note**: This is a complete uninstall. If you only want to remove data files while keeping the package installed, manually delete the `~/.dav` directory:

```bash
rm -rf ~/.dav
```

### Manual Uninstallation

**If installed with pipx:**
```bash
pipx uninstall dav-ai
```

**If installed with pip:**
```bash
pip uninstall dav-ai
```

**If installed in virtual environment:**
```bash
deactivate  # if activated
rm -rf dav-env
```

Then remove configuration:
```bash
rm -rf ~/.dav
```

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/poaxy/DAV.git
cd DAV

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .
```

### Reporting Issues

Please report bugs, suggest features, or ask questions by opening an issue on GitHub.

---

## License

MIT

---

## Acknowledgments

Dav is built with the following excellent open-source projects:
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Rich](https://github.com/Textualize/rich) - Terminal formatting
- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- [Google Generative AI](https://github.com/google/generative-ai-python)
- [Plumbum](https://plumbum.readthedocs.io/) - Command execution
- [python-dotenv](https://github.com/theskumar/python-dotenv) - Environment management

---

**Made with ❤️ for system administrators and DevOps engineers**
