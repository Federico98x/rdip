import requests

r = requests.get("http://localhost:8000/v1/trending/technology", params={"period": "week", "limit": 5})
print("Status:", r.status_code)
print("Response:", r.text[:1500] if len(r.text) > 1500 else r.text)
