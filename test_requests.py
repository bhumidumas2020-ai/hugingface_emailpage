import requests

url = "http://192.168.29.252:8000/review"

for i in range(10):
    data = {
        "email": f"user{i}@gmail.com",
        "review": "Amazing food and great service"
    }

    r = requests.post(url, json=data)
    print(r.json())
