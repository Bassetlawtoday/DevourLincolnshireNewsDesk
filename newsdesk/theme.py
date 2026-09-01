"""
NewsDesk Theme
Shared colours, fonts and branding.
"""

from pathlib import Path

# --------------------------------------------------
# Paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LOGO_PATH = PROJECT_ROOT / "assets" / "devour_lincolnshire_logo.png"

# --------------------------------------------------
# Colours
# --------------------------------------------------

APP_BG = "#0f172a"
HEADER_BG = "#111827"
CARD_BG = "#1f2937"
PANEL_BG = "#172033"

BRAND_RED = "#ed3b35"
BRAND_RED_HOVER = "#d6312c"

# Shared colour for non-destructive actions across every NewsDesk surface.
ACTION_BLUE = "#2563eb"
ACTION_BLUE_HOVER = "#1d4ed8"

ACCENT = BRAND_RED
ACCENT_HOVER = BRAND_RED_HOVER

TEXT_PRIMARY = "#f8fafc"
TEXT_SECONDARY = "#cbd5e1"
TEXT_MUTED = "#94a3b8"

BORDER = "#334155"

IMMEDIATE = "#ef4444"
URGENT = "#f97316"
ROUTINE = "#eab308"
SUCCESS = "#22c55e"

# --------------------------------------------------
# Fonts
# --------------------------------------------------

FONT_HERO = ("Arial", 28, "bold")
FONT_TITLE = ("Arial", 25, "bold")
FONT_SUBTITLE = ("Arial", 13)

FONT_CARD_TITLE = ("Arial", 11, "bold")
FONT_CARD_VALUE = ("Arial", 25, "bold")

FONT_BUTTON = ("Arial", 12, "bold")
FONT_STATUS = ("Arial", 11)

# Shared dimensions used by editorial modules and reusable components.
HEADER_HEIGHT = 122
LOGO_SIZE = (92, 92)
CONTROL_HEIGHT = 32
PRIMARY_ACTION_HEIGHT = 42
CLOSE_BUTTON_WIDTH = 90
PANEL_CORNER_RADIUS = 16
CARD_CORNER_RADIUS = 10
STANDARD_BORDER_WIDTH = 1
CARD_HORIZONTAL_PADDING = 12
CARD_VERTICAL_PADDING = 11

# --------------------------------------------------
# Application
# --------------------------------------------------

APP_NAME = "Devour Lincolnshire NewsDesk"

VERSION = "3.0"
