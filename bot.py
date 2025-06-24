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
from types import NoneType
import re

#connect to the bot's database
db_con = sqlite3.connect("discord_bot.db")
#setup cursor needed for queries
db_cursor = db_con.cursor()


db_tables = [("quotes","guild_id int, content varchar(500), day_timestamp varchar(10), PRIMARY KEY(guild_id, content)"),
             ("gifs", "guild_id int, gif_link varchar(500), category varchar(50), PRIMARY KEY (guild_id, gif_link)"),
             ("addable_roles", "guild_id int, role_id int, PRIMARY KEY (guild_id, role_id"),
             ("welcome_messages", "guild_id int, message varchar(500) NOT NULL, welcome_channel_id int NOT NULL, PRIMARY KEY (guild_id)"),
             ("user_battle_stats", "user_id int, guild_id, int max_health int, current_health int, attack int, defence int, level int, PRIMARY KEY (user_id, guild_id)")]

#create tables if they do not exist
for table in db_tables:
    db_cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table[0]}';")
    if db_cursor.fetchone()[0] != 1:
        db_cursor.execute(f"CREATE TABLE {table[0]}({table[1]})")

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

#basic commands

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
    print(quote_data)
    if not quote_data[0] or quote_data[1] != datetime.today().strftime("%Y-%m-%d"):
        #There is either not an quote for server or the quote needs to be updated
        quote = await choose_random_quote(interaction.guild)
        if not quote:
            await interaction.followup.send("There are no quotes to be found!")
            return
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
    if not quote:
        await interaction.followup.send("There are no quotes to be found!")
        return
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

@client.tree.command(name="remove_gif", description="Removes a gif that was previously added")
async def remove_gif(interaction: discord.Interaction, gif:str):
    await interaction.response.defer()
    query = f"SELECT gifs.gif_link FROM gifs WHERE gifs.guild_id={interaction.guild_id} AND gifs.gif_link=?"
    print(query)
    gif_exists = db_cursor.execute(query, [gif]).fetchone()
    if not gif_exists:
        await interaction.followup.send("This gif does not exist in this server", ephemeral=True)
    else:
        # Delete the gif
        query = f"DELETE FROM gifs WHERE gifs.guild_id={interaction.guild_id} AND gifs.gif_link=?"
        db_cursor.execute(query, [gif])
        db_con.commit()
        await interaction.followup.send("The following gif has been removed: "+gif, ephemeral=True)


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

#battle commands

@client.tree.command(name="battle_bot", description="Attack this Discord bot!")
async def battle_bot(interaction: discord.Interaction):
    print(f"{interaction.user.name} is battling {interaction.client.user.name}")
    bot_stats = get_battle_stat_profile(interaction.client.user.id, interaction.guild_id, True)
    user_stats = get_battle_stat_profile(interaction.user.id, interaction.guild_id)
    # Check if user has no health left
    if user_stats[3] == 0:
        await interaction.response.send_message("You dont have any health left!")
    else:
        battle_message = attack_entity(user_stats, bot_stats, interaction.user.name, interaction.client.user.name)
        if bot_stats[3] != 0:
            battle_message += attack_entity(bot_stats, user_stats, interaction.client.user.name, interaction.user.name)
            if user_stats[3] == 0:
                battle_message += f"\n{interaction.user.name} was defeated!"
        else:
            battle_message += f"{interaction.client.user.name} was defeated!"
        # Update stats for user and bot in database
        db_cursor.execute(f"UPDATE battle_stats SET current_health={bot_stats[3]} WHERE user_id={interaction.client.user.id} AND guild_id={interaction.guild_id}")
        db_cursor.execute(f"UPDATE battle_stats SET current_health={user_stats[3]} WHERE user_id={interaction.user.id} AND guild_id={interaction.guild_id}")
        await interaction.response.send_message(battle_message)

@client.tree.command(name="defend_from_bot", description="Defend from the bot's attack and heal in the process!")
async def defend_from_bot(interaction: discord.Interaction):
    print(f"{interaction.user.name} is defending")
    bot_stats = get_battle_stat_profile(interaction.client.user.id, interaction.guild_id, True)
    user_stats = get_battle_stat_profile(interaction.user.id, interaction.guild_id)
    # Check if user has no health left
    if user_stats[3] == 0:
        await interaction.response.send_message("You dont have any health left!")
    else:
        # Heal randomly froma minimum of 2 point to a maximum of half their max health
        heal_amount = random.randint(2, round(user_stats[2]/2))
        user_stats[3] += heal_amount
        battle_message = f"{interaction.user.name} is defending and healed {heal_amount} points!\n" + attack_entity(bot_stats, user_stats, interaction.client.user.name, interaction.user.name)
        await interaction.response.send_message(battle_message)



#helper functions

async def download_video(url: str):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192'
        }],
        'output': os.path.join(os.path.join(os.getcwd(), download_folder), "%(title)s_%(id)s.%(ext)s")
    }
    downloader = yt_dlp.YoutubeDL(ydl_opts)
    video_info = downloader.extract_info(url, download=False)
    print(video_info)
    #check how long the video is before downloading
    duration_data = video_info["duration_string"].split(":")
    #limit the duration
    if len(duration_data) > 2 and int(duration_data[2]) < 2:
        return None
    name = video_info["title"]
    id = video_info["id"]
    video_name = f"{name} [{id}].mp3"
    #video_path = os.path.join(download_folder, video_name)
    return video_name

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
        if type(r[0]) == NoneType or type(r[0]) == None:
            continue
        result_str += str(str(r[0])+", ")
    #remove the last ", " from string
    return result_str[:-2]  

def get_battle_stat_profile(user_id: int, guild_id: int, is_bot_self: bool = False):
    stats = db_cursor.execute(f"SELECT * FROM bot_battle_stats WHERE user_id={user_id} AND guild_id={guild_id}")
    # Check if stats have not been initialized
    profile = stats.fetchone()
    if not profile[0]:
        defaut_battle_stats = {"health": 20, "attack":2, "defence": 2}
        bot_boss_modifier = 2

        health = defaut_battle_stats['health']
        attack = defaut_battle_stats['attack']
        defence = defaut_battle_stats['defence']
        if is_bot_self:
            health *= bot_boss_modifier
            attack *= bot_boss_modifier
        values_string = f"{user_id}, {guild_id}, {health}, {health}, {attack}, {defence}, 1"
        db_cursor.execute(f"INSERT INTO bot_battle_stats(user_id, guild_id, max_health, current_health, attack) VALUES ({values_string})")
        return (user_id, guild_id, health, health, attack, defence, 1)
    return profile

# Returns battle text
def attack_entity(attacker_stats: tuple, defender_stats: tuple, attacker_name: str, defender_name: str):
    critical_hit = (True if (random.random() < 0.25) else False)
    # Add critical hit multipler if applicable and use defence stat from defender
    damage = attacker_stats[4] * (2 if critical_hit else 1) - defender_stats[5]
    # Ensure no negative damage
    damage = 0 if damage < 0 else damage
    defender_stats[3] -= damage
    if defender_stats[3] < 0:
        defender_stats[3] = 0
    return f"{attacker_name} did {damage} to {defender_name}!" + ("It was a critical hit!" if critical_hit else "")


client.run(TOKEN)