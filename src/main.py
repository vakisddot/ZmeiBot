import os
import time
import threading
from dotenv import load_dotenv
import discord
from discord.ext import commands
from sesame_ai import SesameAI, SesameWebSocket, TokenManager
from sesame_audio_source import SesameAudioSource

load_dotenv()

# Discord Bot Configuration
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)
voice_connections = {}

# Sesame Websocket Setup
token_manager = TokenManager(SesameAI(), token_file="temp-sesame-token.json")
id_token = token_manager.get_valid_token(force_new=True)

# Set your preferred character for Sesame
character = "Maya"
ws = SesameWebSocket(id_token=id_token, character=character)

ws.set_connect_callback(lambda: print("Connected to SesameAI!"))
ws.set_disconnect_callback(lambda: print("Disconnected from SesameAI"))

# Example settings for sending audio to Sesame.
INPUT_SAMPLE_RATE = 16000  # e.g., Sesame expects 16 kHz input.
CHUNK = 1024  # Number of frames to simulate per send.

def send_audio():
    """
    A stub function that sends example (silent) audio data to Sesame in a loop.
    Replace this with your actual audio capture or processing as needed.
    """
    # Create an example audio chunk consisting of zeros.
    # For example, 3200 bytes corresponds to 1600 samples of 16-bit audio.
    example_audio = b'\x00' * 3200
    while True:
        try:
            ws.send_audio_data(example_audio)
        except Exception as e:
            print("Error sending audio chunk to Sesame:", e)
        time.sleep(CHUNK / INPUT_SAMPLE_RATE)

# ----- Discord Bot Commands and Events -----

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
        # Connect to the voice channel.
        voice_client = await voice_channel.connect()
        voice_connections[ctx.guild.id] = voice_client

        # Connect to Sesame and start its stream.
        ws.connect()

        # Create our custom Sesame audio source and play it.
        sesame_audio = SesameAudioSource(ws)
        voice_client.play(sesame_audio)
        print("Started streaming Sesame output in the voice channel.")

        # Start the sending thread (if using bidirectional audio).
        input_thread = threading.Thread(target=send_audio, daemon=True)
        input_thread.start()

        await ctx.reply(f"Joined {voice_channel.name}!")
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
