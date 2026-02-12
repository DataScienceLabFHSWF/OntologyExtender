#!/usr/bin/env python3
"""Test Ollama streaming API."""

import json
import httpx

def test_streaming():
    url = "http://localhost:18135/api/generate"

    payload = {
        "model": "llama3.2:3b",
        "prompt": "Say hello world",
        "stream": True,
        "options": {
            "temperature": 0.5,
            "num_predict": 10,
        }
    }

    print("Testing streaming with small model...")
    try:
        with httpx.stream("POST", url, json=payload, timeout=30.0) as resp:
            resp.raise_for_status()
            print("Response started...")
            
            for line in resp.iter_lines():
                if line:
                    print(f"Raw line: {line}")
                    try:
                        data = json.loads(line.decode('utf-8'))
                        print(f"Parsed: {data}")
                        if 'response' in data:
                            chunk = data['response']
                            print(f"Chunk: '{chunk}'", end='', flush=True)
                        
                        if data.get('done', False):
                            print("\nDone!")
                            break
                            
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error: {e}")
                        continue
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_streaming()