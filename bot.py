import discord
from discord.ext import commands
from discord import ui
import asyncio
from typing import Dict, Optional
import os

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ============================================
# ХРАНИЛИЩЕ КОМНАТ
# ============================================
active_rooms: Dict[str, 'CharacterRoom'] = {}

# ============================================
# КОНФИГУРАЦИЯ РЕЙДОВ
# ============================================
RAID_CONFIG = {
    "「📈」зерка": {
        "emoji": "🇿",
        "color": discord.Color.green(),
        "description": "Зерка",
        "short_name": "зерка"
    },
    "「📈」казерос": {
        "emoji": "🇰",
        "color": discord.Color.red(),
        "description": "Казерос",
        "short_name": "казерос"
    },
    "「📈」собор": {
        "emoji": "🇸",
        "color": discord.Color.gold(),
        "description": "Собор",
        "short_name": "собор"
    },
    "「📈」армог": {
        "emoji": "🇦",
        "color": discord.Color.blue(),
        "description": "Армог",
        "short_name": "армог"
    },
    "「📈」мордрум": {
        "emoji": "🇲",
        "color": discord.Color.purple(),
        "description": "Мордрум",
        "short_name": "мордрум"
    },
    "「📈」эгир": {
        "emoji": "🇪",
        "color": discord.Color.teal(),
        "description": "Эгир",
        "short_name": "эгир"
    }
}

DIFFICULTY_CONFIG = {
    "Обычный": {"emoji": "🇳", "color": discord.Color.green()},
    "Героический": {"emoji": "🇭", "color": discord.Color.red()}
}


# ============================================
# МОДАЛЬНОЕ ОКНО ДЛЯ ОПИСАНИЯ ЛОББИ
# ============================================

class CreateLobbyModal(ui.Modal):
    def __init__(self, raid_name: str, difficulty: str, channel: discord.TextChannel, role: discord.Role):
        title = f"Создание лобби: {raid_name} ({difficulty})"
        super().__init__(title=title[:45])
        self.raid_name = raid_name
        self.difficulty = difficulty
        self.target_channel = channel
        self.role = role

    leader_nick = ui.TextInput(
        label="👑 Ваш ник в игре",
        placeholder="Введите ваш ник в игре",
        max_length=100,
        required=True
    )

    description_input = ui.TextInput(
        label="📝 Описание",
        placeholder="прим: 4-4 +дд +сап",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        creator_id = str(interaction.user.id)

        if creator_id in active_rooms:
            existing_room = active_rooms[creator_id]
            await interaction.response.send_message(
                f"❌ У вас уже есть активное лобби!\n"
                f"📁 Канал: {existing_room.channel.mention}\n"
                f"📋 Название: **{existing_room.title}**\n\n"
                f"Закройте его перед созданием нового.",
                ephemeral=True
            )
            return

        raid_emoji = RAID_CONFIG[self.raid_name]["emoji"]
        diff_emoji = DIFFICULTY_CONFIG[self.difficulty]["emoji"]
        short_name = RAID_CONFIG[self.raid_name]["short_name"]

        room = CharacterRoom(
            creator=interaction.user,
            channel=self.target_channel,
            role=self.role,
            title=f"{raid_emoji} {short_name.upper()} - {diff_emoji} {self.difficulty}",
            description=self.description_input.value,
            raid_name=self.raid_name,
            difficulty=self.difficulty,
            leader_nick=self.leader_nick.value
        )

        active_rooms[creator_id] = room

        await room.create_room_message()

        await interaction.response.send_message(
            f"✅ Лобби создано в канале {self.target_channel.mention}!\n"
            f"🎯 {raid_emoji} **{short_name.upper()}** — {diff_emoji} **{self.difficulty}**\n"
            f"📝 {self.description_input.value[:100]}...",
            ephemeral=True
        )


# ============================================
# VIEW ДЛЯ ВЫБОРА СЛОЖНОСТИ
# ============================================

class DifficultyView(ui.View):
    def __init__(self, raid_name: str, channel: discord.TextChannel, role: discord.Role):
        super().__init__(timeout=300)
        self.raid_name = raid_name
        self.target_channel = channel
        self.role = role

    @ui.button(label="🇳 Обычный", style=discord.ButtonStyle.green)
    async def normal_button(self, interaction: discord.Interaction, button: ui.Button):
        modal = CreateLobbyModal(
            raid_name=self.raid_name,
            difficulty="Обычный",
            channel=self.target_channel,
            role=self.role
        )
        await interaction.response.send_modal(modal)
        self.stop()

    @ui.button(label="🇭 Героический", style=discord.ButtonStyle.red)
    async def heroic_button(self, interaction: discord.Interaction, button: ui.Button):
        modal = CreateLobbyModal(
            raid_name=self.raid_name,
            difficulty="Героический",
            channel=self.target_channel,
            role=self.role
        )
        await interaction.response.send_modal(modal)
        self.stop()


# ============================================
# ГЛАВНОЕ МЕНЮ СОЗДАНИЯ ЛОББИ
# ============================================

class CreateLobbyView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def get_raid_data(self, interaction: discord.Interaction, raid_key: str):
        guild = interaction.guild

        channel = discord.utils.get(guild.text_channels, name=raid_key.lower())
        if not channel:
            await interaction.response.send_message(
                f"❌ Канал «{raid_key}» не найден!\n"
                f"Убедитесь, что создан текстовый канал с названием **{raid_key}**",
                ephemeral=True
            )
            return None, None

        short_name = RAID_CONFIG[raid_key]["short_name"]
        role = discord.utils.get(guild.roles, name=short_name.lower())
        if not role:
            await interaction.response.send_message(
                f"❌ Роль «{short_name}» не найдена!\n"
                f"Убедитесь, что создана роль с названием **{short_name}**",
                ephemeral=True
            )
            return None, None

        return channel, role

    async def handle_raid_click(self, interaction: discord.Interaction, raid_key: str):
        if str(interaction.user.id) in active_rooms:
            existing_room = active_rooms[str(interaction.user.id)]
            await interaction.response.send_message(
                f"❌ У вас уже есть активное лобби!\n"
                f"📁 Канал: {existing_room.channel.mention}\n"
                f"📋 {existing_room.title}\n\n"
                f"Закройте его перед созданием нового.",
                ephemeral=True
            )
            return

        channel, role = await self.get_raid_data(interaction, raid_key)
        if not channel or not role:
            return

        raid_config = RAID_CONFIG[raid_key]

        embed = discord.Embed(
            title=f"{raid_config['emoji']} {raid_config['short_name'].upper()} — выбор сложности",
            description=f"{raid_config['description']}\n\nВыберите уровень сложности:",
            color=raid_config['color']
        )
        embed.set_footer(text="Обычный или Героический")

        view = DifficultyView(raid_key, channel, role)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @ui.button(label="Зерка", style=discord.ButtonStyle.green, emoji="🇿", row=0)
    async def zerka_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_raid_click(interaction, "「📈」зерка")

    @ui.button(label="Казерос", style=discord.ButtonStyle.red, emoji="🇰", row=0)
    async def kazeros_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_raid_click(interaction, "「📈」казерос")

    @ui.button(label="Собор", style=discord.ButtonStyle.gray, emoji="🇸", row=0)
    async def sobor_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_raid_click(interaction, "「📈」собор")

    @ui.button(label="Армог", style=discord.ButtonStyle.blurple, emoji="🇦", row=1)
    async def armog_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_raid_click(interaction, "「📈」армог")

    @ui.button(label="Мордрум", style=discord.ButtonStyle.red, emoji="🇲", row=1)
    async def mordrum_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_raid_click(interaction, "「📈」мордрум")

    @ui.button(label="Эгир", style=discord.ButtonStyle.blurple, emoji="🇪", row=1)
    async def egir_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_raid_click(interaction, "「📈」эгир")


# ============================================
# МОДАЛЬНОЕ ОКНО ДЛЯ ПОДАЧИ ЗАЯВКИ
# ============================================

class ApplicationModal(ui.Modal, title="Подать заявку"):
    def __init__(self, room):
        super().__init__()
        self.room = room

    character_url = ui.TextInput(
        label="🔗 Ссылка на оружейную",
        placeholder="https://example.com/my-armory",
        max_length=500,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        success, response = await self.room.add_applicant(
            interaction.user,
            self.character_url.value
        )

        if success:
            await interaction.response.send_message(
                "✅ Ваша заявка успешно отправлена!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ {response}",
                ephemeral=True
            )


# ============================================
# КЛАСС КОМНАТЫ (ЛОББИ)
# ============================================

class CharacterRoom:
    def __init__(self, creator: discord.Member, channel: discord.TextChannel,
                 role: discord.Role, title: str = "", description: str = "",
                 raid_name: str = "", difficulty: str = "", leader_nick: str = ""):
        self.creator = creator
        self.channel = channel
        self.role = role
        self.title = title
        self.description = description
        self.raid_name = raid_name
        self.difficulty = difficulty
        self.leader_nick = leader_nick
        self.applicants: Dict[str, dict] = {}
        self.is_open = True
        self.main_message: Optional[discord.Message] = None

    async def create_room_message(self):
        """Создает основное сообщение комнаты с кнопками и пингом роли"""
        raid_config = RAID_CONFIG.get(self.raid_name, {})
        diff_config = DIFFICULTY_CONFIG.get(self.difficulty, {})

        color = diff_config.get("color", raid_config.get("color", discord.Color.blue()))

        embed = discord.Embed(
            title=f"📋 {self.title}",
            description=self.description or f"Поиск кандидатов на роль {self.role.mention}",
            color=color
        )
        embed.add_field(name="👑 Создатель лобби", value=self.creator.mention, inline=True)
        embed.add_field(name="🎭 Роль", value=self.role.mention, inline=True)
        embed.add_field(name="⚡ Сложность", value=f"{diff_config.get('emoji', '')} {self.difficulty}", inline=True)
        embed.add_field(
            name="📝 Подать заявку",
            value=f"Требуется роль: {self.role.mention}\n",
            inline=False
        )
        embed.add_field(
            name="📈 Статистика",
            value="Заявок: 0",
            inline=False
        )
        embed.set_footer(
            text=f"Создатель лобби: {self.creator.display_name} | {raid_config.get('short_name', '')} | {self.difficulty}")

        view = RoomView(self)

        self.main_message = await self.channel.send(
            content=f"{self.role.mention} — {self.creator.mention} открыл набор!",
            embed=embed,
            view=view
        )
        return self.main_message

    async def update_main_message(self):
        """Обновляет основное сообщение комнаты"""
        if not self.main_message:
            return

        embed = self.main_message.embeds[0]

        diff_config = DIFFICULTY_CONFIG.get(self.difficulty, {})
        if not self.is_open:
            embed.set_field_at(2, name="⚡ Сложность",
                               value=f"{diff_config.get('emoji', '')} {self.difficulty} (ЗАКРЫТО)", inline=True)
        else:
            embed.set_field_at(2, name="⚡ Сложность", value=f"{diff_config.get('emoji', '')} {self.difficulty}",
                               inline=True)

        total = len(self.applicants)
        stats = f"Всего заявок: {total}"
        embed.set_field_at(4, name="📈 Статистика", value=stats, inline=False)

        view = RoomView(self) if self.is_open else None

        await self.main_message.edit(embed=embed, view=view)

    async def add_applicant(self, user: discord.Member, character_url: str):
        """Добавляет заявку и отправляет в ЛС создателю"""
        if not self.is_open:
            return False, "Набор в лобби закрыт!"

        if str(user.id) in self.applicants:
            return False, "Вы уже подали заявку в это лобби!"

        if self.role not in user.roles:
            return False, f"У вас нет роли {self.role.mention}!"

        # Отправляем заявку в ЛС создателю
        try:
            embed = discord.Embed(
                title=f"📝 Новая заявка в: {self.title}",
                description=f"**От участника:** {user.mention} ({user.display_name})\n"
                           f"**Ссылка на оружейную:** [Открыть]({character_url})",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="📌 Статус", value="⏳ Ожидает решения", inline=True)
            embed.set_footer(text=f"ID: {user.id} | Нажмите ✅ или ❌ ниже")

            view = ApplicationDMView(self, user)

            dm_message = await self.creator.send(embed=embed, view=view)

            self.applicants[str(user.id)] = {
                'user': user,
                'character_url': character_url,
                'status': 'pending',
                'dm_message': dm_message
            }

            await self.update_main_message()
            return True, "Заявка успешно отправлена!"

        except discord.Forbidden:
            return False, "У создателя закрыты личные сообщения!"
        except Exception as e:
            print(f"Ошибка отправки заявки: {e}")
            return False, "Произошла ошибка при отправке заявки"

    async def process_selection(self, interaction: discord.Interaction,
                                user: discord.Member, accepted: bool):
        """Обрабатывает выбор создателя в ЛС"""
        applicant = self.applicants.get(str(user.id))
        if not applicant or applicant['status'] != 'pending':
            await interaction.response.send_message(
                "❌ Эта заявка уже обработана!",
                ephemeral=True
            )
            return

        if accepted:
            applicant['status'] = 'accepted'

            if applicant.get('dm_message'):
                embed = applicant['dm_message'].embeds[0]
                embed.color = discord.Color.green()
                embed.set_field_at(0, name="📌 Статус", value="✅ Принято!", inline=True)
                await applicant['dm_message'].edit(embed=embed, view=None)

            await self.notify_applicant(user, True)
        else:
            applicant['status'] = 'rejected'

            if applicant.get('dm_message'):
                embed = applicant['dm_message'].embeds[0]
                embed.color = discord.Color.red()
                embed.set_field_at(0, name="📌 Статус", value="❌ Отклонено", inline=True)
                await applicant['dm_message'].edit(embed=embed, view=None)

            await self.notify_applicant(user, False)

        await interaction.response.send_message(
            f"✅ Заявка {'принята' if accepted else 'отклонена'}!",
            ephemeral=True
        )

        await self.update_main_message()

    async def notify_applicant(self, user: discord.Member, accepted: bool):
        """Отправляет уведомление участнику с ником лидера"""
        try:
            if accepted:
                embed = discord.Embed(
                    title="✅ Заявка принята!",
                    description=(
                        f"Ваша заявка в лобби **{self.title}** одобрена!\n\n"
                        f"👑 **Лидер лобби:** {self.leader_nick}\n"
                        f"📁 **Канал:** {self.channel.mention}\n\n"
                        f"Свяжитесь с лидером для координации!"
                    ),
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Заявка отклонена",
                    description=f"Ваша заявка в лобби **{self.title}** была отклонена.",
                    color=discord.Color.red()
                )

            embed.add_field(name="Роль", value=self.role.mention, inline=True)
            embed.add_field(name="Канал", value=self.channel.mention, inline=True)
            await user.send(embed=embed)
        except discord.Forbidden:
            pass

    async def check_all_processed(self):
        """Проверяет заявки (НЕ закрывает лобби автоматически)"""
        pass

    async def close_room(self, auto=False):
        """Закрывает комнату и удаляет из хранилища"""
        self.is_open = False

        # Уведомляем всех ожидающих, что набор закрыт
        for user_id, applicant in self.applicants.items():
            if applicant['status'] == 'pending':
                applicant['status'] = 'rejected'
                try:
                    await self.notify_applicant(applicant['user'], False)
                except:
                    pass
                if applicant.get('dm_message'):
                    try:
                        embed = applicant['dm_message'].embeds[0]
                        embed.color = discord.Color.red()
                        embed.set_field_at(0, name="📌 Статус", value="❌ Набор закрыт", inline=True)
                        await applicant['dm_message'].edit(embed=embed, view=None)
                    except:
                        pass

        await self.update_main_message()

        creator_id = str(self.creator.id)
        if creator_id in active_rooms:
            del active_rooms[creator_id]


# ============================================
# VIEW С КНОПКАМИ ДЛЯ ЛОББИ (В КАНАЛЕ)
# ============================================

class RoomView(ui.View):
    def __init__(self, room: CharacterRoom):
        super().__init__(timeout=None)
        self.room = room

    @ui.button(label="📝 Отправить заявку", style=discord.ButtonStyle.green)
    async def apply_button(self, interaction: discord.Interaction, button: ui.Button):
        """Кнопка для подачи заявки"""
        if interaction.user.id == self.room.creator.id:
            await interaction.response.send_message(
                "❌ Вы не можете подать заявку в своё лобби!",
                ephemeral=True
            )
            return

        if str(interaction.user.id) in self.room.applicants:
            await interaction.response.send_message(
                "❌ Вы уже подали заявку в это лобби!",
                ephemeral=True
            )
            return

        if self.room.role not in interaction.user.roles:
            await interaction.response.send_message(
                f"❌ У вас нет роли {self.room.role.mention}!",
                ephemeral=True
            )
            return

        modal = ApplicationModal(self.room)
        await interaction.response.send_modal(modal)

   
        embed.add_field(name="📝 Всего заявок", value=str(total), inline=True)
        embed.set_footer(text=f"Создатель лобби: {self.room.creator.display_name}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="🔒 Закрыть набор", style=discord.ButtonStyle.red)
    async def close_room_button(self, interaction: discord.Interaction, button: ui.Button):
        """Кнопка для закрытия комнаты"""
        if interaction.user.id != self.room.creator.id:
            await interaction.response.send_message(
                "❌ Только создатель лобби может закрыть набор!",
                ephemeral=True
            )
            return

        await self.room.close_room()
        await interaction.response.send_message(
            "🔒 Набор закрыт!",
            ephemeral=True
        )


# ============================================
# VIEW С КНОПКАМИ ДЛЯ ЗАЯВКИ В ЛС
# ============================================

class ApplicationDMView(ui.View):
    def __init__(self, room: CharacterRoom, applicant: discord.Member):
        super().__init__(timeout=None)
        self.room = room
        self.applicant = applicant

    @ui.button(label="✅ Принять", style=discord.ButtonStyle.green)
    async def accept_button(self, interaction: discord.Interaction, button: ui.Button):
        """Кнопка для принятия заявки"""
        await self.room.process_selection(interaction, self.applicant, True)

    @ui.button(label="❌ Отклонить", style=discord.ButtonStyle.red)
    async def reject_button(self, interaction: discord.Interaction, button: ui.Button):
        """Кнопка для отклонения заявки"""
        await self.room.process_selection(interaction, self.applicant, False)


# ============================================
# АВТОМАТИЧЕСКОЕ СОЗДАНИЕ МЕНЮ
# ============================================

async def setup_menu_auto():
    """Автоматически создает меню в канале создать-лобби при запуске бота"""
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name="создать-лобби")
        if not channel:
            print(f"⚠️ Канал «создать-лобби» не найден на сервере {guild.name}")
            continue

        # Удаляем старые сообщения бота в этом канале
        try:
            async for message in channel.history(limit=10):
                if message.author == bot.user:
                    await message.delete()
                    await asyncio.sleep(0.5)
        except:
            pass

        # Создаем меню
        embed = discord.Embed(
            title="🎯 Создание лобби",
            description=(
                "Выберите рейд:\n\n"
                
                ":regional_indicator_z: **Зерка**\n"
                ":regional_indicator_k: **Казерос**\n"
                ":regional_indicator_s: **Собор**\n"
                ":regional_indicator_a: **Армог**\n"
                ":regional_indicator_m: **Мордрум**\n"
                ":regional_indicator_e: **Эгир**"
            ),
            color=discord.Color.gold()
        )
        embed.add_field(
            name="📌 Как это работает?",
            value=(
                "1. Нажмите на кнопку рейда\n"
                "2. Выберите сложность: :regional_indicator_n: Обычный или :regional_indicator_h: Героический\n"
                "3. Введите ваш ник в игре и описание лобби\n"
                "4. Лобби создастся в соответствующем канале\n"
                "5. Участники с нужной ролью смогут подать заявку\n"
                "6. **Заявки приходят в ЛС создателю лобби**"
            ),
            inline=False
        )
        embed.add_field(
            name="⚠️ Важно",
            value=(
                "• Для подачи заявки нужна роль рейда\n"
                "• **Откройте ЛС для получения заявок**"
            ),
            inline=False
        )
        embed.set_footer(text="Выберите рейд, чтобы начать")

        view = CreateLobbyView()

        await channel.send(embed=embed, view=view)
        print(f"✅ Меню создано в канале «создать-лобби» на сервере {guild.name}")


# ============================================
# СЛЭШ-КОМАНДЫ
# ============================================

@bot.tree.command(name="setup_menu", description="Пересоздать меню создания лобби (админ)")
@commands.has_permissions(administrator=True)
async def setup_menu(interaction: discord.Interaction):
    """Пересоздает меню в текущем канале"""
    await interaction.response.defer(ephemeral=True)

    # Удаляем старые сообщения бота
    try:
        async for message in interaction.channel.history(limit=20):
            if message.author == bot.user:
                await message.delete()
                await asyncio.sleep(0.3)
    except:
        pass

    # Создаем новое меню
    embed = discord.Embed(
        title="🎯 Создание лобби для рейда",
        description=(
            "Выберите рейд, для которого хотите создать лобби:\n\n"
            "**Доступные рейды:**\n"
            ":regional_indicator_z: **Зерка**\n"
            ":regional_indicator_k: **Казерос**\n"
            ":regional_indicator_s: **Собор**\n"
            ":regional_indicator_a: **Армог**\n"
            ":regional_indicator_m: **Мордрум**\n"
            ":regional_indicator_e: **Эгир**"
        ),
        color=discord.Color.gold()
    )
    embed.add_field(
        name="📌 Как это работает?",
        value=(
            "1. Нажмите на кнопку рейда\n"
            "2. Выберите сложность: :regional_indicator_n: Обычный или :regional_indicator_h: Героический\n"
            "3. Введите ваш ник в игре и описание лобби\n"
            "4. Лобби создастся в соответствующем канале\n"
            "5. Участники с нужной ролью смогут подать заявку\n"
            "6. **Заявки приходят в ЛС создателю лобби**"
        ),
        inline=False
    )
    embed.add_field(
        name="⚠️ Важно",
        value=(
            "• Для подачи заявки нужна роль рейда\n"
            "• **Откройте ЛС для получения заявок**"
        ),
        inline=False
    )
    embed.set_footer(text="Выберите рейд, чтобы начать")

    view = CreateLobbyView()

    await interaction.channel.send(embed=embed, view=view)
    await interaction.followup.send("✅ Меню пересоздано!", ephemeral=True)


@bot.tree.command(name="close_room", description="Закрыть ваше активное лобби")
async def close_room_command(interaction: discord.Interaction):
    """Закрывает лобби пользователя"""
    creator_id = str(interaction.user.id)

    if creator_id not in active_rooms:
        await interaction.response.send_message(
            "❌ У вас нет активного лобби!",
            ephemeral=True
        )
        return

    room = active_rooms[creator_id]
    await room.close_room()
    await interaction.response.send_message(
        "🔒 Набор закрыт",
        ephemeral=True
    )


@bot.tree.command(name="my_room", description="Показать информацию о вашем лобби")
async def my_room_command(interaction: discord.Interaction):
    """Показывает лобби пользователя"""
    creator_id = str(interaction.user.id)

    if creator_id not in active_rooms:
        await interaction.response.send_message(
            "❌ У вас нет активного лобби!",
            ephemeral=True
        )
        return

    room = active_rooms[creator_id]

    total = len(room.applicants)

    embed = discord.Embed(
        title=f"🏠 Ваше лобби: {room.title}",
        description=room.description or "Нет описания",
        color=discord.Color.blue()
    )
    embed.add_field(name="📁 Канал", value=room.channel.mention, inline=True)
    embed.add_field(name="🎭 Роль", value=room.role.mention, inline=True)
    embed.add_field(name="⚡ Сложность", value=room.difficulty, inline=True)
    embed.add_field(name="📊 Статус", value="🟢 Открыто" if room.is_open else "🔴 Закрыто", inline=True)
    embed.add_field(name="📝 Заявок", value=f"Всего: {total}", inline=False)
    embed.add_field(
        name="📬 Уведомления",
        value="Заявки приходят в личные сообщения",
        inline=False
    )

    view = ui.View()
    if room.main_message:
        view.add_item(ui.Button(label="Перейти к лобби", url=room.main_message.jump_url))

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ============================================
# ЗАПУСК БОТА
# ============================================

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user.name} запущен и готов к работе!')
    print(f'ID бота: {bot.user.id}')

    try:
        synced = await bot.tree.sync()
        print(f"✅ Синхронизировано {len(synced)} слэш-команд")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")

    # Автоматически создаем меню в канале "создать-лобби"
    await setup_menu_auto()

    print('------')


if __name__ == "__main__":
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if not TOKEN:
        print("❌ DISCORD_TOKEN не найден в переменных окружения!")
        exit(1)
    bot.run(TOKEN)
