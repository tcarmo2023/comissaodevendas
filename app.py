import streamlit as st
import pandas as pd
from datetime import datetime
import pdfplumber
import re
import io
import os

# ==============================
# LISTA DOS VENDEDORES VÁLIDOS
# ==============================
VENDEDORES_VALIDOS = [
    "TIAGO FERNANDES DE LIMA",
    "TARCISIO TORRES DE ANDRADE",
    "Marcelo Teles Ribeiro",
    "ROSEANE CRUZ",
    "JOSEZITO SILVA",
    "Nardie Arruda da Silva",
    "Elivaldo Sales Silva",
    "TARCIO HENRIQUE MARIANO DA SILVA",
    "DAVID MARTINS",
    "Camila Aguiar",
    "Sergio Carvalho",
    "Francisco Severo Silva",
    "RENATO TAVARES",
    "ALINY BITENCOURT DOS REIS LIMA",
    "Flavio Rogerio de Almeida Barbosa"
]

# ==============================
# MAPEAMENTO DE PRIMEIRO+SEGUNDO NOME
# ==============================
MAPEAMENTO_NOMES = {
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
    "FLAVIO ROGERIO": "Flavio Rogerio de Almeida Barbosa"
}

# ==============================
# FUNÇÕES
# ==============================
def normalizar_nome(nome):
    nome_upper = nome.upper().strip()
    partes = nome_upper.split()

    # 1 - Tenta primeiro + segundo nome
    if len(partes) >= 2:
        chave = f"{partes[0]} {partes[1]}"
        if chave in MAPEAMENTO_NOMES:
            return MAPEAMENTO_NOMES[chave]

    # 2 - Se vier só o primeiro nome e só existe 1 vendedor com esse nome → usa
    candidatos = [v for v in VENDEDORES_VALIDOS if partes[0] in v.upper()]
    if len(candidatos) == 1:
        return candidatos[0]

    # 3 - Busca exata parcial
    for vendedor in VENDEDORES_VALIDOS:
        if vendedor.upper() in nome_upper or nome_upper in vendedor.upper():
            return vendedor
    
    return None


def extract_text_pdf(file):
    """Extrai o texto bruto do PDF (para debug)"""
    texto_total = []
    with pdfplumber.open(file) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text:
                texto_total.append(f"=== Página {i} ===\n{text}")
    return "\n\n".join(texto_total)


def extract_pecas_pdf(file):
    """Extrai dados do PDF de peças"""
    rows = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    patterns = [
                        r"(.+?)\s+R\$\s*([\d\.\,]+)\s*\%\s*[\d\-\,\.]+",
                        r"(.+?)\s+R\$\s*([\d\.\,]+)",
                        r"(.+?)\s+([\d\.\,]+)\s+\%",
                        r"(.+?)\s+([\d\.\,]+)$"
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, line)
                        if match:
                            nome_bruto = match.group(1).strip()
                            nome_limpo = re.sub(r"\s{2,}", " ", nome_bruto)
                            nome = normalizar_nome(nome_limpo)

                            if nome and nome in VENDEDORES_VALIDOS:
                                valor_str = match.group(2).replace(".", "").replace(",", ".")
                                try:
                                    valor = float(valor_str)
                                    if valor > 0:
                                        rows.append({"Consultor": nome, "Peças (R$)": valor})
                                        break
                                except:
                                    continue

    if rows:
        df = pd.DataFrame(rows)
        df = df.groupby("Consultor", as_index=False).sum(numeric_only=True)
        return df

    return pd.DataFrame(columns=["Consultor", "Peças (R$)"])


def extract_servicos_pdf(file):
    """Extrai dados do PDF de serviços"""
    rows = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    patterns = [
                        r"(.+?)\s+([\d\.\,]+)\s+\d+",
                        r"(.+?)\s+([\d\.\,]+)$"
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, line)
                        if match:
                            nome_bruto = match.group(1).strip()
                            nome_limpo = re.sub(r"\s{2,}", " ", nome_bruto)
                            nome = normalizar_nome(nome_limpo)

                            if nome and nome in VENDEDORES_VALIDOS:
                                valor_str = match.group(2).replace(".", "").replace(",", ".")
                                try:
                                    valor = float(valor_str)
                                    if valor > 0:
                                        rows.append({"Consultor": nome, "Serviços (R$)": valor})
                                        break
                                except:
                                    continue

    if rows:
        df = pd.DataFrame(rows)
        df = df.groupby("Consultor", as_index=False).sum(numeric_only=True)
        return df

    return pd.DataFrame(columns=["Consultor", "Serviços (R$)"])


def processar_dados(df_pecas, df_servicos, ano, mes):
    todos_vendedores = pd.DataFrame({"Consultor": VENDEDORES_VALIDOS})

    if df_pecas.empty:
        df_pecas = pd.DataFrame(columns=["Consultor", "Peças (R$)"])
    if df_servicos.empty:
        df_servicos = pd.DataFrame(columns=["Consultor", "Serviços (R$)"])

    df_pecas_completo = pd.merge(todos_vendedores, df_pecas, on="Consultor", how="left").fillna(0)
    df_servicos_completo = pd.merge(todos_vendedores, df_servicos, on="Consultor", how="left").fillna(0)

    df = pd.merge(df_pecas_completo, df_servicos_completo, on="Consultor", how="outer").fillna(0)
    df["Total Geral (R$)"] = df["Peças (R$)"] + df["Serviços (R$)"]
    df["Comissão (R$)"] = df["Total Geral (R$)"] * 0.01
    df.insert(0, "Ano", ano)
    df.insert(1, "Mês", mes)

    return df.sort_values("Total Geral (R$)", ascending=False)


def exportar(df, formato, filename):
    buf = io.BytesIO()
    if formato == "Excel":
        df.to_excel(buf, index=False, engine="openpyxl")
        st.download_button("⬇️ Baixar Excel", buf.getvalue(), filename,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        buf.write(df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"))
        st.download_button("⬇️ Baixar CSV", buf.getvalue(), filename, mime="text/csv")


def salvar_dados_setembro(df):
    if not os.path.exists("dados_consolidados"):
        os.makedirs("dados_consolidados")
    filename = f"dados_consolidados/consolidado_setembro_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(filename, index=False, engine="openpyxl")
    return filename


# ==============================
# INTERFACE STREAMLIT
# ==============================
st.set_page_config(page_title="Comissão de Vendas", layout="wide")
st.title("📊 Comissão de Vendas")
st.markdown("---")

aba = st.tabs(["🔎 Pré-visualizar PDFs", "📊 Processar Dados"])

with aba[0]:
    st.subheader("Pré-visualização dos PDFs")
    col1, col2 = st.columns(2)
    with col1:
        file_pecas_prev = st.file_uploader("Upload Peças (para visualizar)", type=["pdf"], key="pecas_prev")
        if file_pecas_prev:
            st.text_area("Texto do PDF - Peças", extract_text_pdf(file_pecas_prev), height=400)
    with col2:
        file_servicos_prev = st.file_uploader("Upload Serviços (para visualizar)", type=["pdf"], key="servicos_prev")
        if file_servicos_prev:
            st.text_area("Texto do PDF - Serviços", extract_text_pdf(file_servicos_prev), height=400)

with aba[1]:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📄 Arquivo - Peças")
        file_pecas = st.file_uploader("Upload Peças", type=["pdf"], label_visibility="collapsed", key="pecas_proc")
    with col2:
        st.subheader("📄 Arquivo - Serviços")
        file_servicos = st.file_uploader("Upload Serviços", type=["pdf"], label_visibility="collapsed", key="servicos_proc")

    st.markdown("---")

    col3, col4 = st.columns(2)
    with col3:
        ano = st.number_input("**Ano**", min_value=2020, max_value=2100, value=datetime.now().year)
    with col4:
        mes = st.selectbox("**Mês**",
            ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"],
            index=datetime.now().month - 1)

    st.markdown("---")

    if file_pecas and file_servicos:
        if st.button("🚀 Processar Arquivos", type="primary"):
            with st.spinner("Processando..."):
                df_pecas = extract_pecas_pdf(file_pecas)
                df_servicos = extract_servicos_pdf(file_servicos)
                df_final = processar_dados(df_pecas, df_servicos, ano, mes)

            if not df_final.empty:
                st.subheader("📋 Resultados")
                st.dataframe(df_final, use_container_width=True)

                total_pecas = df_final["Peças (R$)"].sum()
                total_servicos = df_final["Serviços (R$)"].sum()
                total_geral = df_final["Total Geral (R$)"].sum()
                total_comissao = df_final["Comissão (R$)"].sum()

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Peças", f"R$ {total_pecas:,.2f}")
                with col2:
                    st.metric("Total Serviços", f"R$ {total_servicos:,.2f}")
                with col3:
                    st.metric("Total Geral", f"R$ {total_geral:,.2f}")
                with col4:
                    st.metric("Comissão Total", f"R$ {total_comissao:,.2f}")

                st.subheader("💾 Exportar")
                formato = st.radio("Formato:", ["Excel", "CSV"], horizontal=True, key="export_format")
                col_export1, col_export2 = st.columns(2)
                with col_export1:
                    exportar(df_final, formato, f"comissao_{mes}_{ano}.{formato.lower()}")

                if mes == "Setembro":
                    with col_export2:
                        if st.button("💾 Salvar Dados Setembro", type="secondary"):
                            filename = salvar_dados_setembro(df_final)
                            st.success(f"✅ Dados de setembro salvos em: {filename}")
                            st.info("📁 Os dados foram salvos na pasta 'dados_consolidados'")
            else:
                st.error("❌ Não foi possível processar os dados. Verifique se os PDFs têm o formato correto.")
    else:
        st.info("📝 Faça upload dos arquivos PDF de peças e serviços para começar.")
