from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

voice_connections = {}

@bot.event
async def on_ready():
    print(f'Ready! Logged in as {bot.user}')

@bot.command(name='hello')
async def hello(ctx):
    await ctx.reply(f'Hello, {ctx.author.name}!')

@bot.command(name='join')
async def join(ctx):
    if not ctx.author.voice:
        await ctx.reply('You need to be in a voice channel first!')
        return
        
    voice_channel = ctx.author.voice.channel
    
    permissions = voice_channel.permissions_for(ctx.guild.me)
    if not permissions.connect or not permissions.speak:
        await ctx.reply('I need permissions to join and speak in your voice channel!')
        return
    
    try:
        voice_client = await voice_channel.connect()
        voice_connections[ctx.guild.id] = voice_client
        await ctx.reply(f'Joined {voice_channel.name}!')
    except Exception as e:
        print("Error while joining voice channel:", e)
        await ctx.reply('There was an error joining the voice channel!')

@bot.command(name='leave')
async def leave(ctx):
    if ctx.guild.id in voice_connections:
        await voice_connections[ctx.guild.id].disconnect()
        del voice_connections[ctx.guild.id]
        await ctx.reply('Left the voice channel!')
    else:
        await ctx.reply("I'm not in a voice channel!")