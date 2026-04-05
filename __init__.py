from pickletools import StackObject

from aqt import mw, gui_hooks
from aqt.deckbrowser import DeckBrowser, DeckBrowserContent, RenderDeckNodeContext
from anki.decks import DeckId, DeckTreeNode
from anki.stats import CardStats
from typing import Any, Sequence, List
import datetime

# Store desired retention to save time
desired_retention_lookup ={}
day_millisecond = 24 * 3600 * 1000
# Assume 4am utc is reset point implementing time zone support is too complicated and is not useful for me
nextDayReset = datetime.datetime.combine(datetime.datetime.today() + datetime.timedelta(days=1),
                                         datetime.time(4)).timestamp() * 1000

cutOffs = {
    'Today': nextDayReset - day_millisecond,
    'Yesterday': nextDayReset - 2 * day_millisecond,
    'Last Week': nextDayReset - 7 * day_millisecond,
    'Last Month': nextDayReset - 30 * day_millisecond,
    'Last Year': nextDayReset - 365 * day_millisecond,
    'All': 0
}



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
    retention_crit_point = 0.9 * desired_retention


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
    result = ""
    for cutoff in cutOffs:
        try:
            passes = passes_by_deck[cutoff][deck_id]
            total = totals_by_deck[cutoff][deck_id]
            if total > 0:
                accuracy = passes / total
                result +=  create_table_element_HTML(f"{100 * accuracy:.1f}%",
                                                     f"Card Retention Rate - {cutoff}",
                                                     get_colour(accuracy, deck_id))
            else:
                result += create_table_element_HTML("N/A", f"Card Retention Rate - {cutoff}")
        except KeyError:
            result += create_table_element_HTML("N/A", f"Card Retention Rate - {cutoff}")

    return result


def deck_browser_will_show(deck_browser: DeckBrowser, content: DeckBrowserContent) -> None:

    # Do one query

    for cutoff in cutOffs:
        # For correct retention querying see code used for inprogram stats
        # https://github.com/ankitects/anki/blob/bb7f6bbc776c79f05fd35c60041a6ffdde5bbd2b/rslib/src/stats/graphs/retention.rs#L56
        # Query review history - this ensures cards only processed once
        # At least per cutoff by now - this could be further optimised wih CTEs
        reviews = mw.col.db.all(
            f"SELECT COUNT(NULLIF(ease,1)) as passes, COUNT(ease) as total, did "
            f"FROM revlog, cards "
            f"WHERE revlog.cid = cards.id AND "
            f"(revlog.type = 1 OR "
            f"lastIvl>=1 OR "
            f"lastIvl<= -86400) AND "
            f"ease > 0 AND "
            f"revlog.id > {cutOffs[cutoff]} AND "
            f"revlog.id < {cutOffs['Today'] if cutoff == 'Yesterday' else nextDayReset} "
            f"GROUP BY did"
        )

        totals_by_subdeck = {}
        passes_by_subdeck = {}
        for passes, total, deck_id in reviews:
            totals_by_subdeck[deck_id] = total
            passes_by_subdeck[deck_id] = passes

        # Need to count up for children too


        tree = mw.col.decks.deck_tree()

        def process_node(node: DeckTreeNode):
            if node.deck_id in totals_by_subdeck:
                passes_by_deck[cutoff][node.deck_id] = passes_by_subdeck[node.deck_id]
                totals_by_deck[cutoff][node.deck_id] = totals_by_subdeck[node.deck_id]
            else:
                totals_by_deck[cutoff][node.deck_id] = 0
                passes_by_deck[cutoff][node.deck_id] = 0
            for child in node.children:
                process_node(child)
                totals_by_deck[cutoff][node.deck_id] += totals_by_deck[cutoff][child.deck_id]
                passes_by_deck[cutoff][node.deck_id] += passes_by_deck[cutoff][child.deck_id]

        process_node(tree)


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
totals_by_deck = {}
passes_by_deck = {}
for cutOff in cutOffs:
    # Initialse dicts
    totals_by_deck[cutOff] = {}
    passes_by_deck[cutOff] = {}