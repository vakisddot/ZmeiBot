import discord
import audioop
import time
import threading
from pydub import AudioSegment

# Constants to match the desired audio format
CHUNK = 320            # number of samples per chunk
SAMPLE_WIDTH = 2       # 16-bit audio => 2 bytes per sample
CHANNELS = 1           # mono audio
RATE = 16000           # sample rate in Hz

class SesameSink(discord.sinks.WaveSink):
    def __init__(self, ws):
        super().__init__()
        self.ws = ws
        self.state = None
        self.last_audio_time = time.time()
        # Time between audio chunks at 16kHz
        self.chunk_interval = CHUNK / RATE  # seconds
        self.running = True
        self.audio_buffer = bytearray()
        self.silence_threshold = 0.1
        
        # Start the unified audio sending thread
        self.audio_thread = threading.Thread(target=self._process_audio_buffer)
        self.audio_thread.daemon = True
        self.audio_thread.start()

    def write(self, data, user):
        # Convert stereo to mono
        mono_data = self.stereo_to_mono(data)
        # Resample using pydub (more efficient)
        audio = AudioSegment(
            mono_data,
            sample_width=SAMPLE_WIDTH,
            frame_rate=48000,
            channels=1
        )
        audio = audio.set_frame_rate(RATE)
        resampled_data = audio.raw_data
        
        self.last_audio_time = time.time()
        self.audio_buffer.extend(resampled_data)


    def stereo_to_mono(self, data):
        mono = bytearray()
        # Process 4 bytes at a time (2 bytes per channel)
        for i in range(0, len(data), 4):
            if i + 4 > len(data):
                break
            left = int.from_bytes(data[i:i+2], 'little', signed=True)
            right = int.from_bytes(data[i+2:i+4], 'little', signed=True)
            # Take the average of the left and right channels
            avg = (left + right) // 2
            mono.extend(avg.to_bytes(2, 'little', signed=True))
        return bytes(mono)

    def _process_audio_buffer(self):
        chunk_bytes = CHUNK * SAMPLE_WIDTH
        silence_buffer = bytes(chunk_bytes)
        
        while self.running:
            # Always send a chunk every CHUNK/RATE seconds (e.g., 20ms)
            next_send_time = time.time() + self.chunk_interval
            
            # Prioritize real audio data
            if len(self.audio_buffer) >= chunk_bytes:
                chunk_data = self.audio_buffer[:chunk_bytes]
                self.audio_buffer = self.audio_buffer[chunk_bytes:]
            else:
                # Send silence if no real audio is available
                chunk_data = silence_buffer
            
            try:
                self.ws.send_audio_data(chunk_data)
            except Exception as e:
                print(f"Error sending audio: {e}")
            
            # Sleep precisely to maintain timing
            sleep_time = next_send_time - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)

    def cleanup(self):
        self.running = False
        if self.audio_thread.is_alive():
            self.audio_thread.join(timeout=1.0)
        self.state = None

class AudioSender:
    def __init__(self, voice_client, ws):
        self.voice_client = voice_client
        self.ws = ws
        self.sink = SesameSink(ws)

    def start(self):
        self.voice_client.start_recording(self.sink, callback=lambda: print("Started recording and streaming audio"))

    def stop(self):
        self.voice_client.stop_recording()
        self.sink.cleanup()