"""Watchdog: start the Hermes Web Dashboard (127.0.0.1:9119) when it is down.
Watchdog: ξεκινά το Hermes Web Dashboard (127.0.0.1:9119) όταν δεν τρέχει.

Runs as a no_agent cron job once a minute and stays silent while all is well.
Console output is English first, Greek after (house style).
Τρέχει ως no_agent cron job κάθε 1 λεπτό. Σιωπηλό όταν όλα είναι εντάξει.
Η έξοδος είναι αγγλικά πρώτα, μετά ελληνικά.
"""

import os
import socket
import subprocess
import sys
import time

# History (2026-09-08): after an update the dashboard rebuilt its web UI (~60s
# boot). Two concurrent watchdog runs (the app runs two serve processes) spawned
# TWO dashboards -- the old lock was not atomic (it only checked a pid after the
# fact) and on Windows `hermes` has no cross-process build lock (fcntl is
# Unix-only). The two instances collided on port 9119 and BOTH died silently.
# Fix: atomic lock (O_EXCL) before the spawn + verify the lock holder really is
# a dashboard process.
#
# Ιστορικό (2026-09-08): μετά από update το dashboard έκανε rebuild του web UI
# (~60s boot). Δύο ταυτόχρονες εκτελέσεις του watchdog (το app τρέχει δύο
# serve processes) έκαναν ΔΥΟ spawns — το παλιό lock δεν ήταν atomic (έλεγχε
# μόνο pid μετά το γεγονός) και στα Windows το hermes δεν έχει cross-process
# build lock (fcntl μόνο σε Unix). Τα δύο instances συγκρούστηκαν στο port
# 9119 και πέθαναν ΚΑΙ ΤΑ ΔΥΟ αθόρυβα. Λύση: atomic lock (O_EXCL) πριν το
# spawn + επαλήθευση ότι ο κάτοχος του lock είναι όντως διεργασία dashboard.

HOME = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'hermes')
LOCK = os.path.join(HOME, 'dashboard_watchdog.lock')
LOGDIR = os.path.join(HOME, 'logs')
HOST, PORT = '127.0.0.1', 9119
# A pid-less lock younger than this means a boot is in progress.
# Lock χωρίς pid νεότερο από αυτό = boot σε εξέλιξη.
STALE_EMPTY_LOCK_SECONDS = 120


def port_open():
    try:
        with socket.create_connection((HOST, PORT), timeout=2):
            return True
    except OSError:
        return False


def pid_alive(pid):
    if not pid or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def pid_is_dashboard(pid):
    """True if pid belongs to a process running `hermes dashboard`.

    True αν το pid ανήκει σε διεργασία που τρέχει `hermes dashboard`.
    """
    if not pid or pid <= 0:
        return False
    try:
        import psutil
        try:
            cmdline = ' '.join(psutil.Process(int(pid)).cmdline() or []).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
        return 'dashboard' in cmdline and 'hermes' in cmdline
    except ImportError:
        # No psutil: accept any live pid (the old behaviour).
        # Χωρίς psutil: δεχόμαστε κάθε ζωντανό pid (παλιά συμπεριφορά).
        return pid_alive(pid)


def _read_lock_pid():
    try:
        with open(LOCK) as f:
            raw = f.read().strip()
        return int(raw) if raw.isdigit() else None
    except (OSError, ValueError):
        return None


def _lock_fresh():
    try:
        return time.time() - os.path.getmtime(LOCK) < STALE_EMPTY_LOCK_SECONDS
    except OSError:
        return False


def _acquire_lock_and_spawn():
    """Try to take the lock atomically (O_EXCL); on success spawn the dashboard
    and write its pid into the lock. Returns the proc, or None if another
    watchdog got there first (or the holder is a live dashboard).

    Προσπαθεί να αποκτήσει το lock atomic (O_EXCL). Αν το πάρει, κάνει το
    spawn και γράφει το pid του dashboard στο lock. Επιστρέφει το proc ή None
    αν άλλος watchdog το πρόλαβε (ή ο κάτοχος είναι ζωντανό dashboard).
    """
    for attempt in (0, 1):  # second attempt: after breaking a stale lock
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = _read_lock_pid()
            if holder is None:
                # Lock without a pid: either just created by another watchdog
                # that is about to spawn, or stale from an older version.
                # Lock χωρίς pid: μόλις δημιουργήθηκε από άλλο watchdog που
                # ετοιμάζει spawn (ή είναι stale από παλιά έκδοση).
                if _lock_fresh():
                    return None  # someone else is booting -- stay out of it
                # Stale and pid-less: break it and retry.
                try:
                    os.remove(LOCK)
                except OSError:
                    return None
                continue
            if pid_is_dashboard(holder):
                return None  # a live dashboard is booting or already up
            if pid_alive(holder) and not pid_is_dashboard(holder):
                # Live pid that is NOT a dashboard (pid reuse by another
                # process): the lock is bogus -- break it.
                try:
                    os.remove(LOCK)
                except OSError:
                    return None
                continue
            # Dead pid: stale lock -- break it and retry.
            try:
                os.remove(LOCK)
            except OSError:
                return None
            continue
        # We hold the lock. Spawn, then write the pid.
        env = dict(os.environ)
        env.pop('HERMES_WEB_DIST', None)  # otherwise it serves the desktop dist instead of the web dashboard
        try:
            os.makedirs(LOGDIR, exist_ok=True)
            logpath = os.path.join(LOGDIR, 'dashboard_autostart.log')
            with open(logpath, 'a', encoding='utf-8') as logf:
                proc = subprocess.Popen(
                    [sys.executable, '-m', 'hermes_cli.main', 'dashboard'],
                    env=env,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),
                    close_fds=True,
                )
            try:
                os.write(fd, str(proc.pid).encode())
            finally:
                os.close(fd)
            return proc
        except Exception as exc:  # noqa: BLE001
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.remove(LOCK)
            except OSError:
                pass
            print(f'[dashboard-watchdog] FAILED to start the dashboard: {exc}')
            print(f'[dashboard-watchdog] ΑΠΟΤΥΧΙΑ εκκίνησης dashboard: {exc}')
            return None
    return None


def main():
    if port_open():
        return  # dashboard already running - nothing to do (silent) / σιωπηλό

    proc = _acquire_lock_and_spawn()
    if proc is None:
        return  # another watchdog took over, or lock was valid (silent) / σιωπηλό
    logpath = os.path.join(LOGDIR, 'dashboard_autostart.log')
    print(f'[dashboard-watchdog] dashboard started (pid {proc.pid}) at {time.strftime("%H:%M:%S")} - log: {logpath}')
    print(f'[dashboard-watchdog] Ξεκίνησε το dashboard (pid {proc.pid}) στις {time.strftime("%H:%M:%S")} - log: {logpath}')


if __name__ == '__main__':
    main()
