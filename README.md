# n8n Status Script

![GitHub release](https://img.shields.io/github/v/release/urbanadventurer/n8n_tools)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![GitHub stars](https://img.shields.io/github/stars/urbanadventurer/n8n_tools)

A command-line utility for monitoring n8n workflow executions.

![Screenshot](https://github.com/user-attachments/assets/9a2f7b78-457d-4d02-804c-bbbb53846920)

## Overview

This script provides a convenient way to view the status and statistics of your [n8n](https://n8n.io) workflow executions directly from the terminal. It connects to the n8n SQLite database and displays execution data in a nicely formatted table.

Postgres is not currently supported.

## ✨ Features

- View recent workflow executions with detailed status information
- See execution times, workflow names, and current status
- Color-coded output for easy status identification
- Filter by number of executions to display

## 📋 Requirements

- Python 3.6+
- SQLite3 (included in Python standard library)
- An n8n instance with its SQLite database file

## 🚀 Installation

No installation is required. Simply download the script and run it with Python.

```bash
# Clone this repository or download the script
git clone https://github.com/yourusername/n8n-status.git
cd n8n-status

# Make the script executable (optional)
chmod +x n8n-status.py
```

## ⚙️ Configuration

The script now supports configuration via an INI file. Create a `.n8n-status-config.ini` file in either:
- The current directory where you run the script
- Your home directory (`~/`)

Example configuration file:

```ini
[n8n-status]
# Default path to the n8n SQLite database
db_path = ~/.n8n/database.sqlite

# Default limit for the number of execution records to display
limit = 15
```

The configuration uses Python's built-in `configparser` module, so no external dependencies are required.

## 💻 Usage

```bash
# Basic usage (will use config file if available)
python3 n8n-status.py

# Override config settings with command line arguments
python3 n8n-status.py --db-path /path/to/n8n/database.sqlite --limit 10

```

### Command Line Options

```
./n8n-status.py --help
usage: n8n-status.py [-h] [--db-path DB_PATH] [--limit LIMIT] [--errors] [--running] [--waiting] [--id ID] [--workflow WORKFLOW]

n8n workflow execution status viewer for SQLite

options:
  -h, --help           show this help message and exit
  --db-path DB_PATH    Path to SQLite database file
  --limit LIMIT        Maximum number of execution records to display (default: 15)
  --errors, -e         Show only executions with errors
  --running, -r        Show only running executions
  --waiting, -w        Show only waiting executions
  --id ID              Show details for a specific execution ID
  --workflow WORKFLOW  Filter by workflow name (case insensitive substring match)
```

### Finding Your n8n Database

The SQLite database is typically located in:

- Default location: `~/.n8n/database.sqlite`
- Docker: Inside the container at `/home/node/.n8n/database.sqlite`
- Custom location: Wherever you configured n8n to store its data

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
