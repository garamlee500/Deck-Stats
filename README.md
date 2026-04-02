# Deck Stats package for Anki
Anki package to view true retention rate for each deck in main menu
![img.png](img.png)
### TODO:
- Add column labels
- Add more/configurable stats
- Optimise code - lots of query reuse going on - store totals during session?
    - Also query is very inefficient as loads all card ids for each deck then matches against it
- Button to view stats for that deck?