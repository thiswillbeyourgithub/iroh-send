# IROH_SEND.PY PROJECT ROADMAP

## PROGRESS
- Overall completion: 60%
- TODOs remaining: 3
- Active issues: 0

## OBJECTIVES
- CREATE: Self-contained Python script using prime-iroh for file transfer
- IMPLEMENT: Token-based node derivation using SHA256 and mode suffix
- SUPPORT: File and directory transfer with compression
- PROVIDE: Progress tracking with tqdm on both sender/receiver
- ENABLE: uvx execution with embedded requirements

## COMPLETED
- CREATED: iroh_send.py basic structure with uvx requirements header. STATUS: done, includes fire.Fire integration
- IMPLEMENTED: Token parsing and seed derivation logic. STATUS: done, SHA256-based with mode suffix
- IMPLEMENTED: Basic node initialization and connection logic. STATUS: done, nodes connect using derived peer IDs
- ADDED: fire.Fire argument handling for sender/receiver modes. STATUS: done, mode determined by presence of file arguments
- IMPLEMENTED: File metadata exchange via JSON. STATUS: done, sender sends file info, receiver validates paths
- ADDED: File existence validation on receiver side. STATUS: done, crashes if any target files exist

## IN_PROGRESS
- IMPLEMENT: Basic file transfer functionality

## TODO
- P1: IMPLEMENT basic file transfer functionality (complexity: high)
- P1: ADD directory compression/decompression with tar (complexity: medium)
- P2: INTEGRATE tqdm progress bars for both modes (complexity: medium)

## DECISIONS
- CHOICE: Use tar+gzip for directory compression (standard, reliable)
- CHOICE: SHA256 for seed derivation (cryptographically sound)
- CHOICE: JSON for metadata exchange (simple, readable)

## LESSONS_LEARNED
(none yet)
