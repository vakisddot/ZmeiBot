import discord
import audioop

class SesameSink(discord.sinks.WaveSink):
    def __init__(self, ws):
        super().__init__()
        self.ws = ws
        self.state = None

    def write(self, data, user):
        mono_data = self.stereo_to_mono(data)
        resampled_data, self.state = audioop.ratecv(mono_data, 2, 1, 48000, 16000, self.state)
        
        try:
            self.ws.send_audio_data(resampled_data)
        except Exception as e:
            print(f"Error sending audio to Sesame: {e}")

    def stereo_to_mono(self, data):
        mono = bytearray()
        for i in range(0, len(data), 4):
            if i + 4 > len(data):
                break
            left = int.from_bytes(data[i:i+2], 'little', signed=True)
            right = int.from_bytes(data[i+2:i+4], 'little', signed=True)
            avg = (left + right) // 2
            mono.extend(avg.to_bytes(2, 'little', signed=True))
        return bytes(mono)

    def cleanup(self):
        self.state = None

class AudioSender:
    def __init__(self, voice_client, ws):
        self.voice_client = voice_client
        self.ws = ws
        self.sink = SesameSink(ws)

    def start(self):
        self.voice_client.start_recording(self.sink, callback=lambda: print("Started!!!!!!!!"))

    def stop(self):
        self.voice_client.stop_recording()