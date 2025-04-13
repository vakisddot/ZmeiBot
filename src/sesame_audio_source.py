import time
import threading
import numpy as np
import discord

# ----- Audio Output Configuration for Discord -----
TARGET_SAMPLE_RATE = 48000  # Discord expects 48 kHz PCM
FRAME_DURATION_SEC = 0.02   # 20 ms frames
CHANNELS = 2                # Stereo
SAMPLE_WIDTH = 2            # 16-bit (2 bytes per sample)
TARGET_FRAME_SAMPLES = int(TARGET_SAMPLE_RATE * FRAME_DURATION_SEC)  # 960 samples per channel
TARGET_FRAME_BYTES = TARGET_FRAME_SAMPLES * CHANNELS * SAMPLE_WIDTH    # 3840 bytes

class SesameAudioSource(discord.AudioSource):
    """
    Custom AudioSource that buffers incoming audio chunks from Sesame,
    accumulates them until at least one complete frame is available,
    then outputs exactly 20ms of resampled audio per Discord's expectations.
    """
    def __init__(self, ws):
        self.ws = ws
        # The source sample rate from Sesame (defaulting to 16000 Hz)
        self.src_rate = getattr(ws, "server_sample_rate", 16000)
        # Calculate how many source samples constitute 20ms of audio.
        self.input_frame_samples = int(self.src_rate * FRAME_DURATION_SEC)  # e.g. 320 at 16kHz
        # Thread-safe accumulator for incoming samples as a 1D NumPy array (int16)
        self.sample_buffer = np.empty((0,), dtype=np.int16)
        self.buffer_lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self.buffer_audio, daemon=True)
        self.thread.start()
        print("SesameAudioSource initialized with source sample rate:", self.src_rate)
        print("Expecting", self.input_frame_samples, "samples per frame from input.")

    def buffer_audio(self):
        """
        Continuously reads audio chunks from Sesame and appends them to the accumulator.
        Each chunk is converted into an int16 NumPy array and concatenated.
        """
        while self.running:
            # Try to get the next chunk (adjust timeout as needed)
            audio_chunk = self.ws.get_next_audio_chunk(timeout=0.01)
            if audio_chunk is not None:
                # Convert the received bytes to int16 samples.
                try:
                    chunk_samples = np.frombuffer(audio_chunk, dtype=np.int16)
                except Exception as e:
                    print("Error converting audio chunk:", e)
                    continue
                with self.buffer_lock:
                    self.sample_buffer = np.concatenate((self.sample_buffer, chunk_samples))
            else:
                time.sleep(0.005)

    def read(self):
        """
        Called by Discord to retrieve 20ms of audio.
        If enough input samples are available, extract them, resample, convert to stereo,
        and output exactly TARGET_FRAME_BYTES bytes. Otherwise, output silence.
        """
        with self.buffer_lock:
            available_samples = len(self.sample_buffer)
            if available_samples >= self.input_frame_samples:
                # Extract exactly one frame worth of input samples.
                input_frame = self.sample_buffer[:self.input_frame_samples]
                self.sample_buffer = self.sample_buffer[self.input_frame_samples:]
            else:
                input_frame = None

        if input_frame is None:
            # Not enough data: output silence.
            return b'\x00' * TARGET_FRAME_BYTES

        # Resample the input frame to match Discord's target sample rate.
        resampled = self.resample_mono(input_frame, self.src_rate, TARGET_SAMPLE_RATE)
        # After resampling, we expect the length to be close to TARGET_FRAME_SAMPLES.
        # Enforce the exact frame size: pad with zeros or trim if needed.
        if len(resampled) < TARGET_FRAME_SAMPLES:
            resampled = np.pad(resampled, (0, TARGET_FRAME_SAMPLES - len(resampled)))
        elif len(resampled) > TARGET_FRAME_SAMPLES:
            resampled = resampled[:TARGET_FRAME_SAMPLES]

        # Convert mono to stereo by duplicating each sample.
        stereo = np.repeat(resampled, 2)
        # Ensure the stereo buffer has exactly TARGET_FRAME_BYTES bytes.
        if stereo.nbytes < TARGET_FRAME_BYTES:
            stereo = np.pad(stereo, (0, (TARGET_FRAME_BYTES // SAMPLE_WIDTH - len(stereo))))
        elif stereo.nbytes > TARGET_FRAME_BYTES:
            stereo = stereo[:TARGET_FRAME_BYTES // SAMPLE_WIDTH]
        return stereo.tobytes()

    def is_opus(self):
        return False

    def cleanup(self):
        self.running = False
        self.thread.join()

    def resample_mono(self, samples, src_rate, target_rate):
        """
        Resample a 1D NumPy array of int16 samples (mono) from src_rate to target_rate using linear interpolation.
        """
        if src_rate == target_rate:
            return samples
        old_indices = np.arange(len(samples))
        new_length = int(len(samples) * target_rate / src_rate)
        new_indices = np.linspace(0, len(samples), new_length, endpoint=False)
        return np.interp(new_indices, old_indices, samples).astype(np.int16)