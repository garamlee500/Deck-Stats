from aqt import mw, gui_hooks
from aqt.deckbrowser import DeckBrowser, DeckBrowserContent, RenderDeckNodeContext
from anki.decks import DeckId, DeckTreeNode
from anki.stats import CardStats
from typing import Any, Sequence, List
import datetime

def get_deck_stats(deck_id: DeckId) -> dict:
    stats={}

    # Get all cards in the deck
    card_ids = mw.col.decks.cids(deck_id, children=True)

    if not card_ids:
        return {'Today':"N/A",
        'Yesterday': "N/A",
        'Last Week': "N/A",
        'Last Month': "N/A",
        'Last Year': "N/A",
        'All': "N/A"
    }

    day_millisecond = 24*3600*1000
    # Assume 4am utc is reset point implementing time zone support is too complicated and is not useful for me
    nextDayReset = datetime.datetime.combine(datetime.datetime.today()+datetime.timedelta(days=1),datetime.time(4)).timestamp() * 1000
    cutOffs = {
        'Today': nextDayReset - day_millisecond,
        'Yesterday': nextDayReset - 2 * day_millisecond,
        'Last Week': nextDayReset - 7 * day_millisecond,
        'Last Month': nextDayReset - 30 * day_millisecond,
        'Last Year': nextDayReset - 365 * day_millisecond,
        'All': 0
    }
    
    for cutoff in cutOffs:
        # For correct retention querying see code used for inprogram stats
        # https://github.com/ankitects/anki/blob/bb7f6bbc776c79f05fd35c60041a6ffdde5bbd2b/rslib/src/stats/graphs/retention.rs#L56
        # Query review history
        reviews = mw.col.db.first(
            f"SELECT COUNT(NULLIF(ease,1)) as passes, COUNT(ease) as total FROM revlog WHERE "
            f"(type = 1 OR "
            f"lastIvl>=1 OR "
            f"lastIvl<= -86400) AND "
            f"ease > 0 AND "
            f"id > {cutOffs[cutoff]} AND "
            f"id < {cutOffs['Today'] if cutoff == 'Yesterday' else nextDayReset} AND "
            f"cid IN {str(tuple(card_ids)) if len(card_ids) > 1 else f'({card_ids[0]})'}"
        )
        if reviews:
            stats[cutoff] = f"{100 * reviews[0] / reviews[1]:.1f}%" if reviews[1] > 0 else "N/A"
        else:
            stats[cutoff] = "N/A"

    return stats


def deck_browser_will_show(deck_browser: DeckBrowser, content: DeckBrowserContent) -> None:
    # """Modify the deck list to include custom columns."""
    # deck_browser._original_render_deck_tree = deck_browser._renderDeckTree
    #
    # def custom_render_deck_tree(nodes: Sequence[Any]) -> str:
    #     """Custom rendering with additional columns."""
    #     # Get original HTML
    #     buf = deck_browser._original_render_deck_tree(nodes)
    #
    #     # Inject custom CSS for new columns
    #     custom_css = """
    #     <style>
    #     .retention-col { min-width: 80px; text-align: center; }
    #     .mature-col { min-width: 60px; text-align: center; }
    #     .young-col { min-width: 60px; text-align: center; }
    #     </style>
    #     """
    #
    #     return custom_css + buf

    #deck_browser._renderDeckTree = custom_render_deck_tree

    # Only want to add extra stat column functions once to hook
    if not hasattr(deck_browser, "_old_render_node"):
        deck_browser._old_render_node = deck_browser._render_deck_node
        def custom_render_deck_node(node: DeckTreeNode, ctx: RenderDeckNodeContext):
            return deck_browser_will_render_deck_node(deck_browser, node, deck_browser._old_render_node(node, ctx))

        deck_browser._render_deck_node= custom_render_deck_node

def deck_browser_will_render_deck_node(deck_browser: DeckBrowser, node: Any, content: Any) -> Any:
    """Add custom statistics to each deck row."""
    deck_id = node.deck_id
    stats = get_deck_stats(deck_id)

    # Add custom columns to the deck row
    custom_html = ""

    for cutoff in stats:
        custom_html+= f"""<td class="retention{cutoff}-col" title="Card Retention Rate - {cutoff}">
            {stats[cutoff]}
        </td>
        """

    # Insert before the gear/options column (last column)
    if '</td>' in content:
        parts = content.rsplit('</td>', 1)
        content = parts[0] + '</td>' + custom_html + parts[1]

    return content


# Register hooks
gui_hooks.deck_browser_will_render_content.append(deck_browser_will_show)

# Note: Anki 2.1.50+ uses different hook system
# For older versions, you may need to monkey-patch DeckBrowser methods directly
