import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from sesame_ai import SesameAI, SesameWebSocket, TokenManager
from audio_sender import AudioSender
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
ws: SesameWebSocket = None

#  Discord Bot Commands and Events
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
        # Create a new Sesame Websocket
        ws = SesameWebSocket(id_token=id_token, character=character)
        ws.set_connect_callback(lambda: print("Connected to SesameAI!"))
        ws.set_disconnect_callback(lambda: print("Disconnected from SesameAI"))

        # Connect to the voice channel.
        voice_client = await voice_channel.connect()
        voice_connections[ctx.guild.id] = voice_client

        # Connect to Sesame and start its stream.
        ws.connect()

        # Create our custom Sesame audio source and play it.
        sesame_audio = SesameAudioSource(ws)
        voice_client.play(sesame_audio)
        print("Started streaming Sesame output in the voice channel.")

        audio_sender = AudioSender(ws)
        audio_sender.start()

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

@bot.command(name='miles')
async def miles(ctx):
    global character

    if not ctx.guild.id in voice_connections:
        character = "Miles"
        await ctx.reply("Switched to Miles!")
    else:
        await ctx.reply("Cannot switch character while in a voice channel!")

@bot.command(name='maya')
async def miles(ctx):
    global character

    if not ctx.guild.id in voice_connections:
        character = "Maya"
        await ctx.reply("Switched to Maya!")
    else:
        await ctx.reply("Cannot switch character while in a voice channel!")

bot.run(os.getenv("DISCORD_TOKEN"))
