import numpy
import sounddevice
import soundfile

from src.config import config, PATH_FILE

PATH_BEEP = str(PATH_FILE / "assets" / "sounds" / config["beep"]["name"])

beep, samplerate = soundfile.read(PATH_BEEP, dtype = "float32")
channels         = 1 if beep.ndim == 1 else beep.shape[1]

stream = sounddevice.OutputStream(samplerate = samplerate, channels = channels, dtype = "float32")
stream.start()

def create_sequence_beeps(number_beeps, interval):
    samples_interval = int(interval / 1000 * samplerate)
    samples_beep     = len(beep)
    samples_total    = samples_interval * (number_beeps - 1) + samples_beep

    buffer = numpy.zeros((samples_total, channels) if channels > 1 else samples_total, dtype = "float32")

    for i in range(number_beeps):
        start = i * samples_interval
        buffer[start:start + samples_beep] += beep

    return buffer

def play_sequence_beeps(sequence_beeps, volume = config["beep"]["volume"]):
    stream.write(sequence_beeps * volume)
