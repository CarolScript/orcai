from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def transcrever_audio(caminho_audio):
    if not caminho_audio or not os.path.exists(caminho_audio):
        return ""

    try:
        with open(caminho_audio, "rb") as audio:
            transcricao = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio,
                language="pt"
            )

        texto = getattr(transcricao, "text", "")

        print("\n====== RESPOSTA OPENAI TRANSCRIÇÃO ======")
        print(transcricao)
        print("=========================================\n")

        return str(texto or "").strip()

    except Exception as erro:
        print("\n====== ERRO TRANSCRIÇÃO OPENAI ======")
        print(erro)
        print("=====================================\n")
        return ""