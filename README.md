# iroh_send.py

A self-contained peer-to-peer file transfer script using [prime-iroh](https://github.com/n0-computer/iroh-ffi). Transfer files and directories directly between machines without intermediary servers.

This script was developed with assistance from [aider.chat](https://github.com/Aider-AI/aider/).

## Features

- **Peer-to-peer transfer**: Direct file transfers without cloud storage or intermediary servers
- **Directory support**: Automatically compresses and transfers entire directories
- **Progress tracking**: Real-time progress bars showing transfer status
- **Deterministic connections**: Uses shared token to derive connection parameters
- **Zero configuration**: Self-contained script runs via `uvx` with automatic dependency management
- **Verbose logging**: Optional debug mode for troubleshooting

## Requirements

- Python 3.8 or higher
- `uvx` (part of the `uv` package manager)

## Installation

No installation needed! The script uses `uvx` to automatically fetch dependencies when run.

If you don't have `uv` installed:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Usage

### Basic Concept

The script operates in two modes:
- **Receiver mode**: Wait for incoming files (run without arguments)
- **Sender mode**: Send files/directories (specify paths as arguments)

Both sender and receiver must use the same `IROH_SEND_TOKEN` environment variable to establish a connection.

### Receiver Mode

On the receiving machine:

```bash
export IROH_SEND_TOKEN="your-secret-token-here"
uvx iroh_send.py
```

The receiver will:
1. Display its node ID
2. Wait for connection from sender
3. Receive metadata about incoming files
4. Verify no filename conflicts exist
5. Receive and save all files with progress tracking

### Sender Mode

On the sending machine:

```bash
export IROH_SEND_TOKEN="your-secret-token-here"
uvx iroh_send.py file1.txt directory/ file2.py
```

The sender will:
1. Display its node ID
2. Connect to the receiver
3. Send metadata about files to transfer
4. Transfer all files/directories with progress tracking
5. Automatically compress directories as `.tar.gz` archives

### Verbose Mode

Enable detailed logging for troubleshooting:

```bash
uvx iroh_send.py --verbose file1.txt
```

## Examples

### Transfer a single file

Receiver:
```bash
export IROH_SEND_TOKEN="my-unique-token-12345"
uvx iroh_send.py
```

Sender:
```bash
export IROH_SEND_TOKEN="my-unique-token-12345"
uvx iroh_send.py report.pdf
```

### Transfer multiple files and directories

Sender:
```bash
export IROH_SEND_TOKEN="my-unique-token-12345"
uvx iroh_send.py documents/ photos/ notes.txt presentation.pptx
```

### Transfer with verbose logging

Sender:
```bash
export IROH_SEND_TOKEN="my-unique-token-12345"
uvx iroh_send.py --verbose large_project/
```

## How It Works

1. **Token Derivation**: Both sender and receiver derive deterministic seeds from the shared `IROH_SEND_TOKEN` using SHA256 hashing
2. **Node Creation**: Each peer creates an iroh node with their derived seed, resulting in predictable peer IDs
3. **Connection**: Peers connect to each other using the derived peer IDs
4. **Metadata Transfer**: Sender transmits JSON metadata describing files, sizes, and types
5. **File Transfer**: Files are transferred sequentially with progress tracking
6. **Directory Handling**: Directories are compressed as `.tar.gz` archives before transfer and extracted on receipt

## Security Considerations

- The `IROH_SEND_TOKEN` should be kept secret and shared only between sender and receiver
- Transfers are peer-to-peer; ensure you trust the peer you're connecting with
- The script will refuse to overwrite existing files/directories on the receiver side
- Use strong, unique tokens for each transfer session

## Troubleshooting

### Connection timeouts

- Ensure both machines can establish peer-to-peer connections (may require NAT traversal)
- Verify both sender and receiver are using the exact same `IROH_SEND_TOKEN`
- Try the `--verbose` flag to see detailed connection logs

### File already exists error

The receiver will abort if any target file/directory already exists. This prevents accidental overwrites. Move or rename existing files before receiving.

### Large directory transfers

Directories are compressed before transfer. Very large directories may take time to compress. The `--verbose` flag shows compression progress.

## License

See LICENSE file for details.

## Contributing

This is a self-contained utility script. For issues or improvements, please check if updates are available or modify the script directly for your needs.
