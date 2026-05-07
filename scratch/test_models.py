import anthropic
import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

key = os.getenv("ANTHROPIC_API_KEY")
if not key:
    print("ERROR: ANTHROPIC_API_KEY no encontrada")
    sys.exit(1)

print(f"DEBUG: Key starts with: {key[:10]}...")
print(f"DEBUG: Key length: {len(key)}")

client = anthropic.Anthropic(api_key=key)

try:
    print("Probando claude-3-haiku-20240307...", end=" ", flush=True)
    client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=5,
        messages=[{"role": "user", "content": "Hi"}]
    )
    print("[OK]")
except Exception as e:
    print(f"\n[ERROR DETALLADO]: {e}")
