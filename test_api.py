import time
import json
import requests

t0 = time.time()
print("Sending request to API...")
try:
    r = requests.post("http://127.0.0.1:8000/api/chat", json={
        "messages": [{"role": "user", "content": "What is VO2 max according to the newly added Wikipedia data, and how do I improve it?"}]
    }, stream=True)

    first_byte = None
    for chunk in r.iter_lines():
        if not chunk:
            continue
        if first_byte is None:
            first_byte = time.time()
            print(f"\n[Time to first byte: {first_byte - t0:.2f}s]")
            
        data_str = chunk.decode().replace('data: ', '')
        if data_str == '[DONE]':
            break
        try:
            data = json.loads(data_str)
            if data.get('type') == 'metadata':
                print("Sources:", [s['type'] for s in data.get('sources', [])])
            elif data.get('type') == 'content':
                print(data['text'], end='', flush=True)
        except Exception:
            pass

    print(f"\n[Total time: {time.time() - t0:.2f}s]")
except Exception as e:
    print("Error:", e)
