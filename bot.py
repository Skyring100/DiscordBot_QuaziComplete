import discord
from discord.ext import commands
import dotenv
import os
import yt_dlp
from discord import FFmpegPCMAudio


bot_has_pin_commands: bool = False
try:
    import pin_functions
    bot_has_pin_commands = True
except ModuleNotFoundError:
    print("Bot not run on Raspberry Pi, skipping pin functions")

#startup
dotenv.load_dotenv(".env")
TOKEN: str = os.getenv("TOKEN")
client = commands.Bot(command_prefix="Q.", intents=discord.Intents.all())

@client.event
async def on_ready():
    await client.tree.sync()
    print("Quazi Clone online")

#commands
@client.tree.command(name="hello_world", description="Say hello to my little friend!")
async def hello_world(interaction: discord.Interaction):
    await interaction.response.send_message("Hello World!")

@client.tree.command(name="spam", description="Spam a message")
async def spam(interaction: discord.Interaction, message: str, amount: int = 5):
    await interaction.response.send_message("What have you done", ephemeral=True)
    for i in range(amount):
        await interaction.channel.send(message)

#audio commands
@client.tree.command(name="join_vc", description="Bot will join a voice channel")
async def join_vc(interaction: discord.Interaction, voice_channel: discord.VoiceChannel):
    await interaction.response.send_message("Joining voice channel", ephemeral=True)
    return await voice_channel.connect()
    
@client.tree.command(name="vc_with_me", description="Bot will join the voice channel the user is in")
async def vc_with_me(interaction: discord.Interaction):
    await interaction.response.send_message("Joining voice channel", ephemeral=True)
    return await interaction.user.voice.channel.connect()

@client.tree.command(name="youtube", description="Play YouTube audio")
async def youtube(interaction: discord.Interaction, url: str):
    voice = interaction.guild.voice_client
    if voice == None:
        return await interaction.response.send_message("Bot needs to be in a voice channel for this")
    #await clearYoutube()
    if voice.is_playing():
        return await interaction.response.send_message("Please wait until audio is finished")
    video_name = await download_video(url)
    #voice.play(FFmpegPCMAudio(video_name))
    await interaction.response.send_message("Download success")
        
#hardware commands
@client.tree.command(name="change_led", description="Changes LED on hardware")
async def change_led(interaction: discord.Interaction, is_on: bool):
    if bot_has_pin_commands:
        pin_functions.change_led(is_on)
        await interaction.response.send_message("LED changed", ephemeral=True)
    else:
        await interaction.response.send_message("Bot currently does not have access to pin I/O")

#helper functions
async def download_video(url: str):
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192'
        }], 'noplaylist': True
    }
    downloader = yt_dlp.YoutubeDL(ydl_opts)
    downloader.download([url])
    print(downloader.extract_info(url))

client.run(TOKEN)