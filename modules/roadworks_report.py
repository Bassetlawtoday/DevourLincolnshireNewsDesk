import customtkinter as ctk


WINDOW_BG = "#0f172a"
PANEL_BG = "#1f2937"
CARD_BG = "#111827"
ACCENT = "#2563eb"
TEXT_PRIMARY = "#f8fafc"
TEXT_SECONDARY = "#cbd5e1"
MUTED_TEXT = "#94a3b8"
SUCCESS = "#22c55e"
WARNING = "#f59e0b"


class RoadworksReportWindow:
    """
    Native editorial briefing for Roadworks and Travel Intelligence.
    """

    def __init__(self, parent, report_data=None):
        self.parent = parent
        self.report_data = report_data or {}

        self.window = ctk.CTkToplevel(parent)
        self.window.title("Roadworks and Travel Editor's Briefing")
        self.window.geometry("1180x780")
        self.window.minsize(900, 650)
        self.window.configure(fg_color=WINDOW_BG)

        self.build()

        self.window.after(100, self.window.lift)
        self.window.after(150, self.window.focus_force)

    def build(self):
        header = ctk.CTkFrame(
            self.window,
            fg_color=CARD_BG,
            corner_radius=0,
            height=96,
        )
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="🚧 Roadworks and Travel Editor's Briefing",
            font=("Arial", 28, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=28, pady=(18, 2))

        ctk.CTkLabel(
            header,
            text=(
                "Editorial overview of roadworks, closures and "
                "travel disruption."
            ),
            font=("Arial", 14),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w", padx=30)

        container = ctk.CTkScrollableFrame(
            self.window,
            fg_color=WINDOW_BG,
            corner_radius=0,
        )
        container.pack(fill="both", expand=True, padx=18, pady=18)

        self._build_summary(container)
        self._build_breakdowns(container)
        self._build_top_stories(container)
        self._build_watchlist(container)

    def _build_summary(self, parent):
        panel = self._panel(parent, "Current Intelligence")

        grid = ctk.CTkFrame(panel, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 16))

        for column in range(4):
            grid.grid_columnconfigure(column, weight=1, uniform="summary")

        summary = self._dictionary(
            self.report_data.get("editorial_summary")
        )

        total = self._number(
            self.report_data.get(
                "total_records",
                self.report_data.get("applications_processed", 0),
            )
        )

        newsworthy = self._number(
            self.report_data.get("newsworthy_stories", 0)
        )

        front_page = self._number(
            summary.get(
                "front_page",
                self.report_data.get("front_page_candidates", 0),
            )
        )

        closures = self._number(
            self.report_data.get("road_closures", 0)
        )

        cards = (
            ("Records", total, "Downloaded"),
            ("Newsworthy", newsworthy, "Potential stories"),
            ("High Priority", front_page, "Major disruption"),
            ("Closures", closures, "Full road closures"),
        )

        for column, (label, value, note) in enumerate(cards):
            card = ctk.CTkFrame(
                grid,
                fg_color=CARD_BG,
                corner_radius=10,
            )
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=6,
                pady=4,
            )

            ctk.CTkLabel(
                card,
                text=str(value),
                font=("Arial", 30, "bold"),
                text_color=SUCCESS if value else TEXT_PRIMARY,
            ).pack(pady=(15, 1))

            ctk.CTkLabel(
                card,
                text=label,
                font=("Arial", 15, "bold"),
                text_color=TEXT_PRIMARY,
            ).pack()

            ctk.CTkLabel(
                card,
                text=note,
                font=("Arial", 12),
                text_color=MUTED_TEXT,
            ).pack(pady=(2, 15))

    def _build_breakdowns(self, parent):
        panel = self._panel(parent, "Disruption Breakdown")

        grid = ctk.CTkFrame(panel, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 16))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="breakdown")

        categories = self._rows(
            self.report_data.get("category_breakdown")
        )
        areas = self._rows(
            self.report_data.get("area_breakdown")
        )

        self._breakdown_card(
            grid,
            "By Disruption Type",
            categories,
            row=0,
            column=0,
        )

        self._breakdown_card(
            grid,
            "By Area",
            areas,
            row=0,
            column=1,
        )

    def _breakdown_card(
        self,
        parent,
        title,
        rows,
        row,
        column,
    ):
        card = ctk.CTkFrame(
            parent,
            fg_color=CARD_BG,
            corner_radius=10,
        )
        card.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=6,
            pady=4,
        )

        ctk.CTkLabel(
            card,
            text=title,
            font=("Arial", 16, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=14, pady=(13, 8))

        if not rows:
            ctk.CTkLabel(
                card,
                text="No data available yet.",
                font=("Arial", 13),
                text_color=MUTED_TEXT,
            ).pack(anchor="w", padx=14, pady=(0, 16))
            return

        for label, value in rows[:8]:
            row_frame = ctk.CTkFrame(
                card,
                fg_color="transparent",
            )
            row_frame.pack(fill="x", padx=14, pady=3)

            ctk.CTkLabel(
                row_frame,
                text=str(label),
                font=("Arial", 13),
                text_color=TEXT_SECONDARY,
            ).pack(side="left")

            ctk.CTkLabel(
                row_frame,
                text=str(value),
                font=("Arial", 13, "bold"),
                text_color=TEXT_PRIMARY,
            ).pack(side="right")

        ctk.CTkLabel(
            card,
            text="",
            height=7,
        ).pack()

    def _build_top_stories(self, parent):
        panel = self._panel(parent, "Top Story Opportunities")

        stories = self._list(
            self.report_data.get("top_stories")
        )

        if not stories:
            self._empty_message(
                panel,
                "No roadworks stories have been identified yet.",
            )
            return

        for index, story in enumerate(stories[:10], start=1):
            story_data = (
                story if isinstance(story, dict) else {"title": str(story)}
            )

            title = (
                story_data.get("title")
                or story_data.get("description")
                or story_data.get("road")
                or "Untitled roadworks record"
            )

            location = (
                story_data.get("location")
                or story_data.get("town")
                or "Location not specified"
            )

            score = self._number(story_data.get("score", 0))
            severity = story_data.get("severity", "Unrated")

            card = ctk.CTkFrame(
                panel,
                fg_color=CARD_BG,
                corner_radius=9,
            )
            card.pack(fill="x", padx=14, pady=5)

            ctk.CTkLabel(
                card,
                text=f"{index}. {title}",
                font=("Arial", 15, "bold"),
                text_color=TEXT_PRIMARY,
                anchor="w",
                justify="left",
                wraplength=820,
            ).pack(anchor="w", padx=14, pady=(11, 3))

            ctk.CTkLabel(
                card,
                text=(
                    f"{location}  •  Severity: {severity}  "
                    f"•  Score: {score}"
                ),
                font=("Arial", 12),
                text_color=TEXT_SECONDARY,
            ).pack(anchor="w", padx=14, pady=(0, 11))

        ctk.CTkLabel(panel, text="", height=8).pack()

    def _build_watchlist(self, parent):
        panel = self._panel(parent, "Watchlist")

        watchlist = self._list(
            self.report_data.get("watchlist")
        )

        if not watchlist:
            self._empty_message(
                panel,
                "No developing roadworks issues are being watched.",
            )
            return

        for item in watchlist[:12]:
            if isinstance(item, dict):
                text = (
                    item.get("title")
                    or item.get("description")
                    or item.get("location")
                    or str(item)
                )
            else:
                text = str(item)

            ctk.CTkLabel(
                panel,
                text=f"• {text}",
                font=("Arial", 13),
                text_color=TEXT_SECONDARY,
                anchor="w",
                justify="left",
                wraplength=1040,
            ).pack(anchor="w", padx=18, pady=4)

        ctk.CTkLabel(panel, text="", height=10).pack()

    def _panel(self, parent, title):
        panel = ctk.CTkFrame(
            parent,
            fg_color=PANEL_BG,
            corner_radius=12,
        )
        panel.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            panel,
            text=title,
            font=("Arial", 19, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", padx=16, pady=(14, 12))

        return panel

    def _empty_message(self, parent, message):
        ctk.CTkLabel(
            parent,
            text=message,
            font=("Arial", 13),
            text_color=MUTED_TEXT,
        ).pack(anchor="w", padx=18, pady=(0, 18))

    @staticmethod
    def _number(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _dictionary(value):
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _list(value):
        return value if isinstance(value, list) else []

    @staticmethod
    def _rows(value):
        if isinstance(value, dict):
            return list(value.items())

        if not isinstance(value, list):
            return []

        rows = []

        for item in value:
            if isinstance(item, dict):
                label = (
                    item.get("label")
                    or item.get("name")
                    or item.get("area")
                    or item.get("category")
                    or "Unknown"
                )

                count = (
                    item.get("count")
                    or item.get("total")
                    or item.get("value")
                    or 0
                )

                rows.append((label, count))

            elif isinstance(item, (tuple, list)) and len(item) >= 2:
                rows.append((item[0], item[1]))

        return rows


def open_roadworks_report(parent, report_data=None):
    """
    Open the Roadworks and Travel Editor's Briefing.
    """
    return RoadworksReportWindow(parent, report_data)
