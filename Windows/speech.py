"""AssemblyAI streaming; network and audio never run on the UI thread."""
import json
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import sounddevice as sd
import websocket


class Transcript:
    def __init__(self):
        self.turns = {}

    def update(self, event):
        # Formatted finals replace earlier versions of the same turn.
        text = event.get("transcript", "").strip()
        if text:
            self.turns[event["turn_order"]] = text
        return self.text

    @property
    def text(self):
        return " ".join(self.turns[key] for key in sorted(self.turns))


class Session:
    def __init__(self, api_key, device, events):
        self.api_key = api_key
        self.device = device
        self.events = events
        self.stop_requested = threading.Event()
        self.finished = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_requested.set()

    def token(self):
        request = urllib.request.Request(
            "https://streaming.assemblyai.com/v3/token?expires_in_seconds=600",
            headers={"Authorization": self.api_key})
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                return json.load(response)["token"]
        except urllib.error.HTTPError as error:
            # Don't expose the API key, token or request URL in UI/logs.
            if error.code in (401, 403):
                raise RuntimeError("AssemblyAI rechazó la clave API. Revísala en Ajustes.") from None
            raise RuntimeError(f"AssemblyAI no está disponible (HTTP {error.code}).") from None

    def run(self):
        audio = queue.Queue(maxsize=100)
        transcript = Transcript()
        terminated = threading.Event()
        receiver_done = threading.Event()
        errors = queue.Queue()
        socket = None
        receiver = None
        stream = None
        clean_termination = False
        audio_received = threading.Event()

        def capture(data, frames, timing, status):
            audio_received.set()
            samples = memoryview(data).cast("h")
            self.events.put(("level", max((abs(value) for value in samples[::64]), default=0) / 32768))
            if status:
                errors.put("El micrófono perdió audio. Prueba otro dispositivo.")
                self.stop()
            try:
                audio.put_nowait(bytes(data))
            except queue.Full:
                errors.put("La conexión no puede enviar el audio a tiempo. Vuelve a intentarlo.")
                self.stop()

        def receive():
            try:
                while not receiver_done.is_set():
                    try:
                        raw = socket.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not raw:
                        raise RuntimeError("AssemblyAI cerró la conexión antes de finalizar.")
                    event = json.loads(raw)
                    if event["type"] == "Turn":
                        self.events.put(("transcript", transcript.update(event)))
                    elif event["type"] == "Termination":
                        terminated.set()
                        break
                    elif event["type"] == "Error":
                        raise RuntimeError("AssemblyAI: " + str(event.get("error", "Error de transcripción")))
            except Exception as error:
                if not receiver_done.is_set():
                    errors.put(str(error))
                    self.stop()
            finally:
                receiver_done.set()

        try:
            # Check hardware before opening a billable session. Capture at its
            # native rate so 48 kHz microphones don't require resampling.
            try:
                info = sd.query_devices(self.device, "input")
                rate = int(info["default_samplerate"])
                if not 8000 <= rate <= 96000:
                    raise RuntimeError("Selecciona un micrófono con frecuencia entre 8 y 96 kHz.")
                stream = sd.RawInputStream(device=self.device, samplerate=rate,
                    channels=1, dtype="int16", blocksize=rate // 20, callback=capture)
            except sd.PortAudioError:
                raise RuntimeError("No se puede abrir el micrófono. Conecta uno, revisa los permisos de Windows y selecciónalo en Ajustes.") from None
            if self.stop_requested.is_set():
                return
            # Some Windows drivers advertise disconnected endpoints. Verify
            # actual audio delivery before opening a paid cloud connection.
            stream.start()
            audio_deadline = time.monotonic() + 2
            while not audio_received.wait(0.05):
                if self.stop_requested.is_set():
                    return
                if not stream.active or time.monotonic() >= audio_deadline:
                    raise RuntimeError("El micrófono no entrega audio. Revisa la conexión y los permisos, o selecciona otro en Ajustes.")
            stream.stop()
            while not audio.empty():
                audio.get_nowait()
            if self.stop_requested.is_set():
                return
            token = self.token()
            if self.stop_requested.is_set():
                return
            query = urllib.parse.urlencode({"sample_rate": rate, "encoding": "pcm_s16le",
                "speech_model": "universal-3-6-pro", "token": token})
            try:
                socket = websocket.create_connection(
                    "wss://streaming.assemblyai.com/v3/ws?" + query,
                    timeout=12, enable_multithread=True)
            except Exception:
                raise RuntimeError("No se pudo conectar con AssemblyAI. Revisa la red y la clave.") from None
            begin = json.loads(socket.recv())
            if begin.get("type") != "Begin":
                raise RuntimeError("AssemblyAI no pudo iniciar la sesión: " + str(begin.get("error", "Respuesta inesperada")))
            socket.settimeout(0.5)
            receiver = threading.Thread(target=receive, daemon=True)
            receiver.start()
            if not self.stop_requested.is_set():
                stream.start()
                self.events.put(("listening", None))
            deadline = time.monotonic() + 540  # Below the temporary token lifetime.
            while not self.stop_requested.is_set():
                if time.monotonic() >= deadline:
                    self.events.put(("stopping", "Límite de 9 minutos. Finalizando…"))
                    self.stop()
                    break
                if not stream.active:
                    raise RuntimeError("El micrófono se desconectó durante la grabación.")
                try:
                    socket.send_binary(audio.get(timeout=0.1))
                except queue.Empty:
                    continue
            stream.stop()
            while not audio.empty():
                socket.send_binary(audio.get_nowait())
            socket.send(json.dumps({"type": "ForceEndpoint"}))
            socket.send(json.dumps({"type": "Terminate"}))
            end = time.monotonic() + 10
            while not terminated.is_set() and not receiver_done.is_set() and time.monotonic() < end:
                terminated.wait(0.1)
            if not terminated.is_set() and errors.empty():
                errors.put("La sesión no confirmó el final. El texto parcial queda en el historial; revísalo antes de copiar.")
            clean_termination = terminated.is_set()
        except Exception as error:
            errors.put(str(error))
        finally:
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
            if socket is not None:
                if not clean_termination:
                    try:
                        socket.send(json.dumps({"type": "Terminate"}))
                    except Exception:
                        pass
                receiver_done.set()
                try:
                    socket.close(timeout=1)
                except Exception:
                    pass
            if receiver is not None:
                receiver.join(timeout=2)
            error = errors.get() if not errors.empty() else None
            self.events.put(("finished", (transcript.text, error)))
            self.finished.set()
