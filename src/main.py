import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from sesame_ai import SesameAI, SesameWebSocket, TokenManager
import time
import numpy as np
import threading
import collections
import pyaudio
import platform

load_dotenv()

# Discord bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)
voice_connections = {}

# Initialize Sesame authentication and websocket
api_client = SesameAI()
token_manager = TokenManager(api_client, token_file="token.json")
id_token = token_manager.get_valid_token()

character = "Maya"
ws = SesameWebSocket(id_token=id_token, character=character)

def on_connect():
    print("Connected to SesameAI!")

def on_disconnect():
    print("Disconnected from SesameAI")

ws.set_connect_callback(on_connect)
ws.set_disconnect_callback(on_disconnect)

# Audio configuration for Discord (output side)
TARGET_SAMPLE_RATE = 48000  # Discord expects 48 kHz PCM
FRAME_DURATION_SEC = 0.02   # 20 ms frames
CHANNELS = 2                # Stereo
SAMPLE_WIDTH = 2            # 16-bit (2 bytes per sample)
TARGET_FRAME_SAMPLES = int(TARGET_SAMPLE_RATE * FRAME_DURATION_SEC)  # 960 samples per channel
TARGET_FRAME_BYTES = TARGET_FRAME_SAMPLES * CHANNELS * SAMPLE_WIDTH  # = 3840 bytes

def process_audio_chunk(audio_chunk, src_rate):
    """
    Resamples and converts mono PCM audio from the source sample rate to 48 kHz stereo.
    """
    samples = np.frombuffer(audio_chunk, dtype=np.int16)
    
    if src_rate != TARGET_SAMPLE_RATE:
        new_length = int(len(samples) * TARGET_SAMPLE_RATE / src_rate)
        original_indices = np.arange(len(samples))
        target_indices = np.linspace(0, len(samples), new_length, endpoint=False)
        resampled = np.interp(target_indices, original_indices, samples).astype(np.int16)
    else:
        resampled = samples

    # Assume the incoming audio is mono; convert to stereo.
    stereo = np.repeat(resampled, 2)
    required_samples = TARGET_FRAME_SAMPLES * CHANNELS  # 1920 samples total
    if len(stereo) < required_samples:
        stereo = np.pad(stereo, (0, required_samples - len(stereo)))
    elif len(stereo) > required_samples:
        stereo = stereo[:required_samples]
    return stereo.tobytes()

class SesameAudioSource(discord.AudioSource):
    """
    Custom AudioSource for Discord output that buffers incoming audio from Sesame.
    """
    def __init__(self, ws):
        self.ws = ws
        self.src_rate = getattr(ws, "server_sample_rate", 16000)
        self.buffer = collections.deque()
        self.buffer_lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self.buffer_audio)
        self.thread.daemon = True
        self.thread.start()
        print("SesameAudioSource initialized with source sample rate:", self.src_rate)

    def buffer_audio(self):
        while self.running:
            audio_chunk = self.ws.get_next_audio_chunk(timeout=0.01)

            if audio_chunk is not None:
                with self.buffer_lock:
                    self.buffer.append(audio_chunk)
            else:
                time.sleep(0.01)

    def read(self):
        with self.buffer_lock:
            if self.buffer:
                audio_chunk = self.buffer.popleft()
            else:
                audio_chunk = None
        if audio_chunk is None:
            return b'\x00' * TARGET_FRAME_BYTES
        processed = process_audio_chunk(audio_chunk, self.src_rate)
        return processed

    def is_opus(self):
        return False

    def cleanup(self):
        self.running = False
        self.thread.join()

# --- Audio Input (Sending to Sesame) ---

# Input audio configuration for recording (assumed matching Sesame input requirements)
INPUT_SAMPLE_RATE = 16000  # For example, Sesame may expect 16 kHz
INPUT_CHANNELS = 1         # Mono capture
INPUT_FORMAT = pyaudio.paInt16
CHUNK = 1024               # Number of frames per buffer

# Optionally, set device indexes via environment variables.
MIC_DEVICE_INDEX = os.getenv("MIC_DEVICE_INDEX")
LOOPBACK_DEVICE_INDEX = os.getenv("LOOPBACK_DEVICE_INDEX")
if MIC_DEVICE_INDEX is not None:
    MIC_DEVICE_INDEX = int(MIC_DEVICE_INDEX)
if LOOPBACK_DEVICE_INDEX is not None:
    LOOPBACK_DEVICE_INDEX = int(LOOPBACK_DEVICE_INDEX)

p = pyaudio.PyAudio()

def open_input_stream(device_index):
    try:
        stream = p.open(format=INPUT_FORMAT,
                        channels=INPUT_CHANNELS,
                        rate=INPUT_SAMPLE_RATE,
                        input=True,
                        frames_per_buffer=CHUNK,
                        input_device_index=device_index)
        print(f"Opened input stream on device index {device_index}")
        return stream
    except Exception as e:
        print(f"Could not open input stream for device {device_index}: {e}")
        return None

# Open the mic stream (if available)
mic_stream = open_input_stream(MIC_DEVICE_INDEX) if MIC_DEVICE_INDEX is not None else open_input_stream(None)
# Try to open the loopback (system output) stream if provided.
loopback_stream = open_input_stream(LOOPBACK_DEVICE_INDEX) if LOOPBACK_DEVICE_INDEX is not None else None

def mix_audio(data1, data2):
    """
    Mix two PCM audio chunks (bytes) by converting to NumPy arrays, summing with clipping,
    and returning combined bytes.
    If one of the streams is None, it is considered as silence.
    """
    # Convert bytes to int16 numpy arrays
    arr1 = np.frombuffer(data1, dtype=np.int16) if data1 is not None else np.zeros(CHUNK, dtype=np.int16)
    arr2 = np.frombuffer(data2, dtype=np.int16) if data2 is not None else np.zeros(CHUNK, dtype=np.int16)
    # Ensure both arrays are the same length; pad if necessary.
    if len(arr1) < CHUNK:
        arr1 = np.pad(arr1, (0, CHUNK - len(arr1)))
    if len(arr2) < CHUNK:
        arr2 = np.pad(arr2, (0, CHUNK - len(arr2)))
    # Mix by summing and then clipping to int16 range.
    mixed = arr1.astype(np.int32) + arr2.astype(np.int32)
    mixed = np.clip(mixed, -32768, 32767).astype(np.int16)
    return mixed.tobytes()

def record_and_send():
    """
    Continuously captures audio from the mic and optionally system output,
    mixes the channels, and sends the resulting PCM data to Sesame.
    """
    while True:
        try:
            mic_data = mic_stream.read(CHUNK, exception_on_overflow=False) if mic_stream is not None else None
        except Exception as e:
            print("Error reading mic:", e)
            mic_data = None
        try:
            loopback_data = loopback_stream.read(CHUNK, exception_on_overflow=False) if loopback_stream is not None else None
        except Exception as e:
            print("Error reading loopback:", e)
            loopback_data = None

        # Mix the two audio sources (if loopback_data is None, only mic_data is used)
        mixed_data = mix_audio(mic_data, loopback_data)

        # Send the mixed audio to Sesame.
        try:
            ws.send_audio_data(mixed_data)
        except Exception as e:
            print("Error sending audio chunk to Sesame:", e)
        # Sleep to roughly match the real-time capture rate.
        time.sleep(CHUNK / INPUT_SAMPLE_RATE)

# Start the input capture thread.
input_thread = threading.Thread(target=record_and_send, daemon=True)
input_thread.start()

# --- Discord Bot Commands and Events ---

@bot.event
async def on_ready():
    print(f"Ready! Logged in as {bot.user}")

@bot.command(name='hello')
async def hello(ctx):
    await ctx.reply(f"Hello, {ctx.author.name}!")

@bot.command(name='join')
async def join(ctx):
    if not ctx.author.voice:
        await ctx.reply("You need to be in a voice channel first!")
        return
    
    voice_channel = ctx.author.voice.channel
    permissions = voice_channel.permissions_for(ctx.guild.me)

    if not permissions.connect or not permissions.speak:
        await ctx.reply("I need permissions to join and speak in your voice channel!")
        return
    
    try:
        voice_client = await voice_channel.connect()
        voice_connections[ctx.guild.id] = voice_client
        ws.connect()
        sesame_audio = SesameAudioSource(ws)
        voice_client.play(sesame_audio)
        await ctx.reply(f"Joined {voice_channel.name} and streaming audio from Sesame!")
    except Exception as e:
        print("Error joining voice channel:", e)
        await ctx.reply("There was an error joining the voice channel!")

@bot.command(name='leave')
async def leave(ctx):
    if ctx.guild.id in voice_connections:
        vc = voice_connections[ctx.guild.id]
        await vc.disconnect()
        del voice_connections[ctx.guild.id]
        ws.disconnect()
        await ctx.reply("Left the voice channel!")
    else:
        await ctx.reply("I'm not in a voice channel!")

bot.run(os.getenv("DISCORD_TOKEN"))