import threading
import time

INPUT_SAMPLE_RATE = 16000  # e.g., Sesame expects 16 kHz input.
CHUNK = 1024  # Number of frames to simulate per send.

class AudioSender:
    def __init__(self, ws):
        self.ws = ws

    def send_audio(self):
        """
        A stub function that sends example (silent) audio data to Sesame in a loop.
        Replace this with your actual audio capture or processing as needed.
        """
        # Create an example audio chunk consisting of zeros.
        # For example, 3200 bytes corresponds to 1600 samples of 16-bit audio.
        example_audio = b'\x00' * 3200
        
        while True:
            try:
                self.ws.send_audio_data(example_audio)
            except Exception as e:
                print("Error sending audio chunk to Sesame:", e)

            time.sleep(CHUNK / INPUT_SAMPLE_RATE)

    def start(self):
        input_thread = threading.Thread(target=self.send_audio, daemon=True)
        input_thread.start()