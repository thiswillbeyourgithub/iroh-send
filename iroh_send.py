#!/usr/bin/env python3
"""
Self-contained file transfer script using prime-iroh.

Requirements for uvx:
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "prime-iroh",
#     "fire",
#     "tqdm",
# ]
# ///

Usage:
    # Receiver mode (no files specified)
    uvx iroh_send.py

    # Sender mode (files/directories specified)
    uvx iroh_send.py file1.txt dir1/ file2.py
"""

import os
import sys
import json
import time
import hashlib
import tarfile
import tempfile
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple

import fire
from tqdm import tqdm
from prime_iroh import Node


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
    temp_node = Node.with_seed(1, seed=seed)
    node_id = temp_node.node_id()
    temp_node.close()
    return node_id


def establish_connection(node: Node, node_id: str, timeout: int = 30) -> bool:
    """Establish connection to peer and wait until ready."""
    print(f"Connecting to peer {node_id[:16]}...")
    node.connect(node_id, timeout)

    start_time = time.time()
    while not node.is_ready():
        if time.time() - start_time > timeout:
            return False
        time.sleep(0.1)

    print("Connected to peer!")
    return True


def main(*files, verbose: bool = False):
    """Main entry point for iroh_send script.

    Parameters
    ----------
    *files : str
        Files or directories to send (sender mode). If empty, runs in receiver mode.
    verbose : bool, optional
        Enable verbose debug logging, by default False
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
        sender_mode(token, list(files), verbose)


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
    if not establish_connection(node, sender_node_id):
        print("ERROR: Failed to connect to sender")
        node.close()
        sys.exit(1)

    print("Receiver ready - waiting for metadata...")

    # Receive metadata
    logger.debug("Starting metadata receive...")
    recv_work = node.irecv(0)
    metadata_bytes = recv_work.wait()
    logger.debug(f"Received {len(metadata_bytes)} bytes of metadata")

    metadata = json.loads(metadata_bytes.decode("utf-8"))
    logger.debug(f"Parsed metadata: {metadata}")

    print(f"Received metadata for {len(metadata)} items")

    # Check if any files already exist
    logger.debug("Checking if any destination paths already exist...")
    for item in metadata:
        path = Path(item["path"])
        logger.debug(f"Checking path: {path}")
        if path.exists():
            print(f"ERROR: File/directory already exists: {path}")
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
            is_directory = item["is_directory"]
            logger.debug(
                f"Receiving item {i + 1}/{len(metadata)}: {path} (directory={is_directory})"
            )

            # Check again that path doesn't exist (safety check)
            if path.exists():
                print(f"ERROR: File/directory created during transfer: {path}")
                node.close()
                sys.exit(1)

            # Receive file data
            logger.debug(f"Starting receive for: {path}")
            recv_work = node.irecv(0)
            file_data = recv_work.wait()
            logger.debug(f"Received {len(file_data)} bytes for: {path}")

            if is_directory:
                # Extract tar archive
                logger.debug(f"Extracting directory archive: {path}")
                with tempfile.NamedTemporaryFile() as temp_file:
                    temp_file.write(file_data)
                    temp_file.flush()

                    with tarfile.open(temp_file.name, "r:gz") as tar:
                        members = tar.getmembers()
                        logger.debug(f"Archive contains {len(members)} members")
                        tar.extractall(path=path.parent)
                logger.debug(f"Extracted directory: {path}")
            else:
                # Write regular file
                logger.debug(f"Writing file: {path}")
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "wb") as f:
                    f.write(file_data)
                logger.debug(f"Wrote {len(file_data)} bytes to: {path}")

            # Update progress bar
            pbar.update(len(file_data))
            pbar.set_postfix(file=str(path))

    print("All files received successfully!")
    node.close()


def sender_mode(token: str, files: List[str], verbose: bool = False):
    """Run in sender mode - send files.

    Parameters
    ----------
    token : str
        Connection token for deriving seeds
    files : List[str]
        List of file/directory paths to send
    verbose : bool, optional
        Enable verbose debug logging, by default False
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
    node = Node.with_seed(1, seed=sender_seed)
    sender_node_id = node.node_id()
    print(f"Sender node ID: {sender_node_id}")
    logger.debug(f"Full sender node ID: {sender_node_id}")

    # Connect to receiver
    logger.debug(f"Attempting to connect to receiver: {receiver_node_id}")
    if not establish_connection(node, receiver_node_id):
        print("ERROR: Failed to connect to receiver")
        node.close()
        sys.exit(1)

    print(f"Sender ready - preparing metadata for {len(files)} items...")

    # Prepare metadata and calculate sizes
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
            # For directories, calculate compressed size
            logger.debug(f"Creating tar archive for directory: {path}")
            with tempfile.NamedTemporaryFile() as temp_file:
                with tarfile.open(temp_file.name, "w:gz") as tar:
                    tar.add(path, arcname=path.name)

                temp_file.seek(0, 2)  # Seek to end
                compressed_size = temp_file.tell()

            logger.debug(f"Compressed size for {path}: {compressed_size} bytes")
            metadata.append(
                {"path": str(path), "is_directory": True, "size": compressed_size}
            )
            total_size += compressed_size
        else:
            # For files, get actual size
            file_size = path.stat().st_size
            logger.debug(f"File size for {path}: {file_size} bytes")
            metadata.append(
                {"path": str(path), "is_directory": False, "size": file_size}
            )
            total_size += file_size

    # Send metadata
    logger.debug(
        f"Total size to send: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)"
    )
    metadata_json = json.dumps(metadata)
    metadata_bytes = metadata_json.encode("utf-8")
    logger.debug(f"Metadata JSON ({len(metadata_bytes)} bytes): {metadata_json}")

    logger.debug("Sending metadata...")
    send_work = node.isend(metadata_bytes, 0, 1000)
    send_work.wait()
    logger.debug("Metadata sent successfully")

    print(f"Metadata sent - ready to send files")

    # Send files with progress bar
    with tqdm(total=total_size, unit="B", unit_scale=True, desc="Sending") as pbar:
        for i, (file_path, meta) in enumerate(zip(files, metadata)):
            path = Path(file_path)
            is_directory = meta["is_directory"]
            logger.debug(
                f"Sending item {i + 1}/{len(metadata)}: {path} (directory={is_directory})"
            )

            if is_directory:
                # Create tar archive in memory
                logger.debug(f"Creating tar archive for: {path}")
                with tempfile.NamedTemporaryFile() as temp_file:
                    with tarfile.open(temp_file.name, "w:gz") as tar:
                        tar.add(path, arcname=path.name)

                    temp_file.seek(0)
                    file_data = temp_file.read()
                logger.debug(f"Created archive of {len(file_data)} bytes for: {path}")
            else:
                # Read regular file
                logger.debug(f"Reading file: {path}")
                with open(path, "rb") as f:
                    file_data = f.read()
                logger.debug(f"Read {len(file_data)} bytes from: {path}")

            # Send file data
            logger.debug(f"Sending {len(file_data)} bytes for: {path}")
            send_work = node.isend(file_data, 0, 1000)
            send_work.wait()
            logger.debug(f"Sent successfully: {path}")

            # Update progress bar
            pbar.update(len(file_data))
            pbar.set_postfix(file=str(path))

    print("All files sent successfully!")
    node.close()


if __name__ == "__main__":
    fire.Fire(main)
