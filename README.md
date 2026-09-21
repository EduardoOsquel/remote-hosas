# HOSAS + PyQt6 Joystick Bridge

Este proyecto ofrece una base visual para conectar un joystick local y capturar su estado en un paquete serializable que puedes enviar por HOSAS/Tailscale a otro equipo.

## Requisitos

- Python 3.10+
- PyQt6
- pygame

## Instalación

```bash
pip install PyQt6 pygame pytest
```

## Ejecutar la interfaz

```bash
python app.py
```

## Estructura

- `app.py`: interfaz gráfica principal.
- `joystick_bridge.py`: modelo del estado del joystick y el paquete de datos.
- `tests/test_joystick_bridge.py`: pruebas básicas de serialización.

## Qué hace realmente

1. Detecta los joysticks conectados.
2. Permite seleccionar uno.
3. Lee ejes, botones y hats cada 20 ms.
4. Genera un paquete Python (`dict`) listo para enviarse por tu canal de red con HOSAS/Tailscale.

## Siguiente paso

En el equipo remoto, puedes leer ese paquete y reproducirlo en un joystick virtual o reenviarlo a otra aplicación. La lógica de red exacta depende de cómo tengas montado HOSAS en tu red.
