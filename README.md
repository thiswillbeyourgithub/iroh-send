# iroh_send.py

A self-contained peer-to-peer file transfer script using [prime-iroh](https://github.com/n0-computer/iroh-ffi). Transfer files and directories directly between machines without intermediary servers.

This script was developed with assistance from [aider.chat](https://github.com/Aider-AI/aider/), more specifically using [aider_builder](https://github.com/thiswillbeyourgithub/AiderBuilder).

## Features

- **Peer-to-peer transfer**: Direct file transfers without cloud storage or intermediary servers
- **Directory support**: Automatically compresses and transfers entire directories
- **Progress tracking**: Real-time progress bars showing transfer status
- **Deterministic connections**: Uses shared token to derive connection parameters
- **Zero configuration**: Self-contained script runs via `uv run` with automatic dependency management
- **Integrity verification**: SHA256 hash verification ensures file integrity after transfer
- **Configurable parameters**: Adjust latency, chunk size, and logging verbosity
- **Verbose logging**: Optional debug mode for troubleshooting

## Requirements

- Python 3.8 or higher
- `uv run` (part of the `uv` package manager)

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
uv run iroh_send.py
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
uv run iroh_send.py file1.txt directory/ file2.py
```

The sender will:
1. Display its node ID
2. Connect to the receiver
3. Send metadata about files to transfer
4. Transfer all files/directories with progress tracking
5. Compress each file individually using LZMA compression

### Advanced Options

#### Verbose Mode

Enable detailed logging for troubleshooting:

```bash
uv run iroh_send.py --verbose file1.txt
```

#### Adjust Chunk Size

Control how files are split for transfer (default: 5MB). Supports k/K (kilobytes), m/M (megabytes), g/G (gigabytes):

```bash
# Use 10MB chunks
uv run iroh_send.py --chunk-size=10m file1.txt

# Use 512KB chunks
uv run iroh_send.py --chunk-size=512k file1.txt
```

Note: The receiver ignores the `--chunk-size` parameter as it uses the chunk size specified by the sender.

#### Adjust Latency

Control the latency parameter for send operations in milliseconds (default: 100ms):

```bash
uv run iroh_send.py --latency=50 file1.txt
```

## Examples

### Transfer a single file

Receiver:
```bash
export IROH_SEND_TOKEN="my-unique-token-12345"
uv run iroh_send.py
```

Sender:
```bash
export IROH_SEND_TOKEN="my-unique-token-12345"
uv run iroh_send.py report.pdf
```

### Transfer multiple files and directories

Sender:
```bash
export IROH_SEND_TOKEN="my-unique-token-12345"
uv run iroh_send.py documents/ photos/ notes.txt presentation.pptx
```

### Transfer with verbose logging

Sender:
```bash
export IROH_SEND_TOKEN="my-unique-token-12345"
uv run iroh_send.py --verbose large_project/
```

## How It Works

1. **Token Derivation**: Both sender and receiver derive deterministic seeds from the shared `IROH_SEND_TOKEN` using SHA256 hashing
2. **Node Creation**: Each peer creates an iroh node with their derived seed, resulting in predictable peer IDs
3. **Connection**: Peers connect to each other using the derived peer IDs
4. **Version Check**: Protocol version is verified to ensure compatibility between sender and receiver
5. **Metadata Transfer**: Sender transmits JSON metadata describing files, sizes, SHA256 hashes, and chunk counts
6. **File Transfer**: Files are compressed individually using gzip and transferred sequentially in chunks with progress tracking
7. **Integrity Verification**: Each file's SHA256 hash is verified after transfer to ensure data integrity
8. **Directory Handling**: Directories are walked recursively and each file is compressed and transferred individually, preserving the directory structure
9. **Memory Efficiency**: Files are processed in configurable chunks - data is read, compressed, and sent chunk by chunk without storing entire files in memory. This allows efficient transfer of arbitrarily large files and directories

## Security Considerations

- The `IROH_SEND_TOKEN` should be kept secret and shared only between sender and receiver
- Transfers are peer-to-peer; ensure you trust the peer you're connecting with
- The script will refuse to overwrite existing files/directories on the receiver side

## Troubleshooting

### Connection Issues

- Ensure both sender and receiver use the exact same `IROH_SEND_TOKEN`
- Check that the receiver is started before the sender attempts to connect
- Use `--verbose` flag to see detailed connection logs
- The default connection timeout is 30 retries (approximately 30 seconds)

### Large Files and Directories

The script is designed to handle large files and directories efficiently:

- **Memory efficient**: Files are processed in chunks, so you can transfer arbitrarily large files or directories without running out of memory
- **Configurable chunks**: Adjust `--chunk-size` parameter for optimal performance (default: 5MB)
- **Streaming compression**: Each file chunk is read, compressed with gzip, and sent individually
- **Progress tracking**: The progress bar shows real-time transfer status for all files
- **Compression time**: Very large individual files may take time to compress using gzip. The `--verbose` flag shows detailed transfer information

### Hash Verification Failures

If you see a "Hash mismatch" error:

- The transfer was corrupted and the file was automatically deleted
- Try the transfer again
- If it persists, try adjusting the `--latency` parameter
- Check network stability between sender and receiver

### Performance Tuning

- **Chunk size**: Larger chunks (e.g., `--chunk-size=10m`) may be faster for large files but use more memory
- **Latency**: Lower latency values (e.g., `--latency=50`) may improve speed on fast networks
- **Verbose mode**: Use `--verbose` only for debugging as it generates significant log output

## License

See LICENSE file for details.

## Contributing

This is a self-contained utility script. For issues or improvements, please check if updates are available or modify the script directly for your needs.
