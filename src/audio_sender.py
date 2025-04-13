import discord
import audioop
import time
import threading

# Constants to match the desired audio format
CHUNK = 1024           # number of samples per chunk
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
        
        # Start the unified audio sending thread
        self.audio_thread = threading.Thread(target=self._process_audio_buffer)
        self.audio_thread.daemon = True
        self.audio_thread.start()

    def write(self, data, user):
        # Convert the incoming stereo audio to mono
        mono_data = self.stereo_to_mono(data)
        # Resample from Discord's typical 48000 Hz to our desired RATE (16000 Hz)
        resampled_data, self.state = audioop.ratecv(mono_data, SAMPLE_WIDTH, CHANNELS, 48000, RATE, self.state)
        
        # Update the timestamp of last received audio
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
        """Single thread that processes both real audio and silence."""
        chunk_bytes = CHUNK * SAMPLE_WIDTH
        silence_buffer = bytes(chunk_bytes)
        next_send_time = time.time()
        silence_threshold = self.chunk_interval * 2  # Time after which we consider it "silence"
        
        while self.running:
            current_time = time.time()
            
            # Time to send the next chunk?
            if current_time < next_send_time:
                time.sleep(0.001)  # Small sleep to prevent high CPU usage
                continue
            
            # Set the next time to send audio
            next_send_time = current_time + self.chunk_interval
            
            # Determine if we should send real audio or silence
            send_silence = False
            chunk_data = None
            
            # Check if we have real audio to send
            if len(self.audio_buffer) >= chunk_bytes:
                chunk_data = self.audio_buffer[:chunk_bytes]
                self.audio_buffer = self.audio_buffer[chunk_bytes:]
            else:
                # Buffer is empty or not enough data
                time_since_audio = current_time - self.last_audio_time
                if time_since_audio > silence_threshold:
                    # It's been long enough since real audio, should send silence
                    send_silence = True
            
            # If we need to send silence and didn't get real audio
            if send_silence and not chunk_data:
                chunk_data = silence_buffer
                print("SILENCE", current_time)
            elif not chunk_data:
                # No real audio but not time for silence yet, wait for more data
                continue
                
            # Send the audio data (either real or silence)
            try:
                self.ws.send_audio_data(chunk_data)
            except Exception as e:
                print(f"Error sending audio to Sesame: {e}")

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