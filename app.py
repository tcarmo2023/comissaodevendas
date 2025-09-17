import streamlit as st
import pandas as pd
from datetime import datetime
import io, re

# ---------------- CONFIG ----------------
try:
    st.set_page_config(page_title="Comissão de Vendas", layout="wide")
except:
    pass

try:
    import pdfplumber
    PDFPLUMBER_OK = True
except ImportError:
    PDFPLUMBER_OK = False
    st.sidebar.error("❌ pdfplumber não instalado")

# ---------------- LISTA FIXA DE CONSULTORES ----------------
CONSULTORES_VALIDOS = {
    "TIAGO FERNANDES DE LIMA": "TIAGO FERNANDES DE LIMA",
    "TARCISIO TORRES DE ANDRADE": "TARCISIO TORRES DE ANDRADE",
    "MARCELO TELES RIBEIRO": "Marcelo Teles Ribeiro",
    "ROSEANE CRUZ": "ROSEANE CRUZ",
    "JOSEZITO SILVA": "JOSEZITO SILVA",
    "NARDIE ARRUDA DA SILVA": "Nardie Arruda da Silva",
    "ELIVALDO SALES SILVA": "Elivaldo Sales Silva",
    "TARCIO HENRIQUE MARIANO DA SILVA": "TARCIO HENRIQUE MARIANO DA SILVA",
    "DAVID MARTINS": "DAVID MARTINS",
    "CAMILA AGUIAR": "Camila Aguiar",
    "SERGIO CARVALHO": "Sergio Carvalho",
    "FRANCISCO SEVERO SILVA": "Francisco Severo Silva",
    "RENATO TAVARES": "RENATO TAVARES",
    "ALINY BITENCOURT DOS REIS LIMA": "ALINY BITENCOURT DOS REIS LIMA",
    "FLAVIO ROGERIO DE ALMEIDA BARBOSA": "Flavio Rogerio de Almeida Barbosa"
}

def normalizar_nome(nome):
    """Mantém apenas nomes da lista fixa"""
    nome_upper = nome.upper().strip()
    for chave, correto in CONSULTORES_VALIDOS.items():
        if chave in nome_upper:
            return correto
    return None  # ❌ ignora se não estiver na lista

# ---------------- EXTRAÇÃO ----------------
def extract_custom_pdf(text, coluna_valor, tipo="pecas"):
    rows = []
    for line in text.splitlines():
        match = re.search(r"(.+?)\s+([\d\.\,]+)", line)
        if match:
            nome = normalizar_nome(match.group(1))
            if not nome:  # ❌ ignora nomes fora da lista
                continue
            valor = match.group(2).replace(".", "").replace(",", ".")
            try:
                valor = float(valor)
            except:
                valor = 0.0
            rows.append({"Consultor": nome, coluna_valor: valor})
    return pd.DataFrame(rows)

def extract_file(file_obj, coluna_valor, tipo="pecas"):
    if file_obj.name.endswith(".pdf") and PDFPLUMBER_OK:
        text = ""
        file_obj.seek(0)
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                except:
                    continue
        return extract_custom_pdf(text, coluna_valor, tipo)
    elif file_obj.name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file_obj)
        df["Consultor"] = df["Consultor"].apply(normalizar_nome)
        return df.dropna(subset=["Consultor"])[["Consultor", coluna_valor]]
    elif file_obj.name.endswith(".csv"):
        df = pd.read_csv(file_obj)
        df["Consultor"] = df["Consultor"].apply(normalizar_nome)
        return df.dropna(subset=["Consultor"])[["Consultor", coluna_valor]]
    else:
        return pd.DataFrame(columns=["Consultor", coluna_valor])

# ---------------- PROCESSAMENTO ----------------
def processar_dados(df_pecas, df_servicos, ano, mes):
    if df_pecas.empty:
        df_pecas = pd.DataFrame(columns=["Consultor", "Peças (R$)"])
    if df_servicos.empty:
        df_servicos = pd.DataFrame(columns=["Consultor", "Serviços (R$)"])

    df = pd.merge(df_pecas, df_servicos, on="Consultor", how="outer").fillna(0)
    df["Total Geral (R$)"] = df["Peças (R$)"] + df["Serviços (R$)"]
    df["Comissão (R$)"] = df["Total Geral (R$)"] * 0.01
    df.insert(0, "Ano", ano)
    df.insert(1, "Mês", mes)
    return df

# ---------------- EXPORTAÇÃO ----------------
def exportar(df, formato):
    buf = io.BytesIO()
    if formato == "Excel":
        df.to_excel(buf, index=False, engine='openpyxl')
        st.download_button(
            "⬇️ Baixar Excel",
            buf.getvalue(),
            "comissao.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        buf.write(df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'))
        st.download_button(
            "⬇️ Baixar CSV",
            buf.getvalue(),
            "comissao.csv",
            mime="text/csv"
        )

# ---------------- INTERFACE ----------------
st.title("📊 Comissão de Vendas")
st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    st.subheader("📄 Arquivo - Peças")
    file_pecas = st.file_uploader("Upload Peças", type=["pdf", "xlsx", "xls", "csv"], key="pecas")
with col2:
    st.subheader("📄 Arquivo - Serviços")
    file_servicos = st.file_uploader("Upload Serviços", type=["pdf", "xlsx", "xls", "csv"], key="servicos")

st.markdown("---")

col3, col4 = st.columns(2)
with col3:
    ano = st.number_input("Ano", min_value=2020, max_value=2100, value=datetime.now().year)
with col4:
    mes = st.selectbox("Mês",
                       ["Janeiro","Fevereiro","Março","Abril","Maio","Junho",
                        "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"],
                       index=datetime.now().month-1)

st.markdown("---")

if file_pecas and file_servicos:
    if st.button("🚀 Processar Arquivos", type="primary"):
        with st.spinner("Processando..."):
            df_pecas = extract_file(file_pecas, "Peças (R$)", "pecas")
            df_servicos = extract_file(file_servicos, "Serviços (R$)", "servicos")
            df_final = processar_dados(df_pecas, df_servicos, ano, mes)

        if not df_final.empty:
            st.subheader("📋 Resultados")

            # 🔎 Busca
            search = st.text_input("Pesquisar consultor:")
            if search:
                df_final = df_final[df_final["Consultor"].str.contains(search, case=False, na=False)]

            # Ordenação
            colunas = df_final.columns.tolist()
            ordem_col = st.selectbox("Ordenar por:", colunas, index=colunas.index("Total Geral (R$)"))
            ordem_tipo = st.radio("Ordem:", ["Decrescente", "Crescente"], horizontal=True)
            asc = True if ordem_tipo == "Crescente" else False
            df_final = df_final.sort_values(ordem_col, ascending=asc)

            # Mostrar tabela
            st.dataframe(df_final, use_container_width=True)

            # Métricas
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Peças", f"R$ {df_final['Peças (R$)'].sum():,.2f}")
            with col2:
                st.metric("Total Serviços", f"R$ {df_final['Serviços (R$)'].sum():,.2f}")
            with col3:
                st.metric("Comissão Total", f"R$ {df_final['Comissão (R$)'].sum():,.2f}")

            # Exportação
            st.subheader("💾 Exportar")
            formato = st.radio("Formato:", ["Excel", "CSV"], horizontal=True)
            exportar(df_final, formato)
        else:
            st.error("❌ Não foi possível processar os dados.")
