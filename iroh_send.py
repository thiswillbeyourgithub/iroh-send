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
    sender_seed = int.from_bytes(sender_hash[:8], byteorder='big')
    receiver_seed = int.from_bytes(receiver_hash[:8], byteorder='big')
    
    return sender_seed, receiver_seed


def get_peer_id_from_seed(seed: int) -> str:
    """Get the peer ID that would be generated from a given seed."""
    # Create temporary node to get its peer ID
    temp_node = Node.with_seed(1, seed=seed)
    peer_id = temp_node.peer_id()
    temp_node.close()
    return peer_id


def establish_connection(node: Node, peer_id: str, timeout: int = 30) -> bool:
    """Establish connection to peer and wait until ready."""
    print(f"Connecting to peer {peer_id[:16]}...")
    node.connect(peer_id, timeout)
    
    start_time = time.time()
    while not node.is_ready():
        if time.time() - start_time > timeout:
            return False
        time.sleep(0.1)
    
    print("Connected to peer!")
    return True


def main(*files):
    """Main entry point for iroh_send script."""
    # Initialize logging
    logging.basicConfig(level=logging.INFO)
    
    # Get token from environment
    token = os.getenv('IROH_SEND_TOKEN')
    if not token:
        print("ERROR: IROH_SEND_TOKEN environment variable not set")
        sys.exit(1)
    
    # Determine mode based on arguments
    if not files:
        print("Running in receiver mode...")
        receiver_mode(token)
    else:
        print(f"Running in sender mode with {len(files)} items...")
        sender_mode(token, list(files))


def receiver_mode(token: str):
    """Run in receiver mode - wait for files."""
    sender_seed, receiver_seed = derive_seeds(token)
    sender_peer_id = get_peer_id_from_seed(sender_seed)
    
    # Initialize receiver node
    node = Node.with_seed(1, seed=receiver_seed)
    print(f"Receiver node ID: {node.peer_id()}")
    
    # Connect to sender
    if not establish_connection(node, sender_peer_id):
        print("ERROR: Failed to connect to sender")
        node.close()
        sys.exit(1)
    
    print("Receiver ready - waiting for metadata...")
    
    # Receive metadata
    recv_work = node.irecv(0)
    metadata_bytes = recv_work.wait()
    metadata = json.loads(metadata_bytes.decode('utf-8'))
    
    print(f"Received metadata for {len(metadata)} items")
    
    # Check if any files already exist
    for item in metadata:
        path = Path(item['path'])
        if path.exists():
            print(f"ERROR: File/directory already exists: {path}")
            node.close()
            sys.exit(1)
    
    print("All paths clear - ready to receive files")
    # TODO: Implement actual file receiving
    
    node.close()


def sender_mode(token: str, files: List[str]):
    """Run in sender mode - send files."""
    sender_seed, receiver_seed = derive_seeds(token)
    receiver_peer_id = get_peer_id_from_seed(receiver_seed)
    
    # Initialize sender node
    node = Node.with_seed(1, seed=sender_seed)
    print(f"Sender node ID: {node.peer_id()}")
    
    # Connect to receiver
    if not establish_connection(node, receiver_peer_id):
        print("ERROR: Failed to connect to receiver")
        node.close()
        sys.exit(1)
    
    print(f"Sender ready - preparing metadata for {len(files)} items...")
    
    # Prepare metadata
    metadata = []
    for file_path in files:
        path = Path(file_path)
        if not path.exists():
            print(f"ERROR: File/directory does not exist: {path}")
            node.close()
            sys.exit(1)
        
        if path.is_dir():
            # For directories, we'll send as compressed tar
            metadata.append({
                'path': str(path),
                'is_directory': True,
                'size': 0  # Will be calculated during compression
            })
        else:
            # For files, get actual size
            metadata.append({
                'path': str(path),
                'is_directory': False,
                'size': path.stat().st_size
            })
    
    # Send metadata
    metadata_json = json.dumps(metadata)
    metadata_bytes = metadata_json.encode('utf-8')
    send_work = node.isend(metadata_bytes, 0, 1000)
    send_work.wait()
    
    print(f"Metadata sent - ready to send files")
    # TODO: Implement actual file sending
    
    node.close()


if __name__ == "__main__":
    fire.Fire(main)
