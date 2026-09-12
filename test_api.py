import requests
import json

url = "https://api.tgju.org/v1/widget/tmp"

keys = [
    "price_dollar_rl",
    "price_eur",
    "geram18",
    "geram24",
    "sekeb",
    "nim",
    "rob",
    "ons",
    "usdt",
    "tether",
    "bitcoin",
    "btc"
]

params = {
    "keys": ",".join(keys)
}

response = requests.get(url, params=params, timeout=10)

print("Status Code:", response.status_code)
print("\nURL:")
print(response.url)

try:
    data = response.json()

    indicators = data["response"]["indicators"]

    print("\n========== RESULTS ==========\n")

    for item in indicators:
        print(f"Key: {item['name']}")
        print(f"Title: {item['title']}")
        print(f"Price: {item['p']}")
        print(f"Change: {item['d']}")
        print(f"Change %: {item['dp']}")
        print(f"Updated: {item['updated_at']}")
        print("-" * 40)

except Exception as e:
    print("\nERROR:")
    print(e)

    print("\nRAW RESPONSE:")
    print(response.text[:5000])