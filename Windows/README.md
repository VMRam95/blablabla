# Blablabla para Windows 11

Cliente nativo Qt de escritorio, con el diseño del cliente Swift/macOS:
barra lateral plegable, logo original, paleta oscura, tarjetas redondeadas,
interruptores, teclas del atajo y páginas **Settings**, **Transcripts** y **Permissions**.
La rama de trabajo es `feat/windows-local`; el código original de macOS permanece
en `Sources/`. No requiere Xcode, Electron ni un servidor local.

![Interfaz de Blablabla en Windows](docs/windows-settings.png)

## Ejecutar

Si ya se ha generado el ejecutable, abre **`Windows/dist/Blablabla.exe`**.
Es un ejecutable local sin instalador ni firma digital; no se publica como una
release oficial. Incluye Python y las dependencias.

Para ejecutar desde código fuente:

1. Instala [Python 3.11 o superior](https://www.python.org/downloads/windows/),
   marcando **Add Python to PATH**. En este equipo ya está instalado.
2. Haz doble clic en **`Windows/run.cmd`**. Crea un entorno aislado en `Windows/.venv`
   e instala las dependencias. La primera ejecución necesita Internet.
3. En **Settings**, introduce tu [clave API de AssemblyAI](https://www.assemblyai.com/dashboard/signup).
   Los ajustes se guardan automáticamente. **Done** oculta la clave después de editarla.
   Puedes seleccionar un micrófono en **Microphone** o usar **System Default**.
4. En Windows, permite el micrófono para aplicaciones de escritorio en
   **Configuración → Privacidad y seguridad → Micrófono**.
5. Pon el cursor en un campo de texto de otra aplicación. Pulsa
   **Ctrl + Alt + Espacio**, espera al estado **Escuchando**, habla y pulsa
   el mismo atajo para detener. El texto se inserta cuando termina la transcripción.

También puedes usar **Start dictation / Stop dictation** en la ventana o hacer
clic en la pequeña onda flotante sobre la barra de tareas.
El botón utiliza como destino la última ventana externa que tuvo el foco mientras
Blablabla estaba abierta. Si no hay destino, conserva el texto para copiarlo.

```powershell
# Alternativa al doble clic, desde la raíz del repositorio
powershell -NoProfile -ExecutionPolicy Bypass -File .\Windows\run.ps1
```

### Abrir desde el escritorio o el menú Inicio

Después de generar el EXE, puedes abrirlo directamente con CAS cerrado.
Para crear un acceso, haz clic derecho sobre `Windows/dist/Blablabla.exe`,
elige **Mostrar más opciones → Enviar a → Escritorio (crear acceso directo)**
y renómbralo **Blablabla**. El acceso debe apuntar al EXE, sin argumentos.

Para encontrarlo desde Inicio, copia ese acceso a la carpeta que abre
**Win + R → `shell:programs`**. También puedes anclarlo a la barra de tareas
desde su icono mientras está abierto. Conserva el EXE en la ubicación a la que
apunta el acceso; puedes copiarlo antes a una carpeta permanente de tu usuario.

## Qué incluye

- Grabación de micrófono mono PCM de 16 bits, a la frecuencia nativa del dispositivo.
- Transcripción en directo mediante AssemblyAI Universal Streaming v3,
  modelo `universal-3-6-pro`, con idiomas detectados automáticamente.
- Atajo global configurable en **Shortcut → Record**, incluso con la ventana minimizada.
- Inserción Unicode mediante `SendInput`, sin modificar el portapapeles.
- Modos **Clipboard only**, **Also copy to clipboard** y copia manual de transcripciones.
- Historial local y clave cifrada con Windows DPAPI para el usuario actual.
- Recuperación de texto parcial en el historial cuando falla la conexión.
- Indicador flotante con la onda y el gradiente originales, animado con el nivel del micrófono.
- Bandeja del sistema, inicio al iniciar sesión opcional, sonidos de Windows y uso local.
- Historial por tarjetas, búsqueda y paginación como en macOS.

El audio va directamente a AssemblyAI y requiere Internet y una cuenta con acceso
al servicio. No es transcripción offline: «local» se refiere a ejecutar la aplicación
en tu PC. No guarda archivos de audio ni incorpora telemetría.

Los datos se guardan en `%LOCALAPPDATA%\Blablabla\windows.json`.
La clave está cifrada; los textos del historial no. No añadas este archivo al repositorio.

## Límites de esta primera versión

- El atajo funciona como interruptor; todavía no incluye mantener pulsado,
  doble toque ni tecla Fn.
- Cerrar la ventana termina la aplicación y cierra la sesión activa. Minimizarla
  mantiene disponible el atajo. Si activas **Minimize to tray**, cerrar o minimizar
  oculta la ventana y el dictado sigue disponible desde la bandeja; **Quit Blablabla**
  cierra la app. Cada grabación dura como máximo nueve minutos.
- Si cambias a una ventana distinta mientras dicta, no roba su foco: guarda el
  resultado en el historial. Si vuelves a la ventana de Blablabla, puede restaurar
  el foco del destino original.
- Windows bloquea la inserción en apps ejecutadas con privilegios superiores.
  Usa copia manual en esos casos. Algunos campos, juegos o terminales pueden
  no aceptar eventos Unicode. El historial conserva el texto; si una inserción
  fue parcial, revisa el destino antes de copiar el texto completo.
- Si otra aplicación usa tu atajo, puedes usar el botón o grabar otra combinación.
- La lista de micrófonos se actualiza con **Microphone → Refresh**. Si desenchufas
  el micrófono durante una sesión, revisa el texto parcial y vuelve a empezar.
- Los permisos, sonidos y barra de título son los de Windows; no se imitan permisos
  exclusivos de macOS. **Updates** enlaza al proyecto; aún no hay actualizador Windows.
- **Launch at login** modifica únicamente el valor `Blablabla` en la clave de inicio
  del usuario actual de Windows. Está desactivado por defecto y se elimina al desactivarlo.

## Generar un ejecutable

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Windows\build.ps1
```

Genera `Windows/dist/Blablabla.exe` con PyInstaller. El entorno, los archivos de
compilación y el ejecutable están excluidos de Git. Se genera como carpeta (EXE +
`_internal`) para que arranque al instante; para llevarlo a otro Windows 11 de 64
bits copia la carpeta `dist` entera, sin necesidad de instalar Python.

## Verificación

Cierra otras instancias de Blablabla antes de ejecutar las pruebas, para que el
atajo global esté libre. La instalación de Python para pruebas debe incluir
Tcl/Tk: se usa un campo de texto real para comprobar la inserción Unicode.

```powershell
.\Windows\.venv\Scripts\python.exe -m unittest discover -s Windows -p test_windows.py -v
```

Las pruebas verifican cierre de sesión y conservación de finales tardíos,
reemplazo de turnos formateados, errores y cancelación durante la conexión,
cifrado DPAPI, registro del atajo, inserción Unicode real en un campo de texto,
persistencia del historial, navegación Qt, búsqueda/copia, clave enmascarada, atajo
real recibido por Qt, indicador, inicio al login simulado y reapertura desde bandeja.
La prueba de inserción abre
brevemente una ventana de prueba. No usan una clave API real ni envían audio a la nube.

La validación completa de dictado requiere probar con tu micrófono y una clave API:
una frase corta en español, varias frases con pausas, copiar desde el historial,
dictado en otra aplicación con la ventana minimizada y parada/cierre durante una sesión.

En este equipo (Windows 11 Pro, 10/10/2026) se ha generado el EXE y comprobado
su arranque. Se ha sustituido la interfaz inicial por el diseño original de macOS
usando Qt y comprobado mediante capturas renderizadas. Pasan las 21 pruebas.
Windows no tiene micrófono predeterminado y
el endpoint Realtek de micrófono anunciado por el controlador no entrega buffers
de audio. Hay que conectar/habilitar una entrada funcional y seleccionarla.
La aplicación comprueba que recibe audio antes de abrir la sesión de AssemblyAI.
El dictado cloud sigue pendiente de prueba con micrófono y clave API reales.

Referencias: [protocolo AssemblyAI](https://www.assemblyai.com/docs/streaming/message-sequence),
[API y modelos](https://www.assemblyai.com/docs/streaming/api-spec/streaming-websocket),
[captura de audio](https://python-sounddevice.readthedocs.io/en/latest/api/raw-streams.html),
[inserción de Windows](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput).
