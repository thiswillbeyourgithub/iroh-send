Here is an example using prime-iroh to show how to exchange packets between two nodes:

```python
#!/usr/bin/env python3
"""
This example demonstrates bidirectional communication between two nodes.
For simplicity, we initialize with known seeds, so that the nodes can
automatically connect to each other with known connection strings.

Run the receiver:
    python bidirectional.py rank0

Run the sender:
    python bidirectional.py rank1
"""

import sys
import time
import logging
from prime_iroh import Node

def main():
    # Initialize logging
    logging.basicConfig(level=logging.INFO)

    # Get command line arguments
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} [rank0|rank1]")
        sys.exit(1)

    num_streams = 1
    num_messages = 5
    mode = sys.argv[1]

    if mode == "rank0":
        # Initialize variables for rank 0 (define rank 1's connection string)
        print("Running rank 0")
        rank = 0
        peer_id = "ff87a0b0a3c7c0ce827e9cada5ff79e75a44a0633bfcb5b50f99307ddb26b337"
    elif mode == "rank1":
        # Initialize variables for rank 1 (define rank 0's connection string)
        print("Running rank 1")
        rank = 1
        peer_id = "ee1aa49a4459dfe813a3cf6eb882041230c7b2558469de81f87c9bf23bf10a03"
    else:
        print("Invalid mode. Use 'rank0' or 'rank1'")
        sys.exit(1)

    # Initialize node with rank seed
    node = Node.with_seed(num_streams, seed=rank)

    # Wait until connection is established
    print("Waiting for connection...")
    node.connect(peer_id, 10)
    while not node.is_ready():
        time.sleep(0.1)
    print("Connected to peer!")

    # Send and receive messages
    for i in range(num_messages):
        # Send message
        send_msg = f"Hello from rank {rank}"
        bytes_data = send_msg.encode('utf-8')
        send_work = node.isend(bytes_data, 0, 1000)

        # Receive message
        recv_work = node.irecv(0)
        bytes_data = recv_work.wait()
        recv_msg = bytes_data.decode('utf-8')
        print(f"Received message {i + 1}: {recv_msg}")

        # Wait for send work to complete
        send_work.wait()

    # Clean up
    node.close()

if __name__ == "__main__":
    main()
```

I want you to write a self contained python script using prime-iroh called iroh_send.py.
- It loads a IROH_SEND_TOKEN env variable.
- it uses fire.Fire to handle arguments.
- It can be a file, or several files, or directories.
- If the script receives no files as argument, it is in receiver mode, otherwise in sender mode.
    - That "mode" value is added at the end of the token, which is then sent through sha256 to derive a seed used to create both nodes.
        - Hence, with a single script and token, we derive both the node_id of the sender and the receiver.
- The one in sender mode, sends the files to the receiver which writes the files.
- The first exchange sends a json.dumps(string) that describes the length in bytes of each of the files to send, their relative path to the sender, wether they are a directory or not. All files are described in that exchange, and then only files are exchanged.
    - The receiver has to check that no files already exist at those locations, if they do, it should crash. It also has to check before starting to write each file, just in case some new file was created in the meantime or something.
- If sending a directory, we tar + compress them on the fly and send it to the receiver, who, because it knows that it has to be decompressed, will reverse the process.
    - This way if we send a large file we don't have to store the compression. Especially if for example sending a directory of videos. If you have a better idea than tar + compress to do that I'm fine with it.
- Use tqdm on both ends to let the user know how far along we are in the process of sending the data.
- make the requirements part of the fontmatter at the top so that it can be called with "uvx iroh_send.py"
