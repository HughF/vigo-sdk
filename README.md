# Vigo SDK

Integration tools and documentation for the [Vigo profiling winch](https://vigowinch.com) by [C-MAX Ltd](http://www.cmaxsonar.com).

## Contents

### [`docs/tcp-command-server.md`](docs/tcp-command-server.md)

Full reference for the Vigo TCP command server — connection details, message format, all query and action commands, response codes, and unsolicited event types. Start here if you are integrating Vigo into an automated survey workflow or USV mission system.

**Quick facts:**
- Port **8092**, plain ASCII text, persistent TCP connection
- Works from any language with a socket library (Python, MATLAB, C, LabVIEW, …)
- Supports multiple simultaneous clients; all receive the same event broadcasts

### [`tools/vigo_tcp_test.py`](tools/vigo_tcp_test.py)

Interactive Python console for exercising the TCP interface. Connects to a Vigo on the network and presents a menu covering every query, set, and action command, plus a live event monitor and a raw command prompt.

**Requirements:** Python 3.6+, no third-party packages.

```
python3 tools/vigo_tcp_test.py 192.168.1.100
python3 tools/vigo_tcp_test.py 192.168.1.100 --port 8092
```

## Minimal example

Query the current system state in Python:

```python
import socket

HOST = '192.168.1.100'
PORT = 8092

with socket.create_connection((HOST, PORT)) as s:
    f = s.makefile('r')
    print('Greeting:', f.readline().strip())   # VIGO 2026.xx.xx

    s.sendall(b'$QRYMETERSOUT\n')
    print('Metres out:', f.readline().strip())  # $RSP:12.40

    s.sendall(b'$QRYDEPTH\n')
    print('Last depth:', f.readline().strip())  # $RSP:47.2
```

> **Note:** set the data-transfer point via the web UI or physical button before issuing
> `$RUNCAST` commands — see the integration guide for details.

## Licence

© C-MAX Ltd. See [vigowinch.com](https://vigowinch.com) for product information.
