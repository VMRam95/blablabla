"""Rebuild the original short UI tones using only Python's standard library."""
import math
from pathlib import Path
import struct
import wave


TONES = {
    "soft-tap": [(0, .10, 660, 0)],
    "glass": [(0, .18, 1320, 0), (0, .18, 1980, 0)],
    "bloom": [(0, .22, 523, 0), (.035, .20, 659, 0), (.07, .18, 784, 0)],
    "rise": [(0, .17, 440, 3100)],
    "fall": [(0, .17, 960, -3100)],
    "pulse": [(0, .09, 740, 0), (.10, .10, 740, 0)],
    "two-notes": [(0, .12, 587, 0), (.08, .14, 880, 0)],
    "air": [(0, .22, 1108, 0), (.025, .20, 1661, 0)],
}


def generate(destination=None):
    destination = destination or Path(__file__).resolve().parent.parent / "Resources" / "Sounds"
    destination.mkdir(parents=True, exist_ok=True)
    rate = 44100
    for name, notes in TONES.items():
        duration = max(start + length for start, length, _, _ in notes)
        frames = []
        for index in range(math.ceil(duration * rate) + 1):
            now = index / rate
            sample = 0.0
            for start, length, frequency, slope in notes:
                t = now - start
                if 0 <= t < length:
                    envelope = min(1, t / .008) * math.exp(-t / (length * .3)) * (1 - (t/length)**3)
                    sample += envelope * math.sin(2 * math.pi * (frequency*t + .5*slope*t*t))
            frames.append(round(32767 * .16 * sample / len(notes)))
        frames[0] = frames[-1] = 0
        with wave.open(str(destination / (name + ".wav")), "wb") as output:
            output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
            output.writeframes(struct.pack("<" + "h" * len(frames), *frames))


if __name__ == "__main__":
    generate()
