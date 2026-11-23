import json
from collections import defaultdict


def main():
    try:
        with open("history.json") as f:
            history = json.load(f)
    except FileNotFoundError:
        return

    counts = defaultdict(int)
    totals = defaultdict(float)
    for row in history:
        account = row.get("account") or "?"
        counts[account] += 1
        try:
            totals[account] += float(row.get("price") or 0)
        except (TypeError, ValueError):
            pass

    for account in sorted(counts):
        print(f"{account}: {counts[account]} ouvertures, {totals[account]:.2f}")


if __name__ == "__main__":
    main()
