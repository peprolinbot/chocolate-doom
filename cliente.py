import socket
import pygame
import sys
import time

ip_escucha = '0.0.0.0' #'0.0.0.0' '127.0.0.1'
puerto_downlink = 6666

ip_satelite = '192.168.185.17'
puerto_uplink = 7777

pygame.init()
escala = 6
ancho, alto = 160, 100
screen = pygame.display.set_mode((ancho*escala, alto*escala))
pygame.display.set_caption("Tierra Downlink")

paleta_gris = [(i,i,i) for i in range(256)]

pygame.font.init()
fuente = pygame.font.SysFont("monosapce", 24, bold=True)
texto = fuente.render("RX: -- KB/s", True, (255,255,255))

bytes_acumulados = 0
tiempo_calculo = time.time()
kbps = 0.0

DOOM_KEYS = {
    # WASD
    pygame.K_w: 173,        # W -> Avanzar
    pygame.K_s: 175,        # S -> Retroceder
    pygame.K_a: 172,        # A -> Girar Izquierda
    pygame.K_d: 174,        # D -> Girar Derecha
    
    # FLECHAS REALES
    pygame.K_UP: 173,       # Flecha Arriba -> Avanzar
    pygame.K_DOWN: 175,     # Flecha Abajo -> Retroceder
    pygame.K_LEFT: 172,     # Flecha Izq -> Girar Izquierda
    pygame.K_RIGHT: 174,    # Flecha Der -> Girar Derecha
    
    # ACCIONES
    pygame.K_SPACE: 32,     # Espacio -> Abrir / Interactuar
    pygame.K_LCTRL: 157,    # Control Izq -> Disparar
    pygame.K_RETURN: 13,    # Enter -> Aceptar en el menú
    pygame.K_ESCAPE: 27     # Esc -> Abrir/Cerrar menú
}


s_d = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s_d.bind((ip_escucha, puerto_downlink))
s_d.setblocking(False)

s_u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


print("Esperando señal de video")

ejecutando = True
frame_buffer = bytearray (ancho*alto)
while ejecutando:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            ejecutando = False

        elif event.type == pygame.KEYDOWN:
            if event.key in DOOM_KEYS:
                comando = f"D:{DOOM_KEYS[event.key]}"
                s_u.sendto(comando.encode('ascii'), (ip_satelite, puerto_uplink))

        elif event.type == pygame.KEYUP:
            if event.key in DOOM_KEYS:
                comando = f"U:{DOOM_KEYS[event.key]}"
                s_u.sendto(comando.encode('ascii'), (ip_satelite, puerto_uplink))

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 3: 
                comando = "D:157"
                s_u.sendto(comando.encode('ascii'), (ip_satelite, puerto_uplink))

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 3:
                comando = "U:157"
                s_u.sendto(comando.encode('ascii'), (ip_satelite, puerto_uplink))

    try:
        while True:
            datos, dir = s_d.recvfrom(65535)
            
            bytes_acumulados+=len(datos)

            if len(datos) > 0:
                cabecera = datos[0]
                if cabecera == 0 and len(datos) == 16001:
                    frame_buffer[:] = datos[1:]
                elif cabecera == 1:
                    cambios = datos[1:]
                    for i in range (0, len(cambios), 3):
                        if i + 2 < len(cambios):
                            idx = (cambios[i]<<8) | cambios[i+1]
                            color = cambios[i+2]

                            if idx < len(frame_buffer):
                                frame_buffer[idx] = color



                imagen = pygame.image.frombuffer(bytes(frame_buffer), (ancho,alto), "P")
                imagen.set_palette(paleta_gris)
                imagen_escalada = pygame.transform.scale(imagen, (ancho*escala, alto * escala))

                screen.blit(imagen_escalada, (0,0))
                    

    except BlockingIOError:
        pass


    tiempo_actual = time.time()
    if tiempo_actual - tiempo_calculo >= 1.0:
        kbps = bytes_acumulados / 1024.0
        print(f"Consumo actual: {kbps:.2f} KB/s")

        texto = fuente.render(f"RX: {kbps:.2f} KB/s", True, (255,255,255))

        bytes_acumulados = 0
        tiempo_calculo = tiempo_actual

    screen.blit(texto, (10,10))
    pygame.display.flip()

pygame.quit()
sys.exit()

