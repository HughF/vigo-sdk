# Vigo TCP Command Server — Integration Guide

## Overview

The Vigo winch controller exposes a TCP command server that allows external software to query
system state, change operating parameters, start or abort casts, and receive unsolicited status
events in real time. The interface is plain ASCII text over a persistent TCP connection, suitable
for integration from any language with a socket library.

## Prerequisites

The TCP interface provides full remote control of the winch, but **one operation cannot be
performed over TCP and must be done via the web interface before casting is possible:**

**Setting the data-transfer point.** This is the cable position at which the winch stops during
recovery to allow the profiler to transfer its data. It is set by jogging the winch to the correct
position and pressing **Set transfer position** in the web UI (or by running the auto-set routine).
Until this is done, `$QRYSAFEFLAG` returns `false` and any `$RUNCAST` command is rejected
with `ERR,NOT_SAFE`.

The transfer point only needs to be set once per deployment. It is retained across casts until the
system is power-cycled or the point is explicitly reset. After a power cycle, re-establish the
transfer point via the web UI before issuing `$RUNCAST` commands over TCP.

## Connection

| Parameter | Value |
|-----------|-------|
| Port      | **8092** |
| Encoding  | ASCII |
| Line ending (commands) | `\n` (LF) |
| Line ending (responses/events) | `\r\n` (CRLF) |

Immediately after the TCP connection is accepted the server sends a greeting line:

```
VIGO 2026.04.29\r\n
```

The version string will reflect the currently installed server version. You can use this as a
connectivity check and to confirm firmware compatibility.

Multiple clients may connect simultaneously. All clients receive the same unsolicited event
broadcasts.

## Message Format

### Commands (client → server)

```
$VERB\n
$VERB,arg1,arg2\n
```

- The verb and any arguments are separated by commas.
- The verb is case-insensitive; the server normalises it to upper-case internally.
- String arguments for `$SET…` commands are also case-insensitive.
- Terminate every command with a single `\n`. A trailing `\r` is harmless.

### Responses (server → client)

Every command generates exactly one response, sent only to the client that issued the command:

```
$RSP:VALUE\r\n
```

For successful queries, `VALUE` is the requested datum. For commands, `VALUE` is `OK` on
success, or `ERR,REASON` on failure (see [Error Codes](#error-codes)).

### Events (server → all clients)

Unsolicited events are broadcast to every connected client when system state changes:

```
$EVT:EVENTNAME\r\n
$EVT:EVENTNAME,VALUE\r\n
```

Events arrive asynchronously at any time. Your receive loop must be able to handle both
`$RSP:` and `$EVT:` lines, and should not assume a response will arrive before the next event.

---

## Query Commands

All query commands take no arguments and return the current value of the named variable.

| Command | Returns | Description |
|---------|---------|-------------|
| `$QRYCASTTYPE` | `UNDERWAY` \| `DOWNHOLE` | Current cast mode |
| `$QRYSAFEFLAG` | `true` \| `false` | Whether the transfer point has been set and it is safe to run a cast |
| `$QRYPROFILER` | profiler ID (see below) | Currently selected profiler type |
| `$QRYSTOPMODE` | `TRANSFERPOINT` \| `LIMITSWITCH` | Recovery stop mode |
| `$QRYCYCLEFLAG` | `done` \| `out` \| `retract` | Current stage of the cast cycle |
| `$QRYSPEED` | integer (RPM) | Recovery speed setpoint |
| `$QRYTORQUE` | integer (%) | Freefall back-torque setpoint |
| `$QRYMETERSOUT` | float (m) | Metres of cable currently deployed |
| `$QRYDEPTH` | float (m) | Depth reached on the most recent cast (`0` if no cast yet) |
| `$QRYPOWER` | float (W) | Current power draw from the AC power meter |
| `$QRYVOLTAGE` | float (V) | Current supply voltage from the AC power meter |
| `$QRYWATERDEPTH` | float (m) | Water depth from the connected NMEA depth sounder |
| `$QRYCYCLES` | integer | Total number of casts performed this session |
| `$QRYDROPRATE` | float (m/s) | Effective drop rate for the current profiler |
| `$CABLEOUT` | float (m) | Metres of cable currently deployed (alias of `$QRYMETERSOUT`) |

### `$STATUS` — full machine state as JSON

Returns the complete current state of the system as a single-line JSON object. Provided as a
convenience so a client can read everything in one round-trip instead of issuing every `$QRY…`
command individually.

```
→ $STATUS\n
← $RSP:{"castType":"UNDERWAY","safeToCast":true,"profiler":"SWIFTSVP","stopMode":"TRANSFERPOINT","cycleFlag":"done","speedRpm":1000,"torquePct":2,"metersOut":12.7,"lastDepth":34.5,"powerW":150,"voltageV":230,"waterDepth":40,"cycles":3,"dropRate":1.1,"driveMode":"POSITION","driveStatus":"ENABLED","brake":"DISABLED","levelWind":"ENABLED","stepSeconds":1,"payStepBusy":false,"version":"2026.09.04"}\r\n
```

The JSON is always emitted on a single line (no embedded newlines), so the standard
split-on-`\n` receive loop parses it as one message. Field meanings follow the individual
`$QRY…` commands above; `stepSeconds` is the current pay-step duration and `payStepBusy` is
`true` while a `$PAYIN`/`$PAYOUT` step is in progress.

**Example**

```
→ $QRYMETERSOUT\n
← $RSP:12.3\r\n
```

---

## Set / Action Commands

### `$SETPROFILER,<type>`

Select the profiler installed on the winch. This resets the abort-time calculation to use the
default drop rate for that instrument.

| Argument | Profiler |
|----------|----------|
| `SWIFTSVP` | Valeport SWiFT SVP (default) |
| `RAPIDSVP` | Valeport RapidSV |
| `SWIFTCTD` | Valeport SWiFT CTD |
| `RAPIDCTD` | Valeport RapidCTD |
| `AML3LGR`  | AML 3-LGR (plastic) |
| `AML6LGR`  | AML 6-LGR (plastic + 3.9 kg nose weight) |

```
→ $SETPROFILER,RAPIDSVP\n
← $RSP:OK\r\n
```

### `$SETCASTTYPE,<type>`

Switch between underway (free-fall, time-limited) and downhole (powered payout, encoder-stopped)
cast modes.

| Argument | Description |
|----------|-------------|
| `UNDERWAY` | Free-fall cast; freefall duration controls depth |
| `DOWNHOLE` | Powered payout to a precise encoder position |

```
→ $SETCASTTYPE,UNDERWAY\n
← $RSP:OK\r\n
```

### `$SETSTOPMODE,<mode>`

Select how recovery is terminated.

| Argument | Description |
|----------|-------------|
| `TRANSFERPOINT` | Stop at the data-transfer position (default) |
| `LIMITSWITCH`   | Wind all the way in until the proximity switch closes |

```
→ $SETSTOPMODE,TRANSFERPOINT\n
← $RSP:OK\r\n
```

### `$SETSPEED,<rpm>`

Set the recovery (wind-in) speed. Valid range: **600 – 1200 RPM**.

```
→ $SETSPEED,1000\n
← $RSP:OK\r\n
```

On out-of-range: `$RSP:ERR,RANGE_600_1200\r\n`

### `$SETTORQUE,<percent>`

Set the back-torque applied during freefall to control line tension. Valid range: **0 – 300 %**
of the drive's rated torque.

```
→ $SETTORQUE,2\n
← $RSP:OK\r\n
```

On out-of-range: `$RSP:ERR,RANGE_0_300\r\n`

### `$SETPOWERBUDGET,<watts>`

Set the power ceiling. If power exceeds this level during recovery the Vigo automatically
reduces winch speed and sounds an audible alert. Valid range: **250 – 1000 W**.

```
→ $SETPOWERBUDGET,800\n
← $RSP:OK\r\n
```

On out-of-range: `$RSP:ERR,RANGE_250_1000\r\n`

### `$RUNCAST,<depth_m>`

Start a cast to the specified depth. Valid range: **0.1 – 500 m** (float accepted).

The server will reject this command if the data-transfer point has not been set
(`$QRYSAFEFLAG` returns `false`).

```
→ $RUNCAST,50\n
← $RSP:OK\r\n
```

Possible errors:

| Error | Meaning |
|-------|---------|
| `ERR,INVALID_DEPTH` | Depth is not a positive number or exceeds 500 m |
| `ERR,NOT_SAFE` | Transfer point has not been set; casting is locked out |

### `$ABORT`

Abort the current cast immediately. Safe to send at any stage; always returns `OK`.

```
→ $ABORT\n
← $RSP:OK\r\n
```

### `$RECOVER`

Trigger an emergency recovery. Sends an immediate stop-and-wind command to the drive
regardless of current cycle state. Always returns `OK`.

```
→ $RECOVER\n
← $RSP:OK\r\n
```

### `$RECOVERALL`

Wind the cable fully in until the proximity switch closes (only acts when `cycleFlag` is
`done`). Always returns `OK`.

```
→ $RECOVERALL\n
← $RSP:OK\r\n
```

### Manual pay-in / pay-out

These commands nudge the winch a fixed amount in either direction, then stop automatically.
They are intended for recovering the last few metres of cable manually — for example if the
limit switch is unreliable — by issuing repeated short moves. Each move runs for the pay-step
duration set by `$STEP` (default **1 s**) and then stops on its own.

All three require the system to be idle (`cycleFlag` is `done`); they will not interrupt a
running cast.

#### `$STEP[,<seconds>]`

Set the duration of a single `$PAYIN`/`$PAYOUT` move, in seconds (float). Valid range
**0.05 – 10 s**. Returns the accepted value. With no argument, returns the current value
without changing it.

```
→ $STEP,2\n
← $RSP:2\r\n

→ $STEP\n
← $RSP:2\r\n
```

On out-of-range or non-numeric argument: `$RSP:ERR,RANGE_0.05_10\r\n`

#### `$PAYIN`

Wind in for one step, then stop. Returns `OK` if the move started, or an error otherwise.
Re-checks the proximity switch first (as a manual jog-in does).

```
→ $PAYIN\n
← $RSP:OK\r\n
```

| Error | Meaning |
|-------|---------|
| `ERR,BUSY` | A pay step is already running, or the system is not idle (`cycleFlag` ≠ `done`) |
| `ERR,PROX_TRIPPED` | Proximity switch is tripped; move refused (also broadcasts `PROXTRIPPED,WARNING1`) |
| `ERR,IO_ERROR` | Could not read the proximity switch |

#### `$PAYOUT`

Wind out for one step, then stop. Same behaviour as `$PAYIN` in the opposite direction; no
proximity-switch check (paying out moves away from the switch).

```
→ $PAYOUT\n
← $RSP:OK\r\n
```

| Error | Meaning |
|-------|---------|
| `ERR,BUSY` | A pay step is already running, or the system is not idle (`cycleFlag` ≠ `done`) |

#### `$STOP`

Stop any manual motion immediately and cancel a pay-step move that is in progress. Always
returns `OK`.

Note: `$STOP` stops **manual jog / pay motion** (equivalent to releasing a jog button); it does
**not** abort a running cast. To abort a cast, use [`$ABORT`](#abort).

```
→ $STOP\n
← $RSP:OK\r\n
```

---

## Unsolicited Events

These messages are broadcast to all connected clients and arrive at any time, including while
you are waiting for a command response.

| Event | Value | Description |
|-------|-------|-------------|
| `$EVT:CYCLEFLAG,done` | — | The cast cycle has ended; the system is idle |
| `$EVT:CYCLEFLAG,out` | — | Freefall phase has started |
| `$EVT:CYCLEFLAG,retract` | — | Recovery (wind-in) phase has started |
| `$EVT:CASTCOMPLETE` | — | The profiler has been recovered to the stop position |
| `$EVT:CASTFAIL` | — | Cast aborted automatically (no line movement was detected during freefall) |
| `$EVT:PROXTRIPPED,WARNING1` | — | Proximity switch tripped during a jog or manual move; motion stopped |
| `$EVT:PROXTRIPPED,WARNING2` | — | Proximity switch tripped during recovery; profiler may need manual recovery |
| `$EVT:PROXTRIPPED,WARNING3` | — | Proximity switch tripped during a Bluetooth-retry jog |
| `$EVT:TRANSFERSET,MANUAL` | — | Data-transfer position set manually via the web panel |
| `$EVT:TRANSFERSET,AUTOMATIC` | — | Data-transfer position set by the auto-set routine |
| `$EVT:TRANSFERSET,RESET` | — | Data-transfer position reset after a failed Bluetooth transfer |
| `$EVT:ESTOP,HIGH` | — | E-stop button pressed |
| `$EVT:ESTOP,LOW` | — | E-stop button released |
| `$EVT:DRIVEFAULT,LOW` | — | Servo drive fault detected; drive will restart automatically after 7.5 s |
| `$EVT:DRIVEFAULT,HIGH` | — | Servo drive fault cleared |

A typical automated cast sequence produces these events in order:

```
$EVT:CYCLEFLAG,out\r\n
$EVT:CYCLEFLAG,retract\r\n
$EVT:CASTCOMPLETE\r\n
$EVT:CYCLEFLAG,done\r\n
```

---

## Error Codes

| Code | Meaning |
|------|---------|
| `ERR,UNKNOWN_CMD` | The verb was not recognised |
| `ERR,ARG_MISSING` | A required argument was not supplied |
| `ERR,INVALID` | The argument value is not one of the accepted options |
| `ERR,RANGE_X_Y` | The numeric argument is outside the allowed range (X–Y) |
| `ERR,INVALID_DEPTH` | Depth argument for `$RUNCAST` is not a valid positive number ≤ 500 m |
| `ERR,NOT_SAFE` | `$RUNCAST` rejected because the transfer point has not been set |
| `ERR,UNKNOWN_PROFILER` | `$SETPROFILER` argument was not a recognised profiler ID |
| `ERR,RANGE_0.05_10` | `$STEP` duration is outside the allowed range (0.05–10 s) or not a number |
| `ERR,BUSY` | `$PAYIN`/`$PAYOUT` rejected: a pay step is already running or the system is not idle |
| `ERR,PROX_TRIPPED` | `$PAYIN` rejected because the proximity switch is tripped |
| `ERR,IO_ERROR` | `$PAYIN` could not read the proximity switch |

---

## Implementation Notes

**Receive buffering** — TCP does not guarantee message boundaries. Buffer incoming bytes and
split on `\n` before parsing. A simple state machine that appends bytes to a string until it
sees `\n` is sufficient.

**Event interleaving** — Do not assume that a `$RSP:` line will arrive before the next `$EVT:`
line. Process each line as it arrives and route it by prefix.

**Reconnection** — The server does not queue events for absent clients. If your client
disconnects, events that occurred while offline are lost. Re-query state with the `$QRY…`
commands after reconnecting.

**Line endings** — Send commands with `\n` only. The server is tolerant of a leading `\r` but
do not rely on this. Responses always use `\r\n`.

---

## Python Quick-Start

```python
import socket
import threading

HOST = '192.168.1.100'  # Vigo IP address
PORT = 8092

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((HOST, PORT))
sock.setblocking(True)

buf = ''

def send(cmd):
    sock.sendall((cmd + '\n').encode('ascii'))

def receive_lines():
    global buf
    while True:
        chunk = sock.recv(4096).decode('ascii')
        if not chunk:
            break
        buf += chunk
        while '\n' in buf:
            line, buf = buf.split('\n', 1)
            line = line.strip()
            if line.startswith('$EVT:'):
                handle_event(line[5:])
            elif line.startswith('$RSP:'):
                handle_response(line[5:])
            elif line.startswith('VIGO '):
                print('Connected to', line)

def handle_event(payload):
    parts = payload.split(',', 1)
    name  = parts[0]
    value = parts[1] if len(parts) > 1 else None
    print(f'Event: {name}  value={value}')
    if name == 'CASTCOMPLETE':
        print('Cast finished!')

def handle_response(payload):
    print(f'Response: {payload}')

t = threading.Thread(target=receive_lines, daemon=True)
t.start()

# Query current state, then run a 50 m cast
send('$QRYSAFEFLAG')
send('$QRYCYCLEFLAG')
send('$RUNCAST,50')

input('Press Enter to abort and exit\n')
send('$ABORT')
sock.close()
```
