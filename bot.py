import discord
from discord.ext import commands
import dotenv
import os
import shutil
import yt_dlp
from discord import FFmpegPCMAudio
import random
from datetime import datetime
import traceback
import sqlite3
#connect to the bot's database
db_con = sqlite3.connect("discord_bot.db")
#setup cursor needed for queries
db_cursor = db_con.cursor()

#create tables if they do not exist
try:
    db_cursor.execute("SELECT * FROM quotes")
except sqlite3.OperationalError:
    db_cursor.execute("CREATE TABLE quotes(guild_id, content, day_timestamp)")

try:
    db_cursor.execute("SELECT * FROM gifs")
except sqlite3.OperationalError:
    db_cursor.execute("CREATE TABLE gifs(guild_id, gif_link, category)")

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

#bot startup
dotenv.load_dotenv(".env")
TOKEN: str = os.getenv("TOKEN")
client = commands.Bot(command_prefix="Q.", intents=discord.Intents.all())

@client.event
async def on_ready():
    await client.tree.sync()
    print("Quazi Clone online")

#general commands
@client.tree.command(name="hello_world", description="Say hello to my little friend!")
async def hello_world(interaction: discord.Interaction):
    await interaction.response.send_message("Hello World!")

@client.tree.command(name="spam", description="Spam a message")
async def spam(interaction: discord.Interaction, message: str, amount: int = 5):
    await interaction.response.send_message("What have you done", ephemeral=True)
    for i in range(amount):
        await interaction.channel.send(message)

@client.tree.command(name="quote_of_the_day", description="Selects a quote to be quote of the day!")
async def quote_of_the_day(interaction: discord.Interaction):
    await interaction.response.defer()
    quote_data = db_cursor.execute("SELECT quotes.content, quotes.day_timestamp FROM quotes WHERE quotes.guild_id="+str(interaction.guild_id)).fetchone()
    if not quote_data or quote_data[1] != datetime.today().strftime("%Y-%m-%d"):
        #There is either not an quote for server or the quote needs to be updated
        quote = await choose_random_quote(interaction.guild)
        success = change_q_of_day(interaction.guild, quote)
        if not success:
            await interaction.followup.send("There was a database error", ephemeral=True)
            return
    else:
        quote = quote_data[0]
    await interaction.followup.send(quote)

@client.tree.command(name="refresh_quote", description="Reselects quote of the day")
async def refresh_quote(interaction: discord.Interaction):
    await interaction.response.defer()
    quote = await choose_random_quote(interaction.guild)
    success = change_q_of_day(interaction.guild, quote)
    if not success:
        await interaction.followup.send("There was a database error", ephemeral=True)
        return
    await interaction.followup.send(quote)

#audio commands
@client.tree.command(name="join_vc", description="Bot will join a voice channel")
async def join_vc(interaction: discord.Interaction, voice_channel: discord.VoiceChannel):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
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
        return await interaction.response.send_message("Bot needs to be in a voice channel for this", ephemeral=True)
    if voice.is_playing():
        return await interaction.response.send_message("Please wait until audio is finished", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    video_path = await download_video(url)
    if not video_path:
        await interaction.followup.send("Audio is too long to download", ephemeral=True)
    else:
        await interaction.followup.send("Audio is ready!", ephemeral=True)
        voice.play(FFmpegPCMAudio(video_path))

#hardware commands
@client.tree.command(name="change_led", description="Changes LED on hardware")
async def change_led(interaction: discord.Interaction, is_on: bool):
    if bot_has_pin_commands:
        pin_functions.change_led(is_on)
        await interaction.response.send_message("LED changed", ephemeral=True)
    else:
        await interaction.response.send_message("Bot currently does not have access to pin I/O", ephemeral=True)

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
    duration_data = video_info["duration_string"].split(":")
    #limit the duration
    if len(duration_data) > 2 and int(duration_data[2]) < 2:
        return None
    video_name = video_info["title"] + " [" +video_info["id"]+"].mp3"
    video_path = os.path.join(download_folder, video_name)
    #Check if video is not already downloaded
    if not os.path.exists(video_path):
        downloader.download([url])
        shutil.move(video_name, download_folder)
    return video_path

#helper functions
def clear_audio_folder():
    for file in os.listdir(download_folder):
        os.remove(file)

async def choose_random_quote(guild: discord.guild):
    #find the quotes channel of this guild
    quotes_channel = None
    for channel in guild.text_channels:
        if channel.name == "quotes" or channel.name == "quote":
            quotes_channel = channel
    if not quotes_channel:
        return None
    else:
        #quotes channel has been found, now select a random quote
        messages = [m async for m in quotes_channel.history(limit=200)]
        if len(messages) == 0:
            return None
        chosen_quote = random.choice(messages).content
        return chosen_quote

def change_q_of_day(server: discord.Guild, quote_content: str):
    guild_id = server.id
    test_query = db_cursor.execute("SELECT quotes.guild_id FROM quotes WHERE quotes.guild_id="+str(guild_id)).fetchone()
    if not test_query:
        #this server has never used the 'quote of the day' command
        #add the quote for this server to the database
        try:
            query = "INSERT INTO quotes(guild_id, content, day_timestamp) VALUES ("+str(guild_id)+", ?, '"+datetime.today().strftime("%Y-%m-%d")+"')"
            db_cursor.execute(query,(quote_content,))
            db_con.commit()
            print("Guild quote entry added")
        except sqlite3.OperationalError as err:
            traceback.print_exc()
            print(quote_content)
            print(query)
            return False
    else:
        #we need to update quote of the day
        #update with the new quote
        try:
            query = "UPDATE quotes SET content=?, day_timestamp='"+datetime.today().strftime("%Y-%m-%d")+"' WHERE guild_id="+str(guild_id)
            db_cursor.execute(query, (quote_content,))
            db_con.commit()
            print(query)
            print("Guild quote entry updated")
        except sqlite3.OperationalError as err:
            traceback.print_exc()
            print(quote_content)
            return False
    return True


client.run(TOKEN)