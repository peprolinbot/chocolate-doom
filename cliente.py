import socket
import pygame
import sys
import time
import threading 
import subprocess
import re

ip_escucha = '0.0.0.0'
puerto_downlink = 6666

ip_satelite = '192.168.6.229'#'192.168.185.17'
puerto_uplink = 7777

pygame.init()
escala = 6
ancho, alto = 160, 100
screen = pygame.display.set_mode((ancho*escala, alto*escala))
pygame.display.set_caption("Tierra Downlink")

paleta_gris = [(i,i,i) for i in range(256)]

pygame.font.init()
fuente = pygame.font.SysFont("monospace", 24, bold=True)

# --- VARIABLES DE MÉTRICAS ---
bytes_acumulados = 0
bytes_enviados_acumulados = 0  # NUEVO: Para medir TX
frames_recibidos = 0 
frames_enviados = 0
fps_actuales = 0
ping_ms = 0.0
tiempo_calculo = time.time()
kbps = 0.0
tx_kbps = 0.0  # NUEVO: Velocidad de TX

# Inicialización de objetos de texto
texto_kbps = fuente.render("RX  : -- KB/s", True, (255,255,255))
texto_tx_kbps = fuente.render("TX  : -- KB/s", True, (255,255,255)) # NUEVO
texto_fps  = fuente.render("FPS : --", True, (255,255,255))
texto_ping = fuente.render("PING: -- ms", True, (255,255,255))

DOOM_KEYS = {
    pygame.K_w: 173, pygame.K_s: 175, pygame.K_a: 172, pygame.K_d: 174,
    pygame.K_UP: 173, pygame.K_DOWN: 175, pygame.K_LEFT: 172, pygame.K_RIGHT: 174,
    pygame.K_SPACE: 32, pygame.K_LCTRL: 157, pygame.K_RETURN: 13, pygame.K_ESCAPE: 27
}

s_d = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s_d.bind((ip_escucha, puerto_downlink))
s_d.setblocking(False)
s_u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def decode_hamming(byte_val):
    """
    Decodifica Hamming (7,4). Puede corregir 1 bit de error.
    Bits: p1(0), p2(1), d0(2), p3(3), d1(4), d2(5), d3(6)
    """
    p1 = (byte_val >> 0) & 1
    p2 = (byte_val >> 1) & 1
    d0 = (byte_val >> 2) & 1
    p3 = (byte_val >> 3) & 1
    d1 = (byte_val >> 4) & 1
    d2 = (byte_val >> 5) & 1
    d3 = (byte_val >> 6) & 1

    s1 = p1 ^ d0 ^ d1 ^ d3
    s2 = p2 ^ d0 ^ d2 ^ d3
    s3 = p3 ^ d1 ^ d2 ^ d3
    
    syndrome = (s3 << 2) | (s2 << 1) | s1

    # Corregir error si el síndrome no es 0
    if syndrome != 0:
        byte_val ^= (1 << (syndrome - 1))
        # Recalcular los bits de datos tras la corrección
        d0 = (byte_val >> 2) & 1
        d1 = (byte_val >> 4) & 1
        d2 = (byte_val >> 5) & 1
        d3 = (byte_val >> 6) & 1

    return (d3 << 3) | (d2 << 2) | (d1 << 1) | d0

def validar_checksum(datos_completos):
    chk = 0
    for b in datos_completos:
        chk ^= b
    return chk == 0

# --- HILO PARA EL PING ---
ejecutando = True
def medir_ping():
    global ping_ms, ejecutando
    while ejecutando:
        try:
            salida = subprocess.check_output(["ping", "-c", "1", "-W", "1", ip_satelite], universal_newlines=True)
            match = re.search(r'time=([\d\.]+)', salida)
            if match: ping_ms = float(match.group(1))
        except: ping_ms = 999.0
        time.sleep(1)

threading.Thread(target=medir_ping, daemon=True).start()

print("Esperando señal de video")

frame_buffer = bytearray(8000)
LUT = [bytes([(i >> 4) * 17, (i & 0x0F) * 17]) for i in range(256)]

while ejecutando:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            ejecutando = False
        elif event.type == pygame.KEYDOWN:
            if event.key in DOOM_KEYS:
                # Modificado para guardar el tamaño del mensaje enviado
                msg = f"D:{DOOM_KEYS[event.key]}".encode('ascii')
                s_u.sendto(msg, (ip_satelite, puerto_uplink))
                bytes_enviados_acumulados += len(msg)
        elif event.type == pygame.KEYUP:
            if event.key in DOOM_KEYS:
                msg = f"U:{DOOM_KEYS[event.key]}".encode('ascii')
                s_u.sendto(msg, (ip_satelite, puerto_uplink))
                bytes_enviados_acumulados += len(msg)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            msg = b"D:157"
            s_u.sendto(msg, (ip_satelite, puerto_uplink))
            bytes_enviados_acumulados += len(msg)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            msg = b"U:157"
            s_u.sendto(msg, (ip_satelite, puerto_uplink))
            bytes_enviados_acumulados += len(msg)

    cambios = False
    paquetes_ok = 0
    paquetes_corruptos = 0
    correcciones_hamming = 0

    try:
        while True:
            datos, dir = s_d.recvfrom(65535)
            bytes_acumulados += len(datos)
            
            if len(datos) >= 3:
                # 1. Validar Checksum Global (incluye cabecera)
                # XOR de todos los bytes menos el último debe ser igual al último byte
                if not validar_checksum(datos):
                    chk_calculado = 0
                    for b in datos[:-1]:
                        chk_calculado ^= b
                    print(f"[DEBUG] Calculado: {chk_calculado}, Recibido: {datos[-1]}, XOR_total: {chk_calculado ^ datos[-1]}, len={len(datos)}")
                    continue

                # 2. Leer cabecera y extraer payload
                cabecera = datos[0] 
                payload = datos[1:-1] # Los datos están entre la cabecera y el checksum
                cambios = True

                if cabecera == 0 and len(payload) == 8000:
                    frame_buffer[:] = payload
                elif cabecera == 1:
                    for i in range(0, len(payload), 3):
                        if i+2 < len(payload):
                            idx = (payload[i] << 8) | payload[i+1]
                            if idx < 8000: frame_buffer[idx] = payload[i+2]
                elif cabecera == 2:
                    idx_m = 0
                    for i in range(0, len(payload), 2):
                        if i+1 < len(payload):
                            contador, color = payload[i], payload[i+1]
                            # Seguridad: No escribir fuera de los 8000 píxeles
                            for _ in range(min(contador, 8000 - idx_m)):
                                frame_buffer[idx_m] = color
                                idx_m += 1
    except BlockingIOError:
        pass

    if cambios:
        frames_recibidos += 1 # Contamos frame para FPS
        unpacked_bytes = b''.join(LUT[b] for b in frame_buffer)
        imagen = pygame.image.frombuffer(unpacked_bytes, (ancho, alto), "P")        
        imagen.set_palette(paleta_gris)
        screen.blit(pygame.transform.scale(imagen, (ancho*escala, alto*escala)), (0,0))

    # --- CÁLCULO Y ACTUALIZACIÓN DE TEXTOS ---
    tiempo_actual = time.time()
    if tiempo_actual - tiempo_calculo >= 1.0:
        kbps = bytes_acumulados / 1024.0 *8
        tx_kbps = bytes_enviados_acumulados / 1024.0 *8 # Cálculo de TX
        fps_actuales = frames_recibidos
        
        # Renderizamos los textos
        texto_kbps = fuente.render(f"RX  : {kbps:.2f} KB/s", True, (255,255,255))
        texto_tx_kbps = fuente.render(f"TX  : {tx_kbps:.4f} KB/s", True, (255,255,255))
        texto_fps  = fuente.render(f"FPS : {fps_actuales}", True, (255,255,255))
        
        # Color del ping: verde si es bajo, rojo si es alto
        color_p = (0, 255, 0) if ping_ms < 100 else (255, 0, 0)
        texto_ping = fuente.render(f"PING: {ping_ms:.0f} ms", True, color_p)

        # Reseteo de contadores
        bytes_acumulados = 0
        bytes_enviados_acumulados = 0
        frames_recibidos = 0
        tiempo_calculo = tiempo_actual

    # Dibujamos los textos en posiciones ordenadas (he desplazado hacia abajo FPS y PING)
    screen.blit(texto_kbps, (10, 10))
    screen.blit(texto_tx_kbps, (10, 40))
    screen.blit(texto_fps, (10, 70))
    screen.blit(texto_ping, (10, 100))
    
    pygame.display.flip()

pygame.quit()
sys.exit()
