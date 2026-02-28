# Slay-sat 🛰️ 

![Slay-sat banner](banner.jpg)

_Créditos imagen: [wallpapers.com](https://wallpapers.com)_

_README original de _Chocolate Doom_ [aquí](README.chocolate-doom.md)_

Este es un proyecto para el [HackUDC 2026](https://hackudc.gpul.org), que
consiste en ejecutar Doom en un satélite (hipotéticamente).

## 📐 Arquitectura

La idea es emplear un protocolo de transmisión a prueba de entornos de red
hostiles (alta latencia, pérdida de paquetes, ancho de banda limitado...)
manteniendo la jugabilidad.

De esta manera se intenta simular la comunicación de un satélite (_servidor_),
donde se ejecuta el motor del juego, y una estación en tierra (_cliente_) donde
se visualiza el juego y se toman acciones.

### 📡 Entorno de transmisión

Dado que el objetivo es simular la comunicación con un satélite, se han asumido
ciertas características de su entorno para aproximar las pruebas realizadas
durante el desarrollo a una situación real:

- El servidor se considera un satélite geoestacionario, por lo que la conexión
  puede establecerse de forma continuada y sin interrupciones causadas por su
  trayectoria.
- Dada la distancia entre la superficie terrestre y el satélite, se asume un RTT
  de entre 500 y 600 ms, debido a que el tiempo medio de transmisión entre ambos
  es de 250-300ms en casos reales.
- Debido a la falta de protección ante ondas electromagnéticas en el espacio, la
  posibilidad de que un paquete se pierda o sea modificado durante su
  transmisión es muy alta.

Teniendo esto en cuenta, esta versión modificada de Chocolate DOOM prioriza
adaptarse a estas situaciones frente a proporcionar una experiencia de juego
idéntica al juego en local.

## 💡 Probar el proyecto

Todo funciona con ✨[Nix & NixOS](https://nixos.org)✨ así que es tan sencillo
como:

- Compilar: `nix build`
- Entorno desarrollo: `nix develop` Ejecutar el programa:
- Servidor (Chocolate Doom):
  ```
  DOOM_CLIENT_ADDR=127.0.0.1 \
  DOOM_CLIENT_PORT=6666 \
  SDL_VIDEODRIVER=dummy \
  DOOM_SERVER_PORT=7777 \
  ./result/bin/chocolate-doom -iwad DOOM.wad
  ```
- Cliente:
  ```
  DOOM_SAT_ADDR=127.0.0.1 \
  DOOM_LISTEN_PORT=6666 \
  python3 cliente.py
  ```
**Nota importante**: Es necesario el archivo `DOOM.wad` (u otro archivo iwad) para utilizar Chocolate Doom ([más info.](https://doomwiki.org/wiki/IWAD))
