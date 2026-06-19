"""Captura los bytes crudos que ConPTY emite para diagnosticar secuencias VT.

Uso: python scripts/capture_pty.py <salida.bin> <comando> [segundos] [texto-a-enviar]
"""

import sys
import threading
import time

from winpty import PTY

out_path = sys.argv[1]
command = sys.argv[2]
seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0
to_send = sys.argv[4] if len(sys.argv) > 4 else None

pty = PTY(100, 30)
parts = command.split(None, 1)
ok = pty.spawn(parts[0], cmdline=command if len(parts) > 1 else None)
if not ok:
    print("spawn failed")
    sys.exit(1)

chunks = []
done = threading.Event()


def reader():
    while not done.is_set():
        try:
            data = pty.read(8192, blocking=True)
        except Exception:
            break
        if not data:
            if pty.iseof() or not pty.isalive():
                break
            continue
        chunks.append(data)


t = threading.Thread(target=reader, daemon=True)
t.start()

time.sleep(seconds / 2)
if to_send:
    pty.write(to_send.replace("\\r", "\r").replace("\\x03", "\x03"))
time.sleep(seconds / 2)
done.set()
try:
    pty.write("\x03")
    time.sleep(0.3)
    pty.write("\x03")
except Exception:
    pass

data = "".join(chunks)
with open(out_path, "wb") as f:
    f.write(data.encode("utf-8"))
print(f"capturados {len(data)} chars -> {out_path}")
