import os
import socket
import subprocess
import sys
import time

# Watchdog: ξεκινά το Hermes Web Dashboard (127.0.0.1:9119) όταν δεν τρέχει.
# Τρέχει ως no_agent cron job κάθε 1 λεπτό. Σιωπηλό όταν όλα είναι εντάξει.
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
STALE_EMPTY_LOCK_SECONDS = 120  # lock χωρίς pid νεότερο από αυτό = boot σε εξέλιξη


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
    """True αν το pid ανήκει σε διεργασία που τρέχει `hermes dashboard`."""
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
    """Προσπαθεί να αποκτήσει το lock atomic (O_EXCL). Αν το πάρει, κάνει το
    spawn και γράφει το pid του dashboard στο lock. Επιστρέφει το proc ή None
    αν άλλος watchdog το πρόλαβε (ή ο κάτοχος είναι ζωντανό dashboard)."""
    for attempt in (0, 1):  # 2η προσπάθεια: μετά από κλέψιμο stale lock
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = _read_lock_pid()
            if holder is None:
                # Lock χωρίς pid: μόλις δημιουργήθηκε από άλλο watchdog που
                # ετοιμάζει spawn (ή είναι stale από παλιά έκδοση).
                if _lock_fresh():
                    return None  # κάποιος άλλος bootάρει — μην μπλέξουμε
                # Stale χωρίς pid: το σπάμε και ξαναπροσπαθούμε.
                try:
                    os.remove(LOCK)
                except OSError:
                    return None
                continue
            if pid_is_dashboard(holder):
                return None  # ζωντανό dashboard bootάρει ή τρέχει ήδη
            if pid_alive(holder) and not pid_is_dashboard(holder):
                # Ζωντανό pid που ΔΕΝ είναι dashboard (pid reuse από άλλη
                # διεργασία): το lock είναι ψεύτικο — το σπάμε.
                try:
                    os.remove(LOCK)
                except OSError:
                    return None
                continue
            # Νεκρό pid: stale lock — το σπάμε και ξαναπροσπαθούμε.
            try:
                os.remove(LOCK)
            except OSError:
                return None
            continue
        # Έχουμε το lock. Spawnάρουμε και μετά γράφουμε το pid.
        env = dict(os.environ)
        env.pop('HERMES_WEB_DIST', None)  # αλλιώς σερβίρει το desktop dist αντί για το web dashboard
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
            print(f'[dashboard-watchdog] ΑΠΟΤΥΧΙΑ εκκίνησης dashboard: {exc}')
            return None
    return None


def main():
    if port_open():
        return  # το dashboard τρέχει ήδη - τίποτα να κάνουμε (σιωπηλό)

    proc = _acquire_lock_and_spawn()
    if proc is None:
        return  # άλλος watchdog ανέλαβε ή το lock ήταν έγκυρο (σιωπηλό)
    print(f'[dashboard-watchdog] Ξεκίνησε το dashboard (pid {proc.pid}) στις {time.strftime("%H:%M:%S")} - log: {os.path.join(LOGDIR, "dashboard_autostart.log")}')


if __name__ == '__main__':
    main()
