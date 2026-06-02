from openai import OpenAI
from dotenv import load_dotenv

import tempfile
import requests
import os


load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


async def baixar_audio_telegram(
    bot,
    file_id
):

    arquivo = await bot.get_file(file_id)

    url = arquivo.file_path

    resposta = requests.get(url)

    temp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".ogg"
    )

    temp.write(resposta.content)
    temp.close()

    return temp.name


def transcrever_audio(
    caminho_audio
):

    try:

        with open(caminho_audio, "rb") as audio:

            transcricao = (
                client.audio.transcriptions.create(
                    model="gpt-4o-mini-transcribe",
                    file=audio
                )
            )

        return transcricao.text

    except Exception as erro:

        return (
            f"Erro ao transcrever áudio: "
            f"{erro}"
        )