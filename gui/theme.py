"""
gui/theme.py — UI Color Theme Definitions
"""

# Colors for ttk.Treeview tags
# Each category defines a (light_mode_color, dark_mode_color)
TREEVIEW_COLORS = {
    "keyword": ("#6f42c1", "#a871eb"),       # Purple
    "temporal": ("#198754", "#20c997"),      # Green
    "extension": ("#0d6efd", "#4da3ff"),     # Blue
    "unclassified": ("#fd7e14", "#ffc107"),  # Orange/Yellow
    "skip": ("#6c757d", "#adb5bd"),          # Grey
    "retry_failed": ("#dc3545", "#ff6b6b"),  # Red
    "retry_queued": ("#fd7e14", "#ffc107"),  # Yellow
}

def get_tag_colors(appearance_mode: str) -> dict:
    """Return a mapping of tags to their hex color for the current mode."""
    idx = 1 if appearance_mode.lower() == "dark" else 0
    return {k: v[idx] for k, v in TREEVIEW_COLORS.items()}
