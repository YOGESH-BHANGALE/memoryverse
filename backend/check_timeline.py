import requests, json, time
time.sleep(4)
r = requests.get('http://127.0.0.1:8000/api/timeline/default')
data = r.json()
milestones = data.get('milestones', [])
print(f'Total milestones: {len(milestones)}')
for m in milestones:
    print(f"  - [{m['category']}] {m['title']} (date={m['date']})")
