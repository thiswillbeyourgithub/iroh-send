#!/usr/bin/env python3
"""
Self-contained file transfer script using prime-iroh.

Requirements for uv run:
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "prime-iroh>=0.3.1",
#     "fire",
#     "tqdm",
# ]
# ///

Usage:
    # Receiver mode (no files specified)
    uv run iroh_send.py

    # Sender mode (files/directories specified)
    uv run iroh_send.py file1.txt dir1/ file2.py
"""

import os
import sys
import json
import time
import hashlib
import gzip
import tempfile
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple

import fire
from tqdm import tqdm
from prime_iroh import Node

# Version of the protocol - sender and receiver must match
VERSION = "2.1.1"

# Chunk size for file transfers (5 MB) - files are sent/received in chunks to allow streaming
CHUNK_SIZE = 1024 * 1024 * 5


def parse_size(size_str: str) -> int:
    """Parse size string like '1k', '1.5m', '3g' into bytes.

    Supports suffixes: k/K (kilobytes), m/M (megabytes), g/G (gigabytes).
    Plain numbers without suffix are treated as bytes.

    Parameters
    ----------
    size_str : str
        Size string to parse (e.g., "1k", "1.5M", "3.0g", "1024")

    Returns
    -------
    int
        Size in bytes

    Raises
    ------
    ValueError
        If size string format is invalid
    """
    size_str = size_str.strip()

    # Check if there's a suffix
    if size_str and size_str[-1].lower() in ("k", "m", "g"):
        suffix = size_str[-1].lower()
        number_str = size_str[:-1]
    else:
        # No suffix, treat as bytes
        try:
            return int(float(size_str))
        except ValueError:
            raise ValueError(f"Invalid size format: {size_str}")

    # Parse the number part
    try:
        number = float(number_str)
    except ValueError:
        raise ValueError(f"Invalid size format: {size_str}")

    # Convert to bytes based on suffix - k=1024, m=1024^2, g=1024^3
    multipliers = {
        "k": 1024,
        "m": 1024 * 1024,
        "g": 1024 * 1024 * 1024,
    }

    return int(number * multipliers[suffix])


def derive_seeds(token: str) -> Tuple[int, int]:
    """Derive sender and receiver seeds from token using SHA256."""
    sender_token = token + "sender"
    receiver_token = token + "receiver"

    sender_hash = hashlib.sha256(sender_token.encode()).digest()
    receiver_hash = hashlib.sha256(receiver_token.encode()).digest()

    # Convert first 8 bytes to int for seed
    sender_seed = int.from_bytes(sender_hash[:8], byteorder="big")
    receiver_seed = int.from_bytes(receiver_hash[:8], byteorder="big")

    return sender_seed, receiver_seed


def get_node_id_from_seed(seed: int) -> str:
    """Get the peer ID that would be generated from a given seed."""
    # Create temporary node to get its peer ID
    temp_node = Node.with_seed(num_streams=1, seed=seed)
    node_id = temp_node.node_id()
    temp_node.close()
    return node_id


def establish_connection(node: Node, node_id: str, num_retries: int = 30) -> bool:
    """Establish connection to peer and wait until ready.

    Parameters
    ----------
    node : Node
        The node to establish connection from
    node_id : str
        The peer ID to connect to
    num_retries : int, optional
        Number of connection retries and also seconds to wait for ready state, by default 30

    Returns
    -------
    bool
        True if connection established and ready, False if timed out
    """
    print(f"Connecting to peer {node_id[:16]}...")
    node.connect(peer_id_str=node_id, num_retries=num_retries)

    start_time = time.time()
    while not node.is_ready():
        if time.time() - start_time > num_retries:
            return False
        time.sleep(0.1)

    print("Connected to peer!")
    return True


def main(*files, verbose: bool = False, latency: int = 100, chunk_size: str = "5m"):
    """Main entry point for iroh_send script.

    Parameters
    ----------
    *files : str
        Files or directories to send (sender mode). If empty, runs in receiver mode.
    verbose : bool, optional
        Enable verbose debug logging, by default False
    latency : int, optional
        Latency parameter for send operations in milliseconds, by default 100
    chunk_size : str, optional
        Chunk size for file transfers (e.g., "1k", "1.5m", "3g"), by default "5m"
    """
    # Initialize logging with appropriate level based on verbose flag
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    if verbose:
        logger.debug("Verbose mode enabled")
        logger.debug(f"Python version: {sys.version}")
        logger.debug(f"Working directory: {os.getcwd()}")

    # Get token from environment
    token = os.getenv("IROH_SEND_TOKEN")
    if not token:
        print("ERROR: IROH_SEND_TOKEN environment variable not set")
        sys.exit(1)

    # Parse chunk size - this determines how files are split into chunks for transfer
    try:
        chunk_size_bytes = parse_size(chunk_size)
        logger.debug(f"Chunk size: {chunk_size_bytes} bytes ({chunk_size})")
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Determine mode based on arguments
    if not files:
        print("Running in receiver mode...")
        # Warn if chunk_size was specified - receiver ignores it as chunk size comes from sender's metadata
        if chunk_size != "5m":
            logger.warning(
                f"WARNING: chunk_size parameter ('{chunk_size}') is ignored in receiver mode. "
                "Chunk size is determined by the sender."
            )
        receiver_mode(token, verbose)
    else:
        print(f"Running in sender mode with {len(files)} items...")
        sender_mode(token, list(files), verbose, latency, chunk_size_bytes)


def receiver_mode(token: str, verbose: bool = False):
    """Run in receiver mode - wait for files.

    Parameters
    ----------
    token : str
        Connection token for deriving seeds
    verbose : bool, optional
        Enable verbose debug logging, by default False
    """
    logger = logging.getLogger(__name__)

    logger.debug(f"Token: {token[:8]}...{token[-8:]}")
    sender_seed, receiver_seed = derive_seeds(token)
    logger.debug(f"Sender seed: {sender_seed}")
    logger.debug(f"Receiver seed: {receiver_seed}")

    sender_node_id = get_node_id_from_seed(sender_seed)
    logger.debug(f"Sender node ID: {sender_node_id}")

    # Initialize receiver node
    logger.debug("Initializing receiver node...")
    node = Node.with_seed(1, seed=receiver_seed)
    receiver_node_id = node.node_id()
    print(f"Receiver node ID: {receiver_node_id}")
    logger.debug(f"Full receiver node ID: {receiver_node_id}")

    # Connect to sender
    logger.debug(f"Attempting to connect to sender: {sender_node_id}")
    if not establish_connection(node=node, node_id=sender_node_id, num_retries=30):
        print("ERROR: Failed to connect to sender")
        node.close()
        sys.exit(1)

    print("Receiver ready - waiting for metadata...")

    # Receive metadata
    logger.debug("Starting metadata receive...")
    recv_work = node.irecv(tag=0)
    metadata_bytes = recv_work.wait()
    logger.debug(f"Received {len(metadata_bytes)} bytes of metadata")

    metadata_wrapper = json.loads(metadata_bytes.decode("utf-8"))
    logger.debug(f"Parsed metadata wrapper: {metadata_wrapper}")
    logger.debug(f"Metadata wrapper type: {type(metadata_wrapper)}")

    # Print metadata for visibility regardless of verbose mode
    metadata_json = json.dumps(metadata_wrapper)
    print(f"Metadata JSON ({len(metadata_bytes)} bytes): {metadata_json}")

    # Type checking to ensure metadata_wrapper is a dict - this validates JSON structure
    if not isinstance(metadata_wrapper, dict):
        print(
            f"ERROR: Expected metadata_wrapper to be dict, got {type(metadata_wrapper)}"
        )
        print(f"Metadata wrapper content: {metadata_wrapper}")
        node.close()
        sys.exit(1)

    # Check version compatibility - version mismatch causes immediate crash to prevent protocol errors
    received_version = metadata_wrapper.get("version")
    if received_version != VERSION:
        print(
            f"ERROR: Version mismatch! Receiver version: {VERSION}, Sender version: {received_version}"
        )
        node.close()
        sys.exit(1)

    metadata = metadata_wrapper["items"]
    logger.debug(f"Metadata items type: {type(metadata)}")

    # Type checking to ensure items is a list - this validates JSON structure
    if not isinstance(metadata, list):
        print(f"ERROR: Expected metadata['items'] to be list, got {type(metadata)}")
        print(f"Metadata content: {metadata}")
        node.close()
        sys.exit(1)

    print(f"Received metadata for {len(metadata)} items")

    # Type checking to ensure each item is a dict - this validates JSON structure
    for i, item in enumerate(metadata):
        if not isinstance(item, dict):
            print(f"ERROR: Expected metadata item {i} to be dict, got {type(item)}")
            print(f"Item content: {item}")
            node.close()
            sys.exit(1)

    # Check if any files already exist
    logger.debug("Checking if any destination paths already exist...")
    for item in metadata:
        path = Path(item["path"])
        logger.debug(f"Checking path: {path}")
        if path.exists():
            print(f"ERROR: File already exists: {path}")
            node.close()
            sys.exit(1)

    print("All paths clear - ready to receive files")

    # Calculate total size for progress bar
    total_size = sum(item["size"] for item in metadata)
    logger.debug(
        f"Total size to receive: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)"
    )

    # Receive files with progress bar
    with tqdm(total=total_size, unit="B", unit_scale=True, desc="Receiving") as pbar:
        for i, item in enumerate(metadata):
            path = Path(item["path"])
            logger.debug(f"Receiving item {i + 1}/{len(metadata)}: {path}")

            # Check again that path doesn't exist (safety check)
            if path.exists():
                print(f"ERROR: File created during transfer: {path}")
                node.close()
                sys.exit(1)

            # Create parent directories for final destination
            path.parent.mkdir(parents=True, exist_ok=True)

            # Create temporary file to receive data - writes to temp first for atomicity and safety
            temp_file = tempfile.NamedTemporaryFile(mode="wb", delete=False)
            temp_path = Path(temp_file.name)
            logger.debug(f"Created temporary file: {temp_path}")

            try:
                # Receive and write file in chunks to temporary file
                logger.debug(f"Receiving file in {item['num_chunks']} chunks: {path}")
                file_hasher = hashlib.sha256()

                with temp_file:
                    for chunk_idx in range(item["num_chunks"]):
                        # Receive compressed chunk
                        logger.debug(
                            f"Receiving chunk {chunk_idx + 1}/{item['num_chunks']}"
                        )
                        recv_work = node.irecv(tag=0)
                        compressed_chunk = recv_work.wait()
                        logger.debug(
                            f"Received {len(compressed_chunk)} compressed bytes"
                        )

                        # Decompress chunk using gzip
                        chunk_data = gzip.decompress(compressed_chunk)
                        chunk_size = len(chunk_data)
                        logger.debug(f"Decompressed to {chunk_size} bytes")

                        # Write chunk to temporary file
                        temp_file.write(chunk_data)

                        # Update hash with chunk data
                        file_hasher.update(chunk_data)

                        # Update progress bar with uncompressed chunk size
                        pbar.update(chunk_size)
                        pbar.set_postfix(
                            file=str(path),
                            chunk=f"{chunk_idx + 1}/{item['num_chunks']}",
                        )

                logger.debug(f"Wrote complete file to temp: {temp_path}")

                # Verify SHA256 hash to ensure file integrity after transfer
                received_hash = file_hasher.hexdigest()
                expected_hash = item["sha256"]
                logger.debug(
                    f"Hash verification for {path}: received={received_hash}, expected={expected_hash}"
                )
                if received_hash != expected_hash:
                    logger.error(f"Hash mismatch for {path}! Deleting temp file.")
                    temp_path.unlink()  # Delete the corrupted temp file
                    print(f"ERROR: Hash mismatch for {path}!")
                    print(f"  Expected: {expected_hash}")
                    print(f"  Received: {received_hash}")
                    node.close()
                    sys.exit(1)

                # Hash verified - move temp file to final destination atomically
                logger.debug(f"Moving {temp_path} to {path}")
                shutil.move(str(temp_path), str(path))
                logger.debug(f"Successfully moved file to: {path}")

            except Exception as e:
                # Clean up temp file on any error
                if temp_path.exists():
                    logger.error(
                        f"Error during transfer, cleaning up temp file: {temp_path}"
                    )
                    temp_path.unlink()
                raise

    print("All files received successfully!")
    node.close()


def sender_mode(
    token: str,
    files: List[str],
    verbose: bool = False,
    latency: int = 100,
    chunk_size: int = CHUNK_SIZE,
):
    """Run in sender mode - send files.

    Parameters
    ----------
    token : str
        Connection token for deriving seeds
    files : List[str]
        List of file/directory paths to send
    verbose : bool, optional
        Enable verbose debug logging, by default False
    latency : int, optional
        Latency parameter for send operations in milliseconds, by default 100
    chunk_size : int, optional
        Chunk size in bytes for splitting files, by default CHUNK_SIZE
    """
    logger = logging.getLogger(__name__)

    logger.debug(f"Token: {token[:8]}...{token[-8:]}")
    sender_seed, receiver_seed = derive_seeds(token)
    logger.debug(f"Sender seed: {sender_seed}")
    logger.debug(f"Receiver seed: {receiver_seed}")

    receiver_node_id = get_node_id_from_seed(receiver_seed)
    logger.debug(f"Receiver node ID: {receiver_node_id}")

    # Initialize sender node
    logger.debug("Initializing sender node...")
    node = Node.with_seed(num_streams=1, seed=sender_seed)
    sender_node_id = node.node_id()
    print(f"Sender node ID: {sender_node_id}")
    logger.debug(f"Full sender node ID: {sender_node_id}")

    # Connect to receiver
    logger.debug(f"Attempting to connect to receiver: {receiver_node_id}")
    if not establish_connection(node=node, node_id=receiver_node_id, num_retries=30):
        print("ERROR: Failed to connect to receiver")
        node.close()
        sys.exit(1)

    print(f"Sender ready - preparing metadata for {len(files)} items...")

    # Prepare metadata and calculate sizes
    # Build a mapping from metadata index to original file path for later sending
    file_mapping = []  # List of (original_path, metadata_dict) tuples
    metadata = []
    total_size = 0

    for file_path in files:
        path = Path(file_path)
        logger.debug(f"Processing: {path}")

        if not path.exists():
            print(f"ERROR: File/directory does not exist: {path}")
            node.close()
            sys.exit(1)

        if path.is_dir():
            # Resolve directory name to handle ".", "..", and empty string
            if path.name in (".", "..", ""):
                resolved_name = path.resolve().name
                actual_name = resolved_name if resolved_name else "root"
            else:
                actual_name = path.name

            # Walk directory tree and add each file individually
            logger.debug(f"Walking directory tree: {path}")
            for file_path_obj in path.rglob("*"):
                if file_path_obj.is_file():
                    # Calculate relative path that preserves directory structure
                    relative_path = file_path_obj.relative_to(path.parent)

                    # Read file to get size and hash
                    with open(file_path_obj, "rb") as f:
                        file_data = f.read()
                    # Compute SHA256 hash of the original file data to verify integrity after transfer
                    file_hash = hashlib.sha256(file_data).hexdigest()
                    file_size = len(file_data)

                    logger.debug(
                        f"File {file_path_obj}: {file_size} bytes, SHA256: {file_hash}"
                    )

                    num_chunks = (
                        file_size + chunk_size - 1
                    ) // chunk_size  # Ceiling division
                    meta_item = {
                        "path": str(relative_path),
                        "size": file_size,
                        "sha256": file_hash,
                        "num_chunks": num_chunks,
                    }
                    metadata.append(meta_item)
                    file_mapping.append((file_path_obj, meta_item))
                    total_size += file_size
        else:
            # Resolve file name to handle edge cases
            if path.name in (".", "..", ""):
                resolved_name = path.resolve().name
                actual_name = resolved_name if resolved_name else "root"
            else:
                actual_name = path.name

            # Read file to get size and hash
            with open(path, "rb") as f:
                file_data = f.read()
            # Compute SHA256 hash of the original file data to verify integrity after transfer
            file_hash = hashlib.sha256(file_data).hexdigest()
            file_size = len(file_data)

            logger.debug(f"File {path}: {file_size} bytes, SHA256: {file_hash}")

            num_chunks = (file_size + chunk_size - 1) // chunk_size  # Ceiling division
            meta_item = {
                "path": actual_name,
                "size": file_size,
                "sha256": file_hash,
                "num_chunks": num_chunks,
            }
            metadata.append(meta_item)
            file_mapping.append((path, meta_item))
            total_size += file_size

    # Send metadata with version - version is included to ensure protocol compatibility
    logger.debug(
        f"Total size to send: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)"
    )
    metadata_wrapper = {"version": VERSION, "items": metadata}
    metadata_json = json.dumps(metadata_wrapper)
    metadata_bytes = metadata_json.encode("utf-8")
    print(f"Metadata JSON ({len(metadata_bytes)} bytes): {metadata_json}")

    logger.debug("Sending metadata...")
    send_work = node.isend(msg=metadata_bytes, tag=0, latency=latency)
    send_work.wait()
    logger.debug("Metadata sent successfully")

    print(f"Metadata sent - ready to send files")

    # Send files with progress bar
    with tqdm(total=total_size, unit="B", unit_scale=True, desc="Sending") as pbar:
        for i, (original_path, meta) in enumerate(file_mapping):
            logger.debug(f"Sending item {i + 1}/{len(file_mapping)}: {original_path}")

            # Send file in chunks
            logger.debug(
                f"Sending file in {meta['num_chunks']} chunks: {original_path}"
            )
            with open(original_path, "rb") as f:
                for chunk_idx in range(meta["num_chunks"]):
                    # Read chunk
                    chunk_data = f.read(chunk_size)
                    actual_chunk_size = len(chunk_data)
                    logger.debug(
                        f"Read chunk {chunk_idx + 1}/{meta['num_chunks']}: {actual_chunk_size} bytes"
                    )

                    # Compress chunk using gzip
                    compressed_chunk = gzip.compress(chunk_data)
                    logger.debug(f"Compressed chunk to {len(compressed_chunk)} bytes")

                    # Send compressed chunk
                    send_work = node.isend(msg=compressed_chunk, tag=0, latency=latency)
                    send_work.wait()
                    logger.debug(f"Sent chunk {chunk_idx + 1}/{meta['num_chunks']}")

                    # Update progress bar with uncompressed chunk size
                    pbar.update(actual_chunk_size)
                    pbar.set_postfix(
                        file=meta["path"], chunk=f"{chunk_idx + 1}/{meta['num_chunks']}"
                    )

    print("All files sent successfully!")
    node.close()


if __name__ == "__main__":
    fire.Fire(main)
