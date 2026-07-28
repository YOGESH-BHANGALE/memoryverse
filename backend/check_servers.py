import urllib.request

try:
    with urllib.request.urlopen("http://127.0.0.1:8000/docs", timeout=5) as res:
        print("Backend Status:", res.status)
except Exception as e:
    print("Backend check failed:", e)

try:
    with urllib.request.urlopen("http://127.0.0.1:3000", timeout=5) as res:
        print("Frontend Status:", res.status)
except Exception as e:
    print("Frontend check failed:", e)
