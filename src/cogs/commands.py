import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import re
from tib_utility.db_utils import cursor, database
import tib_utility.config as config

owner_id = config.owner()

COG_CATEGORIES = {
    'db': 'TPE Leaderboards',
    'placemap': 'Placemap Commands',
    'commander': 'General Commands',
}

def bot_commands(existing_commands, parent_name=''):
    """Find all bot commands for /help"""
    command_list = []
    for command in existing_commands:
        full_name = f'{parent_name} {command.name}'.strip()
        if isinstance(command, app_commands.Group):
            command_list.extend(bot_commands(command.commands, parent_name=full_name))
        else:
            description = command.description or 'No description provided.'
            command_list.append((f'/{full_name}', description))
    return command_list

class commander(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Command cog loaded.')

    @app_commands.command(name='hello', description='Say hi!')
    async def hello(self, interaction: discord.Interaction):
        await interaction.response.send_message(f'Hello, {interaction.user.mention}.')
    
    @app_commands.command(name='ping', description='See the ping.')
    async def ping(self, interaction: discord.Interaction):
        bot_latency = round(self.client.latency * 1000)
        await interaction.response.send_message(f'Pong! Current ping is {bot_latency}ms.')
    
    @app_commands.command(name='help', description='Displays all existing commands.')
    async def help(self, interaction: discord.Interaction):
        """Help command that dynamically finds all slash commands within the bot."""
        categories = {}
        for cog in self.client.cogs.values():
            cog_name = cog.__class__.__name__.lower()
            if cog_name == 'admin':
                continue
            category = COG_CATEGORIES.get(cog_name, cog.__class__.__name__)
            commands = getattr(cog, '__cog_app_commands__', [])
            for command in bot_commands(commands):
                full_name, description = command
                categories.setdefault(category, []).append(f'* `{full_name}`: {description}')

        embed = discord.Embed(
            title = 'Available Commands',
            color= discord.Color.purple()
        )
        for category, commands in categories.items():
            embed.add_field(
                name=category,
                value='\n'.join(commands) if commands else 'No commands available in this category.',
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='canvas', description='See a canvas.')
    @app_commands.describe(
        canvas='Canvas number',
        display='Choose whether to use a custom display or not.'
    )
    @app_commands.choices(display=[
        app_commands.Choice(name='Initial', value='initial'),
        app_commands.Choice(name='Final', value='final'),
        app_commands.Choice(name='Activity', value='activity'),
        app_commands.Choice(name='Age', value='age'),
        app_commands.Choice(name='Virgin', value='virgin'),
        app_commands.Choice(name='Milliseconds', value='milliseconds'),
        app_commands.Choice(name='Minutes', value='minutes'),
        app_commands.Choice(name='Seconds', value='seconds'),
        app_commands.Choice(name='Combined', value='combined'),
        ]
    )
    async def canvas(self, interaction: discord.Interaction, canvas: str, display: Optional[app_commands.Choice[str]] = None):
        """View a canvas generated via the pxlslog-explorer."""
        displayed = display.value if display else 'final'
        await interaction.response.defer(ephemeral=False, thinking=True)
        try:
            if not re.fullmatch(r'^(?![cC])[a-z0-9]{1,4}+$', canvas):
                await interaction.followup.send('Invalid format, canvases may not begin with c.', ephemeral=True)
                return
            filename = f'canvas-{canvas}_{displayed}.png'
            path = f'{config.pxlslog_explorer_dir}/pxls-final-canvas/canvas-{canvas}-{displayed}.png'
            file = discord.File(path, filename=filename)
            embed = discord.Embed(title=f'Canvas {canvas}, {displayed}')
            embed.set_image(url=f'attachment://{filename}')
            await interaction.followup.send(embed=embed, file=file)
            print(f'Sending canvas {canvas}, {displayed}')
        except Exception as e:
            if canvas  in ['6','17','28','30a']:
                await interaction.followup.send('Log files are... weird for c6, c17, c28, and c30a, and thus final images are not available.', ephemeral=True)
            else: 
                await interaction.followup.send(f'No log files available.', ephemeral=True)
                print(f'An error occurred: {e}')
                
    @app_commands.command(name='notify-me', description='Sign up for DM notifications when Tib is updated with new canvases (run again to unsubscribe).')
    async def notfications(self, interaction: discord.Interaction):
        """Command to add users to DB for DM notifcations"""
        try:
            cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (interaction.user.id,))
        except Exception as e:
            return await interaction.response.send_message(f'An error occurred while signing you up: {e}', ephemeral=True)
        cursor.execute('SELECT status FROM notif WHERE user_id = ?', (interaction.user.id,))
        result = cursor.fetchone()
        if result is None:
            cursor.execute('INSERT INTO notif (user_id, status) VALUES (?, ?)', (interaction.user.id, 1))
            database.commit()
            await interaction.response.send_message('You have been signed up for notifications!', ephemeral=True)
            print(f'{interaction.user} ({interaction.user.id}) signed up for notifications.')
        else:
            if result[0] == 1:
                cursor.execute('UPDATE notif SET status = 0 WHERE user_id = ?', (interaction.user.id,))
                database.commit()
                await interaction.response.send_message('You have been unsubscribed from notifications.', ephemeral=True)
                print(f'{interaction.user} ({interaction.user.id}) unsubscribed from notifications.')
            if result[0] == 0:
                cursor.execute('UPDATE notif SET status = 1 WHERE user_id = ?', (interaction.user.id,))
                database.commit()
                await interaction.response.send_message('You have been re-subscribed to notifications!', ephemeral=True)
                print(f'{interaction.user} ({interaction.user.id}) re-subscribed to notifications.')

async def setup(client):
    await client.add_cog(commander(client))