import socket
import pygame
import sys
import time
import threading 
import subprocess
import re

ip_escucha = '0.0.0.0'
puerto_downlink = 6666

ip_satelite = '192.168.6.229'#'192.168.6.210'
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
frames_recibidos = 0 
fps_actuales = 0
ping_ms = 0.0
tiempo_calculo = time.time()
kbps = 0.0

# Inicialización de objetos de texto
texto_kbps = fuente.render("RX: -- Kb/s", True, (255,255,255))
texto_fps  = fuente.render("FPS: --", True, (255,255,255))
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
        print(f"🛠️ ¡FEC ACTIVO! Cabecera corrupta (Síndrome {sindrome}). Auto-reparando...")
        if sindrome == 3: d1 ^= 1
        elif sindrome == 5: d2 ^= 1
        elif sindrome == 6: d3 ^= 1
        elif sindrome == 7: d4 ^= 1

    return (d1 << 3) | (d2 << 2) | (d3 << 1) | d4


frame_buffer = bytearray(8000)
LUT = [bytes([(i >> 4) * 17, (i & 0x0F) * 17]) for i in range(256)]

while ejecutando:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            ejecutando = False
        elif event.type == pygame.KEYDOWN:
            if event.key in DOOM_KEYS:
                s_u.sendto(f"D:{DOOM_KEYS[event.key]}".encode('ascii'), (ip_satelite, puerto_uplink))
        elif event.type == pygame.KEYUP:
            if event.key in DOOM_KEYS:
                s_u.sendto(f"U:{DOOM_KEYS[event.key]}".encode('ascii'), (ip_satelite, puerto_uplink))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            s_u.sendto("D:157".encode('ascii'), (ip_satelite, puerto_uplink))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            s_u.sendto("U:157".encode('ascii'), (ip_satelite, puerto_uplink))

    hubo_cambios = False
    try:
        while True:
            datos, dir = s_d.recvfrom(65535)
            
            if len(datos) > 2: # Mínimo: Cabecera + Datos + Checksum
                cabecera_cruda = datos[0]
                payload = datos[1:-1]         # Los datos crudos sin cabecera ni checksum
                checksum_recibido = datos[-1] # El último byte
                
                # 1. VERIFICAR PAYLOAD CON CHECKSUM
                check_calculado = 0
                for b in payload:
                    check_calculado ^= b
                    
                if check_calculado != checksum_recibido:
                    print(" ¡BIT FLIP EN VÍDEO! Frame descartado")
                    continue
                
                # 2. REPARAR CABECERA CON HAMMING(7,4)
                cabecera = reparar_cabecera_hamming(cabecera_cruda)
                
                bytes_acumulados += len(datos)
                hubo_cambios = True
                    
                if cabecera == 0 and len(payload) == 8000:
                    frame_buffer[:] = payload
                    
                elif cabecera == 1:
                    for i in range(0, len(payload), 3):
                        if i+2 < len(payload):
                            idx = (payload[i]<<8) | payload[i+1]
                            if idx < 8000: frame_buffer[idx] = payload[i+2]
                            
                elif cabecera == 2:
                    idx_m = 0
                    for i in range(0, len(payload), 2):
                        if i+1 < len(payload):
                            for _ in range(payload[i]):
                                if idx_m < 8000:
                                    frame_buffer[idx_m] = payload[i+1]
                                    idx_m += 1
    except BlockingIOError:
        pass

    if hubo_cambios:
        frames_recibidos += 1 # Contamos frame para FPS
        unpacked_bytes = b''.join(LUT[b] for b in frame_buffer)
        imagen = pygame.image.frombuffer(unpacked_bytes, (ancho, alto), "P")        
        imagen.set_palette(paleta_gris)
        screen.blit(pygame.transform.scale(imagen, (ancho*escala, alto*escala)), (0,0))

    # --- CÁLCULO Y ACTUALIZACIÓN DE TEXTO ---
    tiempo_actual = time.time()
    if tiempo_actual - tiempo_calculo >= 1.0:
        kbps = bytes_acumulados / 1024.0*8
        fps_actuales = frames_recibidos
        
        # Renderizamos los tres textos
        texto_kbps = fuente.render(f"RX  : {kbps:.2f} Kb/s", True, (255,255,255))
        texto_fps  = fuente.render(f"FPS : {fps_actuales}", True, (255,255,255))
        
        # Color del ping: verde si es bajo, rojo si es alto
        color_p = (0, 255, 0) if ping_ms < 100 else (255, 0, 0)
        texto_ping = fuente.render(f"PING: {ping_ms:.0f} ms", True, color_p)

        bytes_acumulados = 0
        frames_recibidos = 0
        tiempo_calculo = tiempo_actual

    # Dibujamos los tres textos en posiciones distintas
    screen.blit(texto_kbps, (10, 10))
    screen.blit(texto_fps, (10, 40))
    screen.blit(texto_ping, (10, 70))
    
    pygame.display.flip()

pygame.quit()
sys.exit()