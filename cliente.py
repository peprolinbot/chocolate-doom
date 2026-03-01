import socket
import pygame
import sys
import time
import threading
import subprocess
import re
import os
from prometheus_client import start_http_server, Gauge, Enum
import requests

# --- Configuración de Red ---
IP_ESCUCHA = os.getenv("DOOM_LISTEN_ADDR", "0.0.0.0")
PUERTO_DOWNLINK = int(os.getenv("DOOM_LISTEN_PORT", "6666"))

IP_SATELITE = os.getenv("DOOM_SAT_ADDR", "192.168.6.210")  # Ip raspberry
PUERTO_UPLINK = int(os.getenv("DOOM_SAT_PORT", "7777"))

pygame.init()
pygame.font.init()

ESCALA = 6
ANCHO, ALTO = 160, 100

# Ventana escalada
screen = pygame.display.set_mode((ANCHO * ESCALA, ALTO * ESCALA))
pygame.display.set_caption("Tierra Downlink")

# Paleta de grises
PALETA_GRIS = [(i, i, i) for i in range(256)]
FUENTE = pygame.font.SysFont("monospace", 24, bold=True)

# Mapea de teclas
DOOM_KEYS = {
    pygame.K_w: 173,
    pygame.K_s: 175,
    pygame.K_a: 172,
    pygame.K_d: 174,
    pygame.K_UP: 173,
    pygame.K_DOWN: 175,
    pygame.K_LEFT: 172,
    pygame.K_RIGHT: 174,
    pygame.K_SPACE: 32,
    pygame.K_LCTRL: 157,
    pygame.K_RETURN: 13,
    pygame.K_ESCAPE: 27,
}


# Mejora en la redundancia
def reparar_cabecera_hamming(byte_corrupto):
    p1 = (byte_corrupto >> 6) & 1
    p2 = (byte_corrupto >> 5) & 1
    d1 = (byte_corrupto >> 4) & 1
    p3 = (byte_corrupto >> 3) & 1
    d2 = (byte_corrupto >> 2) & 1
    d3 = (byte_corrupto >> 1) & 1
    d4 = byte_corrupto & 1

    s1 = p1 ^ d1 ^ d2 ^ d4
    s2 = p2 ^ d1 ^ d3 ^ d4
    s3 = p3 ^ d2 ^ d3 ^ d4
    sindrome = (s3 << 2) | (s2 << 1) | s1

    if sindrome != 0:
        # Volteamos el bit de datos correspondiente si roto
        if sindrome == 3:
            d1 ^= 1
        elif sindrome == 5:
            d2 ^= 1
        elif sindrome == 6:
            d3 ^= 1
        elif sindrome == 7:
            d4 ^= 1

    # Devolvemos los 4 bits de la cabecera original
    return (d1 << 3) | (d2 << 2) | (d3 << 1) | d4


# Inicialización de sockets
s_d = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s_d.bind((IP_ESCUCHA, PUERTO_DOWNLINK))
s_d.setblocking(False)
s_u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


# Métricas
class AppMetrics:
    def __init__(self):
        self.fps = Gauge("fps", "FPS")
        self.tx = Gauge("tx", "TX")
        self.ping = Gauge("ping", "Ping")
        self.err = Gauge("err", "Err")

    def update(self, fps, tx, ping, err):
        self.fps.set(fps)
        self.tx.set(tx)
        self.ping.set(ping)
        self.err.set(err)


exporter_port = int(os.getenv("EXPORTER_PORT", "9877"))
app_metrics = AppMetrics()
start_http_server(exporter_port)

# --- VARIABLES DE MÉTRICAS ---
ejecutando = True
ping_ms = 0.0


def medir_ping():
    global ping_ms, ejecutando
    while ejecutando:
        try:
            salida = subprocess.check_output(
                ["ping", "-c", "1", "-W", "1", IP_SATELITE], universal_newlines=True
            )
            match = re.search(r"time=([\d\.]+)", salida)
            if match:
                ping_ms = float(match.group(1))
        except:
            ping_ms = 999.0
        time.sleep(1)


threading.Thread(target=medir_ping, daemon=True).start()


# ----------------------

print("Esperando señal de video")

# Variables telemetría
bytes_acumulados = 0
frames_recibidos = 0
fps_actuales = 0
tiempo_calculo = time.time()
kbps = 0.0
paquetes_totales = 0
paquetes_corruptos = 0
loss_ratio = 0.0

# Inicialización de textos
texto_kbps = FUENTE.render("RX: -- Kb/s", True, (255, 255, 255), (0, 0, 0))
texto_fps = FUENTE.render("FPS: --", True, (255, 255, 255), (0, 0, 0))
texto_ping = FUENTE.render("PING: -- ms", True, (255, 255, 255), (0, 0, 0))
texto_loss = FUENTE.render("ERR : -- %", True, (255, 255, 255), (0, 0, 0))

# Framebuffer
frame_buffer = bytearray(8000)

LUT = [bytes([(i >> 4) * 17, (i & 0x0F) * 17]) for i in range(256)]


while ejecutando:
    # Uplink captura de controles
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            ejecutando = False
        elif event.type == pygame.KEYDOWN:
            if event.key in DOOM_KEYS:
                s_u.sendto(
                    f"D:{DOOM_KEYS[event.key]}".encode("ascii"),
                    (IP_SATELITE, PUERTO_UPLINK),
                )
        elif event.type == pygame.KEYUP:
            if event.key in DOOM_KEYS:
                s_u.sendto(
                    f"U:{DOOM_KEYS[event.key]}".encode("ascii"),
                    (IP_SATELITE, PUERTO_UPLINK),
                )
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            s_u.sendto("D:157".encode("ascii"), (IP_SATELITE, PUERTO_UPLINK))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            s_u.sendto("U:157".encode("ascii"), (IP_SATELITE, PUERTO_UPLINK))

    # Downlink recepción de video
    cambiado = False
    try:
        while True:
            datos, dir = s_d.recvfrom(65535)
            paquetes_totales += 1

            # Integridad estructural de cabecera + datos + checksum
            if len(datos) > 2:
                cabecera_cruda = datos[0]
                payload = datos[1:-1]  # Los datos crudos sin cabecera ni checksum
                checksum_recibido = datos[-1]  # Último byte (paridad)

                # Checksum XOR
                check_calculado = 0
                for b in payload:
                    check_calculado ^= b

                if check_calculado != checksum_recibido:
                    print(" ¡BIT FLIP EN VÍDEO! Frame descartado")
                    paquetes_corruptos += 1
                    continue

                # Reparar cabecera con hamming(7,4)
                cabecera = reparar_cabecera_hamming(cabecera_cruda)

                bytes_acumulados += len(datos)
                cambiado = True

                # Decod
                if cabecera == 0 and len(payload) == 8000:  # Raw, refresco total
                    frame_buffer[:] = payload

                elif cabecera == 1:  # Delta por macrobloques
                    for i in range(0, len(payload), 3):
                        if i + 2 < len(payload):
                            idx = (payload[i] << 8) | payload[i + 1]
                            if idx < 8000:
                                frame_buffer[idx] = payload[i + 2]

                elif cabecera == 2:  # RLE -- tono repe
                    idx_m = 0
                    for i in range(0, len(payload), 2):
                        if i + 1 < len(payload):
                            for _ in range(payload[i]):
                                if idx_m < 8000:
                                    frame_buffer[idx_m] = payload[i + 1]
                                    idx_m += 1
    except BlockingIOError:
        pass

    # Render
    if cambiado:
        frames_recibidos += 1
        unpacked_bytes = b"".join(LUT[b] for b in frame_buffer)

        # Pygame
        imagen = pygame.image.frombuffer(unpacked_bytes, (ANCHO, ALTO), "P")
        imagen.set_palette(PALETA_GRIS)
        screen.blit(
            pygame.transform.scale(imagen, (ANCHO * ESCALA, ALTO * ESCALA)), (0, 0)
        )

    # Cálculos de stats
    tiempo_actual = time.time()
    if tiempo_actual - tiempo_calculo >= 1.0:
        kbps = bytes_acumulados / 1024.0 * 8
        fps_actuales = frames_recibidos

        if paquetes_totales > 0:
            loss_ratio = (paquetes_corruptos / paquetes_totales) * 100.0
        else:
            loss_ratio = 0.0

        color_err = (0, 255, 0) if loss_ratio == 0 else (255, 165, 0)
        texto_loss = FUENTE.render(
            f"ERR : {loss_ratio:.1f} %", True, color_err, (0, 0, 0)
        )

        # Render textos
        texto_kbps = FUENTE.render(
            f"RX  : {kbps:.2f} Kb/s", True, (255, 255, 255), (0, 0, 0)
        )
        texto_fps = FUENTE.render(
            f"FPS : {fps_actuales}", True, (255, 255, 255), (0, 0, 0)
        )

        # Cambio de color de ping
        color_p = (0, 255, 0) if ping_ms < 700 else (255, 0, 0)
        texto_ping = FUENTE.render(
            f"PING: {ping_ms:03.0f} ms", True, color_p, (0, 0, 0)
        )

        app_metrics.update(fps_actuales, kbps, ping_ms, loss_ratio)

        bytes_acumulados = 0
        frames_recibidos = 0
        paquetes_totales = 0
        paquetes_corruptos = 0
        tiempo_calculo = tiempo_actual

    # Dibujamos los tres textos en posiciones distintas
    screen.blit(texto_kbps, (10, 10))
    screen.blit(texto_fps, (10, 40))
    screen.blit(texto_ping, (10, 70))
    screen.blit(texto_loss, (10, 100))

    pygame.display.flip()

pygame.quit()
sys.exit()
