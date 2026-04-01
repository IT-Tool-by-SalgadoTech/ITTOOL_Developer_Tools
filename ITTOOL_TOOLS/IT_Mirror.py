#!/usr/bin/env python3
"""
IT-Tool PC Mirror
Receives the IT-Tool screen (160x128 RGB565) via USB Serial
and displays it scaled on your PC.

Requirements:
    pip install pygame pyserial

Usage:
    python IT_Mirror.py
    python IT_Mirror.py --port COM10
    python IT_Mirror.py --port /dev/ttyACM0 --scale 4
"""

import sys
import argparse
import threading
import time
import struct

# ── Dependency check ──────────────────────────────────────────────────────────
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("ERROR: pyserial not installed.")
    print("  Run: pip install pyserial")
    sys.exit(1)

try:
    import pygame
except ImportError:
    print("ERROR: pygame not installed.")
    print("  Run: pip install pygame")
    sys.exit(1)

# ── Constants ─────────────────────────────────────────────────────────────────
FRAME_W      = 160
FRAME_H      = 128
FRAME_PIXELS = FRAME_W * FRAME_H
FRAME_BYTES  = FRAME_PIXELS * 2          # RGB565 = 2 bytes/pixel
BAUD         = 921600

HDR_MAGIC    = bytes([0xFF, 0xAA])
FTR_MAGIC    = bytes([0xFF, 0xBB])
HEADER_SIZE  = 6                         # 0xFF 0xAA W_hi W_lo H_hi H_lo

# ── Auto-detect / selector interactivo de puerto ─────────────────────────────
def list_serial_ports():
    ports = []
    for p in serial.tools.list_ports.comports():
        ports.append((p.device, p.description or ""))
    return sorted(ports, key=lambda x: x[0])

def find_ittool_port():
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        if any(k in desc for k in ("usb serial", "cp210", "ch340", "cdc")):
            return p.device
    return None

def select_port_interactive():
    ports = list_serial_ports()
    if not ports:
        print("No se encontraron puertos seriales.")
        print("Conecta el IT-Tool por USB e intenta de nuevo.")
        sys.exit(1)

    print("\n=== Puertos seriales disponibles ===")
    for i, (dev, desc) in enumerate(ports):
        print(f"  [{i+1}] {dev}  —  {desc}")
    print("  [0] Escribir puerto manualmente")
    print()

    while True:
        try:
            raw = input("Elige un número: ").strip()
            n = int(raw)
            if n == 0:
                manual = input("Puerto (ej: COM10 o /dev/ttyACM0): ").strip()
                if manual:
                    return manual
            elif 1 <= n <= len(ports):
                return ports[n-1][0]
            else:
                print(f"  Número inválido. Elige entre 0 y {len(ports)}.")
        except (ValueError, KeyboardInterrupt):
            print("\nCancelado.")
            sys.exit(0)

# ── RGB565 → RGB888 ───────────────────────────────────────────────────────────
def rgb565_to_rgb888(px):
    r = ((px >> 11) & 0x1F) << 3
    g = ((px >>  5) & 0x3F) << 2
    b = ( px        & 0x1F) << 3
    return (r, g, b)

# ── Frame receiver thread ─────────────────────────────────────────────────────
class FrameReceiver(threading.Thread):
    def __init__(self, port, baud):
        super().__init__(daemon=True)
        self.port     = port
        self.baud     = baud
        self.frame    = None          # latest complete frame (list of RGB tuples)
        self.lock     = threading.Lock()
        self.running  = True
        self.fps      = 0
        self._fps_cnt = 0
        self._fps_ts  = time.time()
        self.error    = None

    def run(self):
        try:
            ser = serial.Serial(self.port, self.baud, timeout=2)
        except serial.SerialException as e:
            self.error = str(e)
            return

        buf = bytearray()

        while self.running:
            try:
                chunk = ser.read(512)
                if not chunk:
                    continue
                buf.extend(chunk)

                # Search for header
                while True:
                    idx = buf.find(HDR_MAGIC)
                    if idx == -1:
                        # Keep last byte in case it's start of next header
                        buf = buf[-1:]
                        break
                    if idx > 0:
                        buf = buf[idx:]

                    # Need at least header + pixels + footer
                    needed = HEADER_SIZE + FRAME_BYTES + 2
                    if len(buf) < needed:
                        break

                    # Validate dimensions from header
                    w = (buf[2] << 8) | buf[3]
                    h = (buf[4] << 8) | buf[5]
                    if w != FRAME_W or h != FRAME_H:
                        buf = buf[2:]   # bad header, skip
                        continue

                    # Check footer
                    ftr_pos = HEADER_SIZE + FRAME_BYTES
                    if buf[ftr_pos:ftr_pos+2] != FTR_MAGIC:
                        buf = buf[2:]   # bad frame, skip
                        continue

                    # Valid frame — decode
                    raw = buf[HEADER_SIZE:HEADER_SIZE + FRAME_BYTES]
                    pixels = []
                    for i in range(0, len(raw), 2):
                        px = (raw[i] << 8) | raw[i+1]
                        pixels.append(rgb565_to_rgb888(px))

                    with self.lock:
                        self.frame = pixels

                    # FPS counter
                    self._fps_cnt += 1
                    now = time.time()
                    if now - self._fps_ts >= 1.0:
                        self.fps      = self._fps_cnt
                        self._fps_cnt = 0
                        self._fps_ts  = now

                    buf = buf[HEADER_SIZE + FRAME_BYTES + 2:]

            except serial.SerialException as e:
                self.error = str(e)
                break

        try:
            ser.close()
        except Exception:
            pass

    def get_frame(self):
        with self.lock:
            return self.frame

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="IT-Tool PC Mirror")
    parser.add_argument("--port",  default=None, help="Serial port (auto-detect if omitted)")
    parser.add_argument("--scale", type=int, default=5, help="Display scale factor (default 5 → 800x640)")
    args = parser.parse_args()

    # Port selection
    port = args.port
    if port is None:
        # ── Secuencia unplug/plug (igual que Script_Saver.ps1) ───────────────
        print("")
        print("=" * 46)
        print("   IT-Tool PC Mirror — Port Setup")
        print("=" * 46)
        print("")
        print("Before continuing:")
        print("  1. Unplug the IT-Tool USB cable")
        print("  2. Plug it back in")
        print("")
        input("Come back here and press ENTER...")
        print("")

        # Detectar puertos disponibles tras el reconectar
        ports = list_serial_ports()
        if not ports:
            print("No COM ports detected. Check IT-Tool USB connection.")
            input("Press ENTER to close.")
            sys.exit(1)

        print("Available ports:")
        for i, (dev, desc) in enumerate(ports):
            print(f"  {i+1}. {dev}  —  {desc}")
        print("")

        # Si solo hay uno, preguntar confirmación
        if len(ports) == 1:
            print(f"Only one port found: {ports[0][0]}")
            ans = input("Use it? [Y/n]: ").strip().lower()
            if ans in ("", "y", "s"):
                port = ports[0][0]
            else:
                input("Connect the IT-Tool and restart the script. Press ENTER to close.")
                sys.exit(0)
        else:
            while True:
                try:
                    n = int(input("Select port number: ").strip())
                    if 1 <= n <= len(ports):
                        port = ports[n-1][0]
                        break
                    else:
                        print(f"  Invalid option.")
                except (ValueError, KeyboardInterrupt):
                    print("\nCancelled.")
                    sys.exit(0)

        print(f"Using {port}")
        print("")
    else:
        print(f"Using port: {port}")

    scale = max(1, args.scale)
    WIN_W = FRAME_W * scale
    WIN_H = FRAME_H * scale

    # Start receiver
    receiver = FrameReceiver(port, BAUD)
    receiver.start()

    # Pygame init
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("IT-Tool PC Mirror")
    clock  = pygame.time.Clock()
    font   = pygame.font.SysFont("monospace", 14)

    # Surface for the frame
    frame_surf = pygame.Surface((FRAME_W, FRAME_H))
    frame_surf.fill((0, 0, 0))

    waiting_text   = True
    last_frame_ref = None

    print(f"Window: {WIN_W}x{WIN_H}  Scale: {scale}x")
    print("Waiting for IT-Tool to enter PC_Mirror mode...")
    print("Press B on IT-Tool or close this window to exit.")

    running = True
    while running:
        # ── Events ────────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        # ── Check receiver error ──────────────────────────────────────────────
        if receiver.error:
            screen.fill((30, 0, 0))
            msg = font.render(f"Serial error: {receiver.error}", True, (255, 80, 80))
            screen.blit(msg, (10, WIN_H // 2 - 10))
            pygame.display.flip()
            clock.tick(5)
            continue

        # ── Get latest frame ──────────────────────────────────────────────────
        frame = receiver.get_frame()

        if frame is None:
            # No frame yet — show waiting screen
            screen.fill((10, 10, 30))
            lines = [
                "IT-Tool PC Mirror",
                "",
                f"Port: {port}",
                "",
                "Waiting for IT-Tool...",
                "Select PC_Mirror from the",
                "IT-Tool main menu.",
            ]
            y = WIN_H // 2 - len(lines) * 9
            for line in lines:
                surf = font.render(line, True, (253, 160, 32))
                screen.blit(surf, (WIN_W // 2 - surf.get_width() // 2, y))
                y += 20
            pygame.display.flip()
            clock.tick(10)
            continue

        # ── Render frame ──────────────────────────────────────────────────────
        if frame is not last_frame_ref:
            last_frame_ref = frame
            waiting_text = False
            # Paint pixels into surface
            pa = pygame.PixelArray(frame_surf)
            for y in range(FRAME_H):
                for x in range(FRAME_W):
                    r, g, b = frame[y * FRAME_W + x]
                    pa[x][y] = frame_surf.map_rgb(r, g, b)
            del pa

        # Scale and blit
        scaled = pygame.transform.scale(frame_surf, (WIN_W, WIN_H))
        screen.blit(scaled, (0, 0))

        # FPS overlay (top-right corner)
        fps_txt = font.render(f"{receiver.fps} fps", True, (253, 160, 32))
        screen.blit(fps_txt, (WIN_W - fps_txt.get_width() - 6, 4))

        pygame.display.flip()
        clock.tick(60)

    receiver.running = False
    pygame.quit()
    print("Closed.")

if __name__ == "__main__":
    main()
