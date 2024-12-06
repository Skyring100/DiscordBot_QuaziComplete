import discord
from discord.ext import commands
import dotenv
import os
import shutil
import yt_dlp
from discord import FFmpegPCMAudio

bot_has_pin_commands: bool = False
try:
    import pin_functions
    bot_has_pin_commands = True
except ModuleNotFoundError:
    print("Bot not run on Raspberry Pi, skipping pin functions")

#folder setup
download_folder = "downloaded_audio"
if not os.path.exists(download_folder):
    os.makedirs(download_folder)
max_audio_duration = "7:00"

#bot startup
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

@client.tree.command(name="leave_vc", description="Bot will leave the vc it is currently in")
async def leave_vc(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Voice channel disconnected", ephemeral=True)
    else:
        await interaction.response.send_message("Bot is not in a voice channel", ephemeral=True)

@client.tree.command(name="youtube", description="Play YouTube audio")
async def youtube(interaction: discord.Interaction, url: str):
    voice = interaction.guild.voice_client
    if not voice:
        return await interaction.response.send_message("Bot needs to be in a voice channel for this")
    if voice.is_playing():
        return await interaction.response.send_message("Please wait until audio is finished")
    await interaction.response.defer()
    video_path = await download_video(url)
    if not video_path:
        await interaction.response.send_message("Audio is too long to download", ephemeral=True)
    else:
        await interaction.response.send_message("Audio read", ephemeral=True)
        voice.play(FFmpegPCMAudio(video_path))
        
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
    video_info = downloader.extract_info(url, download=False)
    print(video_info)
    #check how long the video is before downloading
    if video_info["duration_string"] > max_audio_duration:
        return None
    video_name = video_info["title"] + " [" +video_info["id"]+"].mp3"
    video_path = os.path.join(download_folder, video_name)
    #Check if video is not already downloaded
    if not os.path.exists(video_path):
        downloader.download([url])
        shutil.move(video_name, download_folder)
    return video_path

client.run(TOKEN)