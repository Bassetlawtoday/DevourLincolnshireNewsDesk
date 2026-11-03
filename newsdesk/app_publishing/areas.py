"""App Publishing area choices based on existing NewsDesk geography."""
from newsdesk.geography.lincolnshire import LINCOLNSHIRE_PLACES

EXCLUDED_SUFFIXES = (" Court", " station")


def available_areas():
    """Return sorted unique geographic labels, excluding non-place source labels."""
    return tuple(sorted({name for name in LINCOLNSHIRE_PLACES
                         if name != "Lincolnshire"
                         and not name.endswith(EXCLUDED_SUFFIXES)
                         and name not in {"Lincoln Central", "Peaks Lane", "Immingham East", "Immingham West"}},
                        key=str.casefold))
