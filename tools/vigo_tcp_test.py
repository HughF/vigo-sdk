#!/usr/bin/env python3
"""
vigo_tcp_test.py — interactive console test application for the Vigo TCP command server

Usage:
    python3 vigo_tcp_test.py [host] [--port PORT]

Examples:
    python3 vigo_tcp_test.py 192.168.1.100
    python3 vigo_tcp_test.py 192.168.1.100 --port 8092
"""

import argparse
import queue
import socket
import sys
import threading
import time
from datetime import datetime


# ── ANSI colours ──────────────────────────────────────────────────────────────

class C:
    RESET  = '\033[0m'
    BOLD   = '\033[1m'
    DIM    = '\033[2m'
    RED    = '\033[91m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    CYAN   = '\033[96m'
    WHITE  = '\033[97m'

# Enable VT sequences on Windows; fall back to plain text if unavailable
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7)
    except Exception:
        for _a in vars(C):
            if not _a.startswith('_'):
                setattr(C, _a, '')


DEFAULT_HOST    = '192.168.1.100'
DEFAULT_PORT    = 8092
RESPONSE_TIMEOUT = 5.0  # seconds to wait for $RSP before declaring a timeout


# ── Client ────────────────────────────────────────────────────────────────────

class VigoClient:
    """Thin TCP client that splits the receive stream into $RSP and $EVT lines."""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self._buf = ''
        self._rsp_queue = queue.Queue()
        self._stop = threading.Event()

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect((self.host, self.port))
        self.sock.setblocking(True)
        self._stop.clear()
        t = threading.Thread(target=self._rx_loop, daemon=True, name='vigo-rx')
        t.start()

    def disconnect(self):
        self._stop.set()
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()
            self.sock = None

    def send(self, cmd):
        """Send a command string without waiting for a response."""
        self.sock.sendall((cmd + '\n').encode('ascii'))

    def query(self, cmd):
        """Send a command and block until the matching $RSP arrives (or timeout)."""
        self.send(cmd)
        try:
            return self._rsp_queue.get(timeout=RESPONSE_TIMEOUT)
        except queue.Empty:
            return None

    # ── internal ──────────────────────────────────────────────────────────────

    def _rx_loop(self):
        while not self._stop.is_set():
            try:
                chunk = self.sock.recv(4096)
            except (OSError, socket.timeout):
                if not self._stop.is_set():
                    _print_error('Connection lost')
                break
            if not chunk:
                if not self._stop.is_set():
                    _print_error('Server closed connection')
                break
            self._buf += chunk.decode('ascii', errors='replace')
            while '\n' in self._buf:
                line, self._buf = self._buf.split('\n', 1)
                line = line.strip()
                if line:
                    self._dispatch(line)

    def _dispatch(self, line):
        ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        if line.startswith('$RSP:'):
            payload = line[5:]
            _print_response(ts, payload)
            self._rsp_queue.put(payload)
        elif line.startswith('$EVT:'):
            _print_event(ts, line[5:])
        elif line.startswith('VIGO '):
            _print_info(f'Server greeting: {line}')
        else:
            _print_info(f'Unrecognised: {line}')


# ── Output helpers ────────────────────────────────────────────────────────────

def _print_response(ts, payload):
    colour = C.RED if payload.startswith('ERR') else C.GREEN
    print(f'\r{C.DIM}[{ts}]{C.RESET} {colour}{C.BOLD}RSP{C.RESET} '
          f'{colour}{payload}{C.RESET}')

def _print_event(ts, payload):
    print(f'\r{C.DIM}[{ts}]{C.RESET} {C.YELLOW}{C.BOLD}EVT{C.RESET} '
          f'{C.YELLOW}{payload}{C.RESET}')

def _print_info(msg):
    print(f'\r{C.CYAN}     {msg}{C.RESET}')

def _print_error(msg):
    print(f'\r{C.RED}  ✗  {msg}{C.RESET}')

def _header(title):
    bar = '─' * max(0, 52 - len(title))
    print(f'\n{C.BOLD}{C.WHITE}── {title} {bar}{C.RESET}')

def _result(label, value):
    if value is None:
        print(f'  {C.DIM}{label:<28}{C.RESET} {C.RED}(timeout — no response){C.RESET}')
    elif value.startswith('ERR'):
        print(f'  {C.DIM}{label:<28}{C.RESET} {C.RED}{value}{C.RESET}')
    else:
        print(f'  {C.DIM}{label:<28}{C.RESET} {C.WHITE}{value}{C.RESET}')

def _ok(msg):
    print(f'  {C.GREEN}✓{C.RESET}  {msg}')

def _fail(msg):
    print(f'  {C.RED}✗{C.RESET}  {msg}')

def _warn(msg):
    print(f'  {C.YELLOW}!{C.RESET}  {msg}')


# ── Query test ────────────────────────────────────────────────────────────────

ALL_QUERIES = [
    ('$QRYCASTTYPE',   'Cast type'),
    ('$QRYSAFEFLAG',   'Safe to cast'),
    ('$QRYPROFILER',   'Profiler'),
    ('$QRYSTOPMODE',   'Stop mode'),
    ('$QRYCYCLEFLAG',  'Cycle flag'),
    ('$QRYSPEED',      'Recovery speed (RPM)'),
    ('$QRYTORQUE',     'Freefall torque (%)'),
    ('$QRYMETERSOUT',  'Metres out'),
    ('$QRYDEPTH',      'Last cast depth (m)'),
    ('$QRYPOWER',      'AC power (W)'),
    ('$QRYVOLTAGE',    'Supply voltage (V)'),
    ('$QRYWATERDEPTH', 'Water depth (m)'),
    ('$QRYCYCLES',     'Cast count'),
    ('$QRYDROPRATE',   'Drop rate (m/s)'),
]

def test_all_queries(client):
    _header('Query all state variables')
    for cmd, label in ALL_QUERIES:
        r = client.query(cmd)
        _result(label, r)
        time.sleep(0.05)


# ── Set / action tests ────────────────────────────────────────────────────────

def test_set_profiler(client):
    _header('Set profiler')
    profilers = ['SWIFTSVP', 'RAPIDSVP', 'SWIFTCTD', 'RAPIDCTD', 'AML3LGR', 'AML6LGR']
    for i, p in enumerate(profilers, 1):
        print(f'  {C.CYAN}{i}.{C.RESET} {p}')
    print(f'  {C.DIM}0. Cancel{C.RESET}')
    choice = input('  Choose: ').strip()
    if choice == '0' or choice == '':
        return
    try:
        sel = profilers[int(choice) - 1]
    except (ValueError, IndexError):
        _fail('Invalid selection')
        return
    r = client.query(f'$SETPROFILER,{sel}')
    _result(f'SETPROFILER,{sel}', r)


def test_set_cast_type(client):
    _header('Set cast type')
    print(f'  {C.CYAN}1.{C.RESET} UNDERWAY  (free-fall, time-limited)')
    print(f'  {C.CYAN}2.{C.RESET} DOWNHOLE  (powered payout, encoder-stopped)')
    print(f'  {C.DIM}0. Cancel{C.RESET}')
    mapping = {'1': 'UNDERWAY', '2': 'DOWNHOLE'}
    choice = input('  Choose: ').strip()
    if choice not in mapping:
        return
    r = client.query(f'$SETCASTTYPE,{mapping[choice]}')
    _result(f'SETCASTTYPE,{mapping[choice]}', r)


def test_set_stop_mode(client):
    _header('Set recovery stop mode')
    print(f'  {C.CYAN}1.{C.RESET} TRANSFERPOINT  (stop at data-transfer position)')
    print(f'  {C.CYAN}2.{C.RESET} LIMITSWITCH    (wind all the way in)')
    print(f'  {C.DIM}0. Cancel{C.RESET}')
    mapping = {'1': 'TRANSFERPOINT', '2': 'LIMITSWITCH'}
    choice = input('  Choose: ').strip()
    if choice not in mapping:
        return
    r = client.query(f'$SETSTOPMODE,{mapping[choice]}')
    _result(f'SETSTOPMODE,{mapping[choice]}', r)


def test_set_speed(client):
    _header('Set recovery speed (600–1200 RPM)')
    val = input('  RPM: ').strip()
    r = client.query(f'$SETSPEED,{val}')
    _result(f'SETSPEED,{val}', r)


def test_set_torque(client):
    _header('Set freefall back-torque (0–300 %)')
    val = input('  Torque %: ').strip()
    r = client.query(f'$SETTORQUE,{val}')
    _result(f'SETTORQUE,{val}', r)


def test_set_power_budget(client):
    _header('Set power budget (250–1000 W)')
    val = input('  Watts: ').strip()
    r = client.query(f'$SETPOWERBUDGET,{val}')
    _result(f'SETPOWERBUDGET,{val}', r)


def test_run_cast(client):
    _header('Run cast')
    safe = client.query('$QRYSAFEFLAG')
    cycle = client.query('$QRYCYCLEFLAG')
    _result('Safe flag', safe)
    _result('Cycle flag', cycle)
    if safe != 'true':
        _warn('Transfer point not set — $RUNCAST will be rejected (ERR,NOT_SAFE)')
    if cycle != 'done':
        _warn(f'Cycle flag is "{cycle}" — cast may be rejected or unsafe')

    depth = input('\n  Depth in metres (0.1–500): ').strip()
    confirm = input(f'  Send $RUNCAST,{depth} ? [y/N]: ').strip().lower()
    if confirm != 'y':
        print('  Cancelled.')
        return
    r = client.query(f'$RUNCAST,{depth}')
    _result(f'RUNCAST,{depth}', r)
    if r == 'OK':
        print(f'\n  {C.CYAN}Watching for events. Press Enter at any time to return to the menu.{C.RESET}')
        input()


def test_abort(client):
    _header('Abort cast')
    r = client.query('$ABORT')
    _result('ABORT', r)


def test_recover(client):
    _header('Emergency recover')
    _warn('This sends an immediate stop-and-wind command regardless of cycle state.')
    confirm = input('  Send $RECOVER ? [y/N]: ').strip().lower()
    if confirm != 'y':
        print('  Cancelled.')
        return
    r = client.query('$RECOVER')
    _result('RECOVER', r)


def test_recover_all(client):
    _header('Recover all (wind in to limit switch)')
    cycle = client.query('$QRYCYCLEFLAG')
    _result('Cycle flag', cycle)
    if cycle != 'done':
        _warn(f'Cycle flag is "{cycle}" — $RECOVERALL only acts when flag is "done"')
    confirm = input('  Send $RECOVERALL ? [y/N]: ').strip().lower()
    if confirm != 'y':
        print('  Cancelled.')
        return
    r = client.query('$RECOVERALL')
    _result('RECOVERALL', r)


# ── Error / boundary test ─────────────────────────────────────────────────────

def test_error_handling(client):
    _header('Error handling — boundary and invalid-input checks')
    print(f'  {C.DIM}Each case expects an ERR response.  '
          f'{C.GREEN}✓{C.RESET}{C.DIM} = server rejected correctly.{C.RESET}\n')

    cases = [
        ('$UNKNOWN_VERB',          'Unknown verb'),
        ('$QRYCASTTYPE,EXTRAARG',  'Query with unexpected argument'),
        ('$SETPROFILER',           'SETPROFILER — missing arg'),
        ('$SETPROFILER,INVALID',   'SETPROFILER — unknown type'),
        ('$SETCASTTYPE',           'SETCASTTYPE — missing arg'),
        ('$SETCASTTYPE,INVALID',   'SETCASTTYPE — invalid type'),
        ('$SETSTOPMODE',           'SETSTOPMODE — missing arg'),
        ('$SETSTOPMODE,INVALID',   'SETSTOPMODE — invalid mode'),
        ('$SETSPEED',              'SETSPEED — missing arg'),
        ('$SETSPEED,599',          'SETSPEED — below min (599)'),
        ('$SETSPEED,1201',         'SETSPEED — above max (1201)'),
        ('$SETSPEED,abc',          'SETSPEED — non-numeric'),
        ('$SETTORQUE',             'SETTORQUE — missing arg'),
        ('$SETTORQUE,-1',          'SETTORQUE — below min (-1)'),
        ('$SETTORQUE,301',         'SETTORQUE — above max (301)'),
        ('$SETPOWERBUDGET',        'SETPOWERBUDGET — missing arg'),
        ('$SETPOWERBUDGET,249',    'SETPOWERBUDGET — below min (249)'),
        ('$SETPOWERBUDGET,1001',   'SETPOWERBUDGET — above max (1001)'),
        ('$RUNCAST',               'RUNCAST — missing depth'),
        ('$RUNCAST,0',             'RUNCAST — depth zero'),
        ('$RUNCAST,-10',           'RUNCAST — negative depth'),
        ('$RUNCAST,501',           'RUNCAST — depth above max (501)'),
        ('$RUNCAST,abc',           'RUNCAST — non-numeric depth'),
    ]

    passed = 0
    failed = 0
    for cmd, desc in cases:
        r = client.query(cmd)
        if r is not None and r.startswith('ERR'):
            print(f'  {C.GREEN}✓{C.RESET}  {desc:<42} {C.DIM}{r}{C.RESET}')
            passed += 1
        else:
            val_str = r if r is not None else f'{C.RED}(timeout){C.RESET}'
            print(f'  {C.RED}✗{C.RESET}  {desc:<42} {C.RED}{val_str}{C.RESET}')
            failed += 1
        time.sleep(0.05)

    print(f'\n  {C.BOLD}Result: {C.GREEN}{passed} passed{C.RESET}'
          f'{C.BOLD}, {C.RED}{failed} failed{C.RESET}'
          f'{C.BOLD} out of {passed + failed} checks{C.RESET}')


# ── Watch mode ────────────────────────────────────────────────────────────────

def test_watch_events(client):
    _header('Watch for events')
    print(f'  {C.CYAN}Displaying all events. Press Enter to return to the menu.{C.RESET}\n')
    input()


# ── Raw command ───────────────────────────────────────────────────────────────

def test_raw(client):
    _header('Send raw command')
    print(f'  {C.DIM}Type a command (e.g. $QRYSPEED or $SETSPEED,1000) and press Enter.{C.RESET}')
    cmd = input('  > ').strip()
    if not cmd:
        return
    r = client.query(cmd)
    _result(cmd, r)


# ── Main menu ─────────────────────────────────────────────────────────────────

MENU = [
    ('Query all state variables',           test_all_queries),
    ('Set profiler type',                   test_set_profiler),
    ('Set cast type',                       test_set_cast_type),
    ('Set recovery stop mode',              test_set_stop_mode),
    ('Set recovery speed',                  test_set_speed),
    ('Set freefall back-torque',            test_set_torque),
    ('Set power budget',                    test_set_power_budget),
    ('Run cast',                            test_run_cast),
    ('Abort cast',                          test_abort),
    ('Emergency recover',                   test_recover),
    ('Recover all (wind in to limit)',      test_recover_all),
    ('Error-handling boundary tests',       test_error_handling),
    ('Watch for events',                    test_watch_events),
    ('Send raw command',                    test_raw),
]

def _print_menu():
    print(f'\n{C.BOLD}{"─" * 56}{C.RESET}')
    for i, (label, _) in enumerate(MENU, 1):
        print(f'  {C.CYAN}{i:>2}.{C.RESET}  {label}')
    print(f'   {C.DIM} 0.  Exit{C.RESET}')
    print(f'{C.BOLD}{"─" * 56}{C.RESET}')


def main():
    parser = argparse.ArgumentParser(
        description='Interactive test console for the Vigo TCP command server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Events are displayed in real time regardless of which menu item is active.')
    parser.add_argument('host', nargs='?', default=DEFAULT_HOST,
                        help=f'Vigo IP address (default: {DEFAULT_HOST})')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT,
                        help=f'TCP port (default: {DEFAULT_PORT})')
    args = parser.parse_args()

    print(f'\n{C.BOLD}{C.WHITE}Vigo TCP Command Server — Test Console{C.RESET}')
    print(f'{"─" * 56}')
    print(f'Target : {args.host}:{args.port}')
    print(f'Timeout: {RESPONSE_TIMEOUT}s per command')
    print(f'\nConnecting…')

    client = VigoClient(args.host, args.port)
    try:
        client.connect()
    except (OSError, socket.timeout) as e:
        _print_error(f'Connection failed: {e}')
        sys.exit(1)

    _ok(f'Connected to {args.host}:{args.port}')
    print(f'  {C.DIM}Unsolicited events ({C.YELLOW}EVT{C.RESET}{C.DIM}) appear '
          f'inline as they arrive from the server.{C.RESET}')

    try:
        while True:
            _print_menu()
            try:
                choice = input(f'{C.BOLD}>{C.RESET} ').strip()
            except EOFError:
                break
            if choice in ('0', 'q', 'quit', 'exit'):
                break
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(MENU):
                    MENU[idx][1](client)
                else:
                    print('  Out of range — enter a number from the menu.')
            except ValueError:
                print('  Enter the number next to the option you want.')
    except KeyboardInterrupt:
        print()

    print('\nDisconnecting…')
    client.disconnect()
    _ok('Done.')


if __name__ == '__main__':
    main()
