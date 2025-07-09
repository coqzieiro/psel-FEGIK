import zipfile
from bs4 import BeautifulSoup
import sys
import io
import os
import requests

# configurando o diretório
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# pasta raiz onde vai ter todas as subpastas dos anos
CAMINHO = os.path.join(BASE_DIR, "arquivos_csv")

BASE_URL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS/"

def lista_arquivos_index():
    """
    retorna lista de nomes de arquivos .zip disponíveis no índice
    """
    resp = requests.get(BASE_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return [
        a["href"]
        for a in soup.find_all("a", href=True)
        if a["href"].lower().endswith(".zip")
    ]

def extrai_zip_para_pasta(zip_bytes, pasta_destino):
    """
    recebe um objeto bytes-io contendo o .zip e extrai tudo em pasta_destino
    """
    with zipfile.ZipFile(zip_bytes) as zf:
        zf.extractall(pasta_destino)

def main():
    # cria a pasta raiz
    os.makedirs(CAMINHO, exist_ok=True)

    print(f"busca na lista de arquivos em {BASE_URL} …")
    arquivos = lista_arquivos_index()
    if not arquivos:
        print("nenhum .zip encontrado, veja a url.")
        sys.exit(1)

    for nome_zip in arquivos:
        # define pasta destino com o mesmo nome do zip
        nome_pasta = nome_zip.replace(".zip", "")
        pasta_destino = os.path.join(CAMINHO, nome_pasta)
        os.makedirs(pasta_destino, exist_ok=True)

        print(f"\n[{nome_pasta}] baixando e extraindo {nome_zip} …")
        url = BASE_URL + nome_zip

        try:
            resp = requests.get(url)
            resp.raise_for_status()

            # carrega o conteúdo do ZIP em memória e extrai diretamente
            zip_bytes = io.BytesIO(resp.content)
            extrai_zip_para_pasta(zip_bytes, pasta_destino)

            print(f"[{nome_pasta}] extraído em {pasta_destino}")
        except Exception as e:
            print(f"[erro] falha ao processar {nome_pasta}: {e}")

if __name__ == "__main__":
    main()