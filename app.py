import streamlit as st
import pandas as pd
import pdfplumber
import re

# ==============================
# Lista oficial de consultores (nomes finais)
# ==============================
CONSULTORES_CHAVES = {
    "TIAGO FERNANDES": "TIAGO FERNANDES DE LIMA",
    "TARCISIO TORRES": "TARCISIO TORRES DE ANDRADE",
    "MARCELO TELES": "Marcelo Teles Ribeiro",
    "ROSEANE CRUZ": "ROSEANE CRUZ",
    "JOSEZITO SILVA": "JOSEZITO SILVA",
    "NARDIE ARRUDA": "Nardie Arruda da Silva",
    "ELIVALDO SALES": "Elivaldo Sales Silva",
    "TARCIO HENRIQUE": "TARCIO HENRIQUE MARIANO DA SILVA",
    "DAVID MARTINS": "DAVID MARTINS",
    "CAMILA AGUIAR": "Camila Aguiar",
    "SERGIO CARVALHO": "Sergio Carvalho",
    "FRANCISCO SEVERO": "Francisco Severo Silva",
    "RENATO TAVARES": "RENATO TAVARES",
    "ALINY BITENCOURT": "ALINY BITENCOURT DOS REIS LIMA",
    "FLAVIO ROGERIO": "Flavio Rogerio de Almeida Barbosa",
}

# ==============================
# Função para normalizar nomes
# ==============================
def normalizar_nome(nome):
    nome_upper = nome.upper().strip()

    # tenta chave pelo primeiro + segundo nome
    partes = nome_upper.split()
    if len(partes) >= 2:
        chave = f"{partes[0]} {partes[1]}"
        if chave in CONSULTORES_CHAVES:
            return CONSULTORES_CHAVES[chave]

    return None

# ==============================
# Função para extrair dados do PDF
# ==============================
def extrair_dados_pdf(caminho_pdf):
    dados = []
    with pdfplumber.open(caminho_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if texto:
                for linha in texto.split("\n"):
                    # Regex ajustado: só pega nome + R$ valor (ignora % da 3ª coluna)
                    match = re.search(r"([A-ZÇÉÃÂÊÍÓÚ\s]+)\s+R\$\s?([\d\.\,]+)", linha.upper())
                    if match:
                        nome_raw = match.group(1).title().strip()
                        valor = float(match.group(2).replace(".", "").replace(",", "."))
                        nome = normalizar_nome(nome_raw)
                        if nome:
                            dados.append((nome, valor))
    return dados

# ==============================
# Função para processar arquivos
# ==============================
def processar_arquivos(arquivo_pecas, arquivo_servicos, ano, mes):
    dados_pecas = extrair_dados_pdf(arquivo_pecas) if arquivo_pecas else []
    dados_servicos = extrair_dados_pdf(arquivo_servicos) if arquivo_servicos else []

    # Convertendo em DataFrames
    df_pecas = pd.DataFrame(dados_pecas, columns=["Consultor", "Peças (R$)"])
    df_servicos = pd.DataFrame(dados_servicos, columns=["Consultor", "Serviços (R$)"])

    # Somando valores repetidos
    df_pecas = df_pecas.groupby("Consultor", as_index=False).sum()
    df_servicos = df_servicos.groupby("Consultor", as_index=False).sum()

    # Juntando
    df = pd.merge(df_pecas, df_servicos, on="Consultor", how="outer").fillna(0)

    # Total Geral + Comissão
    df["Total Geral (R$)"] = df["Peças (R$)"] + df["Serviços (R$)"]
    df["Comissão (R$)"] = df["Total Geral (R$)"] * 0.01

    # Adiciona ano e mês
    df.insert(0, "Ano", ano)
    df.insert(1, "Mês", mes)

    return df

# ==============================
# Streamlit UI
# ==============================
st.title("📊 Comissão de Vendas")

col1, col2 = st.columns(2)
with col1:
    arquivo_pecas = st.file_uploader("Upload Peças", type=["pdf"])
with col2:
    arquivo_servicos = st.file_uploader("Upload Serviços", type=["pdf"])

ano = st.number_input("Ano", min_value=2000, max_value=2100, value=2025)
mes = st.selectbox("Mês", ["Janeiro","Fevereiro","Março","Abril","Maio","Junho",
                           "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"])

if st.button("🚀 Processar Arquivos"):
    if arquivo_pecas or arquivo_servicos:
        df = processar_arquivos(arquivo_pecas, arquivo_servicos, ano, mes)
        if not df.empty:
            st.subheader("📋 Resultados")
            st.dataframe(df)

            # Totais
            total_pecas = df["Peças (R$)"].sum()
            total_servicos = df["Serviços (R$)"].sum()
            total_geral = df["Total Geral (R$)"].sum()
            total_comissao = df["Comissão (R$)"].sum()

            st.markdown(f"""
            ### Totais
            - **Total Peças:** R$ {total_pecas:,.2f}
            - **Total Serviços:** R$ {total_servicos:,.2f}
            - **Total Geral:** R$ {total_geral:,.2f}
            - **Comissão Total:** R$ {total_comissao:,.2f}
            """)
        else:
            st.error("❌ Não foi possível extrair dados válidos.")
    else:
        st.warning("⚠️ Envie pelo menos um arquivo PDF.")
