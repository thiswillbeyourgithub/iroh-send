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
from typing import List, Dict, Any

import fire
from tqdm import tqdm
from prime_iroh import Node


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
    print("Receiver mode not yet implemented")
    pass


def sender_mode(token: str, files: List[str]):
    """Run in sender mode - send files."""
    print("Sender mode not yet implemented")
    pass


if __name__ == "__main__":
    fire.Fire(main)
