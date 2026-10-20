"""All Discord role logic"""

import discord
from tib_utility import config
from tib_utility.db_utils import cursor

class RoleUtility:
    """Handles all Discord role logic."""

    @staticmethod
    async def sync_point_role(guild: discord.Guild, member: discord.Member, total_points: int):
        """Syncs all point roles to users when their points are updated 
        (ops, /admin add-points, etc)

        Args:
            guild (discord.Guild): The guild to do this in
            member (discord.Member): Who to apply the roles to
            total_points (int): Determines which point role they should get.
        """
        role_ids = config.point_rank_roles()
        cur_thresholds = [
            threshold for threshold in role_ids if total_points >= threshold
        ]

        new_threshold = max(cur_thresholds, default=None)
        cur_role_ids = set(role_ids.values())

        new_role = None
        if new_threshold is not None:
            new_role = guild.get_role(role_ids[new_threshold])
            if new_role is None:
                print(
                    f"Configured role for {new_threshold} points was not found."
                )
                return

        remove_roles = [
            role for role in member.roles if role.id in cur_role_ids and (
                new_role is None or role.id != new_role.id
                )
        ]
        for role in remove_roles:
            if not role.is_assignable:
                continue
            try:
                await member.remove_roles(*remove_roles)
            except discord.Forbidden:
                continue

        if new_role is not None and new_role not in member.roles:
            if new_role.is_assignable():
                try:
                    await member.add_roles(new_role)
                    await RoleUtility.rankup_message(guild, member, total_points, new_role)
                except discord.Forbidden:
                    pass

    @staticmethod
    def get_total_points(username: str) -> int:
        """Finds the total points for any one user

        Args:
            username (str): the user in question

        Returns:
            int: The number of found points, else 0
        """
        query = "SELECT COALESCE(SUM(points), 0) FROM points WHERE user = ?"
        cursor.execute(query, (username,))
        return int(cursor.fetchone()[0])

    @staticmethod
    def points_to_next_role(total_points: int) -> int:
        """Finds the points needed to reach the next role

        Args:
            total_points (int): The user's current total points

        Returns:
            int: The number of points needed to reach the next role, else 0
        """
        role_ids = config.point_rank_roles()
        thresholds = sorted(role_ids.keys())
        for threshold in thresholds:
            if total_points < threshold:
                return threshold - total_points
        return 0

    @staticmethod
    async def rankup_message(guild: discord.Guild, member: discord.Member,
                             total_points: int, new_role: discord.Role):
        """Sends a rankup message in a chosen channel."""
        rankup_channel_id = config.rankup_channel()
        rankup_channel = guild.get_channel(rankup_channel_id)
        if rankup_channel is None:
            print(f"Rankup channel with ID {rankup_channel_id} not found.")
            return

        member_id = member.id

        embed = discord.Embed(
            title="New rank up",
            description=f"""Congrats {member.mention}, you are now {new_role.name} with {total_points} points!
            You need {RoleUtility.points_to_next_role(total_points)} points until the next rank.""",
            color=discord.Color.green()
        )
        embed.set_footer(text="If you want to opt-out of rankup messages, you may run /operations no-rankup to disable them.")
        query = "SELECT rankup_status FROM users WHERE user_id = ?"
        cursor.execute(query, (member_id,))
        row = cursor.fetchone()
        if row is not None and row[0] == 0:
            content = None
        else:
            content = member.mention
        if isinstance(rankup_channel, discord.TextChannel):
            await rankup_channel.send(content=content, embed=embed)
