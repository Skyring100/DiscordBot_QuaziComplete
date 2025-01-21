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
    db_cursor.execute("CREATE TABLE quotes(guild_id int, content varchar(500), day_timestamp varchar(10), PRIMARY KEY(guild_id, content))")
try:
    db_cursor.execute("SELECT * FROM gifs")
except sqlite3.OperationalError:
    db_cursor.execute("CREATE TABLE gifs(guild_id int, gif_link varchar(500), category varchar(50), PRIMARY KEY (guild_id, gif_link))")
try:
    db_cursor.execute("SELECT * FROM addable_roles")
except sqlite3.OperationalError:
    db_cursor.execute("CREATE TABLE addable_roles(guild_id int, role_id int, PRIMARY KEY (guild_id, role_id))")
try:
    db_cursor.execute("SELECT * FROM welcome_messages")
except sqlite3.OperationalError:
    db_cursor.execute("CREATE TABLE welcome_messages(guild_id int, message varchar(500) NOT NULL, welcome_channel_id int NOT NULL, PRIMARY KEY (guild_id))")

db_con.commit()

bot_has_pin_commands: bool = False
'''
try:
    import pin_functions
    bot_has_pin_commands = True
except ModuleNotFoundError:
    print("Bot not run on Raspberry Pi, skipping pin functions")
'''

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

@client.event
async def on_member_join(member: discord.Member):
    #send welcome message if configured
    welcome_data = db_cursor.execute(f"SELECT welcome_messages.message, welcome_messages.welcome_channel_id FROM welcome_messages WHERE welcome_messages.guild_id={member.guild.id}").fetchone()
    if welcome_data:
        await member.guild.get_channel(welcome_data[1]).send(f"Hello {member.mention},\n{welcome_data[0]}")



#testing commands

@client.tree.command(name="hello_world", description="Say hello to my little friend!")
async def hello_world(interaction: discord.Interaction):
    await interaction.response.send_message("Hello World!")

@client.tree.command(name="spam", description="Spam a message")
async def spam(interaction: discord.Interaction, message: str, amount: int = 5):
    await interaction.response.send_message("What have you done", ephemeral=True)
    for i in range(amount):
        await interaction.channel.send(message)

@client.tree.command(name="set_welcome_message", description="Sets the welcome message that the bot will send upon a new user joining the server")
async def set_welcome_message(interaction: discord.Interaction, message: str, welcome_channel: discord.TextChannel):
    #make sure the caller is authorized to change the welcome message
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("You are not authorized to set the welcome message for this server")
        return
    await interaction.response.defer()
    server_has_welcome = db_cursor.execute(f"SELECT welcome_messages.message FROM welcome_messages WHERE welcome_messages.guild_id={interaction.guild_id}").fetchone()
    if server_has_welcome:
        db_cursor.execute(f"UPDATE welcome_messages SET message=?, welcome_channel_id={welcome_channel.id} WHERE guild_id={interaction.guild_id}", [message])
    else:
        db_cursor.execute(f"INSERT INTO welcome_messages(guild_id, message, welcome_channel_id) VALUES({interaction.guild_id}, ?, {welcome_channel.id})", [message])
    db_con.commit()
    await interaction.followup.send(f"A new welcome message has be set for the server:\n{message}")


#quote of the day commands

@client.tree.command(name="quote_of_the_day", description="Selects a quote to be quote of the day!")
async def quote_of_the_day(interaction: discord.Interaction):
    await interaction.response.defer()
    quote_data = db_cursor.execute(f"SELECT quotes.content, quotes.day_timestamp FROM quotes WHERE quotes.guild_id={interaction.guild_id}").fetchone()
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

#gif commands

@client.tree.command(name="add_gif", description="Adds a gif to he list of gif the bot can send")
async def add_gif(interaction: discord.Interaction, gif:str, category:str=None):
    await interaction.response.defer()
    query = f"INSERT INTO gifs(guild_id, gif_link, category) VALUES ({interaction.guild_id}, ?, "
    safe_input = [gif]
    if not category:
        query += "NULL)"
    else:
        query += "?)"
        safe_input.append(category)

    try:
        print(query)
        print(safe_input)
        db_cursor.execute(query, safe_input)
        db_con.commit()
        await interaction.followup.send(f"Gif successfully added:\n{gif}")
    except sqlite3.OperationalError:
        traceback.print_exc()
        print("Gif: "+gif+" category: "+str(category))
    except sqlite3.IntegrityError:
        await interaction.followup.send("This gif has already been added")

@client.tree.command(name="send_gif", description="Sends a random gif that the bot has been allowed to send")
async def send_gif(interaction: discord.Interaction, category:str=None):
    await interaction.response.defer()
    query = f"SELECT gifs.gif_link FROM gifs WHERE gifs.guild_id={interaction.guild_id}"
    safe_input = []
    if category:
        query += " and gifs.category=?"
        safe_input.append(category)
    gif_results = db_cursor.execute(query, safe_input).fetchall()
    if not gif_results:
        await interaction.followup.send("There are no gifs added for this server or category. Try adding some with commands!")
        return
    await interaction.followup.send(random.choice(gif_results)[0])

@client.tree.command(name="gif_categories", description="Lists all categories of gifs created for this server")
async def gif_categories(interaction: discord.Interaction):
    await interaction.response.defer()
    categories = db_cursor.execute(f"SELECT DISTINCT gifs.category FROM gifs WHERE gifs.guild_id={interaction.guild_id}")
    string_categories = str_query_results(categories)
    if string_categories != "":
        await interaction.followup.send(f"This server has the following gif categories:\n{string_categories}")
    else:
        await interaction.followup.send(f"This server currently has no categories for gifs")

#role commands

@client.tree.command(name="add_role", description="Allows the user to add one of the authorized roles to themselves")
async def add_role(interaction: discord.Interaction, role: discord.Role):
    await interaction.response.defer()
    role_authorized = db_cursor.execute(f"SELECT addable_roles.role_id FROM addable_roles WHERE addable_roles.guild_id={interaction.guild_id} AND addable_roles.role_id={role.id}").fetchone()
    if role_authorized:
        await interaction.user.add_roles(role)
        await interaction.followup.send(f"{interaction.user.name} joined {role.name}")
    else:
        await interaction.followup.send("You are not authorized to get this role")
    
@client.tree.command(name="authorize_role", description="Allows an admin to add roles that people can add to themsleves with the bot")
async def authorize_role(interaction: discord.Interaction, role: discord.Role):
    await interaction.response.defer()
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.followup.send("You must have the 'manage roles' permission in the server to use this command")
        return
    try:
        db_cursor.execute(f"INSERT INTO addable_roles(guild_id, role_id) VALUES ({interaction.guild_id}, {role.id})")
        db_con.commit()
    except sqlite3.IntegrityError:
        await interaction.followup.send("Role has already been authorized")
        return
    await interaction.followup.send(f"Role authorized:{role.name}")

@client.tree.command(name="deauthorize_role", description="Removes a previously authorized role")
async def deauthorize_role(interaction: discord.Interaction, role: discord.Role):
    await interaction.response.defer()
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.followup.send("You must have the 'manage roles' permission in the server to use this command")
        return
    db_cursor.execute(f"DELETE FROM addable_roles WHERE addable_roles.guild_id={interaction.guild_id} AND addable_roles.role_id={role.id}")
    db_con.commit()
    await interaction.followup.send(f"Role deauthorized:{role.name}")

@client.tree.command(name="list_authorized_roles", description="Shows a list of all roles that are authorized")
async def list_authorized_roles(interaction: discord.Interaction):
    await interaction.response.defer()
    roles = db_cursor.execute(f"SELECT addable_roles.role_id FROM addable_roles WHERE addable_roles.guild_id={interaction.guild_id}")
    result_str = ""
    for r in roles:
        role_data = interaction.guild.get_role(r[0])
        result_str += str(role_data.name+", ")
    #remove the last ", " from string
    result_str = result_str[:-2]  
    await interaction.followup.send(f"The following roles to choose from are:\n{result_str}")
    

#audio commands

@client.tree.command(name="join_vc", description="Bot will join a voice channel")
async def join_vc(interaction: discord.Interaction, voice_channel: discord.VoiceChannel):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message(f"Joining voice channel {voice_channel.name}")
    return await voice_channel.connect()
    
@client.tree.command(name="vc_with_me", description="Bot will join the voice channel the user is in")
async def vc_with_me(interaction: discord.Interaction):
    await interaction.response.send_message(f"Joining voice channel with {interaction.user.name}")
    return await interaction.user.voice.channel.connect()

@client.tree.command(name="leave_vc", description="Bot will leave the vc it is currently in")
async def leave_vc(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Voice channel disconnected")
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
        await interaction.followup.send("Audio is ready!")
        voice.play(FFmpegPCMAudio(video_path))

#hardware commands

@client.tree.command(name="change_led", description="Changes LED on hardware")
async def change_led(interaction: discord.Interaction, is_on: bool):
    if bot_has_pin_commands:
        pin_functions.change_led(is_on)
        await interaction.response.send_message("LED changed")
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

def str_query_results(results: sqlite3.Cursor):
    result_list = results.fetchall()
    if len(result_list) == 0:
        return ""
    result_str = ""
    for r in result_list:
        print(r)
        print(type(r[0]))
        if type(r[0]) == None:
            continue
        result_str += str(str(r[0])+", ")
    #remove the last ", " from string
    return result_str[:-2]  

client.run(TOKEN)