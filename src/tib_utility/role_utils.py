import discord
import tib_utility.config as config
from tib_utility.db_utils import cursor

class RoleUtility:
    @staticmethod
    async def sync_point_role(guild: discord.Guild, member: discord.Member, total_points: int):
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
            role for role in member.roles if role.id in cur_role_ids and (new_role is None or role.id != new_role.id)
        ]

        if remove_roles:
            await member.remove_roles(*remove_roles)

        if new_role is not None and new_role not in member.roles:
            await member.add_roles(new_role)

    @staticmethod
    def get_total_points(username: str) -> int:
        query = "SELECT COALESCE(SUM(points), 0) FROM points WHERE user = ?"
        cursor.execute(query, (username,))
        return int(cursor.fetchone()[0])