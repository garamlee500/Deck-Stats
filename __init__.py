from pickletools import StackObject

from aqt import mw, gui_hooks
from aqt.deckbrowser import DeckBrowser, DeckBrowserContent, RenderDeckNodeContext
from anki.decks import DeckId, DeckTreeNode
from anki.stats import CardStats
from typing import Any, Sequence, List
import datetime

# Store desired retention to save time
desired_retention_lookup ={}

def create_table_element_HTML(content: str, title: str, colour = None) -> str:
    if colour is None:
        return  f"<td title=\"{title}\" class='zero-count' col>{content}</td>"
    else:
        # colo(u)r is the correct spelling
        return  f"<td title=\"{title}\" style=\"color:{colour}\" col>{content}</td>"


def get_colour(accuracy: float, deck_id: DeckId) -> str:
    if deck_id in desired_retention_lookup:
        desired_retention = desired_retention_lookup[deck_id]
    else:
        deck = mw.col.decks.get(deck_id)
        if not deck:
            return "green"

        config = mw.col.decks.config_dict_for_deck_id(deck_id)

        # Default retention is 0.9
        desired_retention = config.get('desiredRetention', 0.9)
        desired_retention_lookup[deck_id] = desired_retention


    # If retention below a certain point we just say its unacceptable and give it a red
    retention_crit_point = 0.8 * desired_retention


    if accuracy == 1:
        return f"rgb(0,255,255)"
    elif accuracy > desired_retention:
        # Green if exactly desired cyan if 100%
        return (f"rgb(0,255,"
                f"{255*(accuracy-desired_retention)/(1-desired_retention)})")
    elif accuracy == desired_retention:
        return f"rgb(0,255,0)"


    elif accuracy > (desired_retention+retention_crit_point)/2:
        return (f"rgb({2*255*(desired_retention-accuracy)/(desired_retention-retention_crit_point)},"
                f"255,0)")

    # hit yellow halfway between desired and bottom worst case

    elif accuracy == (desired_retention+retention_crit_point)/2:
        return f"rgb(255,255,00)"


    elif accuracy > retention_crit_point:
        # Gradient from green to red for accuracy to crit point
        return (f"rgb(255,"
                f"{2*255*(accuracy-retention_crit_point)/(desired_retention-retention_crit_point)},0)")

    else:
        # You're cooked
        return f"rgb(255,0,0)"



def get_deck_stats(deck_id: DeckId) -> str:
    # Get all cards in the deck
    card_ids = mw.col.decks.cids(deck_id, children=True)
    result = ""

    if not card_ids:
        for cutoff in ["Today", "Yesterday", "Last Week", "Last Year", "All"]:
            result +=  create_table_element_HTML("N/A", f"Card Retention Rate - {cutoff}")

        return result

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
        if reviews and reviews[1] > 0:

            accuracy = reviews[0] / reviews[1]
            result +=  create_table_element_HTML(f"{100 * accuracy:.1f}%",
                                                 f"Card Retention Rate - {cutoff}",
                                                 get_colour(accuracy, deck_id))
        else:
            result += create_table_element_HTML("N/A", f"Card Retention Rate - {cutoff}")

    return result


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
    custom_html = get_deck_stats(deck_id)

    # Insert before the gear/options column (last column)
    if '</td>' in content:
        parts = content.rsplit('</td>')
        content = '</td>'.join(parts[0:4] + [custom_html] + parts[4:])

    return content


# Register hooks
gui_hooks.deck_browser_will_render_content.append(deck_browser_will_show)
