# pyrefly: ignore [missing-import]
from bot.services import claude_service
import json

def test_parse():
    query = "teclado pausa"
    print(f"Probando parse de Claude para: '{query}'")
    try:
        res = claude_service.parse_text_query(query)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    test_parse()
