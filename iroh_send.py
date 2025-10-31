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
import lzma
import tempfile
import logging
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any, Tuple

import fire
from tqdm import tqdm
from prime_iroh import Node

# Version of the protocol - sender and receiver must match
VERSION = "2.1.0"


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


def wait_with_timeout(work, timeout: int = 30):
    """Wait for work to complete with a timeout.

    Parameters
    ----------
    work : object
        Work object with a wait() method
    timeout : int, optional
        Timeout in seconds, by default 30

    Returns
    -------
    Any
        Result from work.wait()

    Raises
    ------
    TimeoutError
        If operation times out
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(work.wait)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Operation timed out after {timeout} seconds")


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


def main(*files, verbose: bool = False, latency: int = 1000):
    """Main entry point for iroh_send script.

    Parameters
    ----------
    *files : str
        Files or directories to send (sender mode). If empty, runs in receiver mode.
    verbose : bool, optional
        Enable verbose debug logging, by default False
    latency : int, optional
        Latency parameter for send operations in milliseconds, by default 1000
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

    # Determine mode based on arguments
    if not files:
        print("Running in receiver mode...")
        receiver_mode(token, verbose)
    else:
        print(f"Running in sender mode with {len(files)} items...")
        sender_mode(token, list(files), verbose, latency)


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
    try:
        metadata_bytes = wait_with_timeout(recv_work, timeout=30)
    except TimeoutError as e:
        print(f"ERROR: {e}")
        node.close()
        sys.exit(1)
    logger.debug(f"Received {len(metadata_bytes)} bytes of metadata")

    metadata_wrapper = json.loads(metadata_bytes.decode("utf-8"))
    logger.debug(f"Parsed metadata wrapper: {metadata_wrapper}")
    logger.debug(f"Metadata wrapper type: {type(metadata_wrapper)}")

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

            # Receive compressed data
            logger.debug(f"Starting receive for: {path}")
            recv_work = node.irecv(tag=0)
            try:
                compressed_data = wait_with_timeout(recv_work, timeout=30)
            except TimeoutError as e:
                print(f"ERROR: {e}")
                node.close()
                sys.exit(1)
            logger.debug(
                f"Received {len(compressed_data)} compressed bytes for: {path}"
            )

            # Decompress using LZMA
            file_data = lzma.decompress(compressed_data)
            logger.debug(f"Decompressed to {len(file_data)} bytes for: {path}")

            # Create parent directories and write file
            logger.debug(f"Writing file: {path}")
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(file_data)
            logger.debug(f"Wrote {len(file_data)} bytes to: {path}")

            # Verify SHA256 hash to ensure file integrity after transfer
            received_hash = hashlib.sha256(file_data).hexdigest()
            expected_hash = item["sha256"]
            logger.debug(
                f"Hash verification for {path}: received={received_hash}, expected={expected_hash}"
            )
            if received_hash != expected_hash:
                logger.error(f"Hash mismatch for {path}! Deleting file.")
                path.unlink()  # Delete the corrupted file
                print(f"ERROR: Hash mismatch for {path}!")
                print(f"  Expected: {expected_hash}")
                print(f"  Received: {received_hash}")
                node.close()
                sys.exit(1)

            # Update progress bar
            pbar.update(len(compressed_data))
            pbar.set_postfix(file=str(path))

    print("All files received successfully!")
    node.close()


def sender_mode(
    token: str, files: List[str], verbose: bool = False, latency: int = 1000
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
        Latency parameter for send operations in milliseconds, by default 1000
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

                    # Read and compress file to get compressed size using LZMA
                    with open(file_path_obj, "rb") as f:
                        file_data = f.read()
                    # Compute SHA256 hash of the original file data to verify integrity after transfer
                    file_hash = hashlib.sha256(file_data).hexdigest()
                    compressed_data = lzma.compress(file_data)
                    compressed_size = len(compressed_data)

                    logger.debug(
                        f"File {file_path_obj}: {len(file_data)} bytes -> {compressed_size} bytes compressed, SHA256: {file_hash}"
                    )

                    meta_item = {
                        "path": str(relative_path),
                        "size": compressed_size,
                        "sha256": file_hash,
                    }
                    metadata.append(meta_item)
                    file_mapping.append((file_path_obj, meta_item))
                    total_size += compressed_size
        else:
            # Resolve file name to handle edge cases
            if path.name in (".", "..", ""):
                resolved_name = path.resolve().name
                actual_name = resolved_name if resolved_name else "root"
            else:
                actual_name = path.name

            # Read and compress file to get compressed size using LZMA
            with open(path, "rb") as f:
                file_data = f.read()
            # Compute SHA256 hash of the original file data to verify integrity after transfer
            file_hash = hashlib.sha256(file_data).hexdigest()
            compressed_data = lzma.compress(file_data)
            compressed_size = len(compressed_data)

            logger.debug(
                f"File {path}: {len(file_data)} bytes -> {compressed_size} bytes compressed, SHA256: {file_hash}"
            )

            meta_item = {
                "path": actual_name,
                "size": compressed_size,
                "sha256": file_hash,
            }
            metadata.append(meta_item)
            file_mapping.append((path, meta_item))
            total_size += compressed_size

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
    try:
        wait_with_timeout(send_work, timeout=30)
    except TimeoutError as e:
        print(f"ERROR: {e}")
        node.close()
        sys.exit(1)
    logger.debug("Metadata sent successfully")

    print(f"Metadata sent - ready to send files")

    # Send files with progress bar
    with tqdm(total=total_size, unit="B", unit_scale=True, desc="Sending") as pbar:
        for i, (original_path, meta) in enumerate(file_mapping):
            logger.debug(f"Sending item {i + 1}/{len(file_mapping)}: {original_path}")

            # Read file
            logger.debug(f"Reading file: {original_path}")
            with open(original_path, "rb") as f:
                file_data = f.read()
            logger.debug(f"Read {len(file_data)} bytes from: {original_path}")

            # Compress using LZMA
            compressed_data = lzma.compress(file_data)
            logger.debug(
                f"Compressed to {len(compressed_data)} bytes for: {original_path}"
            )

            # Send compressed data
            logger.debug(f"Sending {len(compressed_data)} bytes for: {original_path}")
            send_work = node.isend(msg=compressed_data, tag=0, latency=latency)
            try:
                wait_with_timeout(send_work, timeout=30)
            except TimeoutError as e:
                print(f"ERROR: {e}")
                node.close()
                sys.exit(1)
            logger.debug(f"Sent successfully: {original_path}")

            # Update progress bar
            pbar.update(len(compressed_data))
            pbar.set_postfix(file=meta["path"])

    print("All files sent successfully!")
    node.close()


if __name__ == "__main__":
    fire.Fire(main)
