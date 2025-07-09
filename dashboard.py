import os
import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, Input, Output, dash_table
import dash_bootstrap_components as dbc
from flask_caching import Cache
import time
import pandas.api.types as ptypes

# --- Carregamento de dados ---
def load_data():
    this_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(this_dir, 'arquivos_csv')
    all_files = []
    for root, _, files in os.walk(data_dir):
        for f in files:
            if f.lower().endswith('.csv'):
                all_files.append(os.path.join(root, f))
    dfs = []
    for fp in all_files:
        try:
            df = pd.read_csv(fp, sep=';', decimal=',', encoding='latin-1')
        except Exception as e:
            print(f"Erro ao ler arquivo {fp}: {e}. Tentando outro formato...")
            try:
                df = pd.read_csv(fp, sep=',', decimal='.', encoding='utf-8', errors='ignore')
            except Exception as e2:
                print(f"Erro ao ler arquivo {fp} no formato alternativo: {e2}. Pulando este arquivo.")
                continue # Pula para o próximo arquivo
        # marca pasta de origem (ano)
        df['source_folder'] = os.path.basename(os.path.dirname(fp))
        # converte colunas de data
        for col in df.columns:
            if 'data' in col.lower():
                df[col] = pd.to_datetime(df[col], errors='coerce')
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

# dados carregados globalmente
start_load_time = time.time()
df_data = load_data()
load_time = time.time() - start_load_time
print(f"Tempo para carregar os dados: {load_time:.2f} segundos")

if not df_data.empty:
    # Converte colunas com muitos valores repetidos para 'category'
    for col in df_data.columns:
        if df_data[col].nunique() < len(df_data) / 10: # Critério: menos de 10% de valores únicos
            try:
                df_data[col] = df_data[col].astype('category')
            except Exception as e:
                print(f"Aviso: Não foi possível converter coluna '{col}' para 'category': {e}")
    print("Colunas convertidas para 'category' para otimização.")
else:
    print("Aviso: DataFrame df_data está vazio após o carregamento.")

# detecta coluna que identifica o fundo (CNPJ ou código)
fundo_id_col = next((c for c in df_data.columns if 'cnpj' in c.lower() or 'fundo' in c.lower()), None)
if fundo_id_col:
     try:
        df_data[fundo_id_col] = df_data[fundo_id_col].astype('category')
        print(f"Coluna de ID do fundo '{fundo_id_col}' convertida para 'category'.")
     except Exception as e:
        print(f"Nao foi possivel converter a coluna '{fundo_id_col}' para category:", e)


# debug: print no console
def debug_console():
    dirs = os.listdir(os.path.join(os.path.dirname(__file__), 'arquivos_csv'))
    print(f"DEBUG: registros={len(df_data)}, date_cols={[c for c in df_data.columns if 'data' in c.lower()]}, fundo_id_col={fundo_id_col}, unique fundos={len(df_data[fundo_id_col].unique()) if fundo_id_col else 0}, anos={[c for c in dirs]}")

debug_console()

# configura Dash e cache
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
# cache = Cache(app.server, config={'CACHE_TYPE': 'simple'}) # Desativando o cache
TIMEOUT = 60  # segundos

# opções de filtro iniciais
date_cols = [c for c in df_data.columns if 'data' in c.lower()]
fundos = sorted(df_data[fundo_id_col].dropna().unique()) if fundo_id_col else []

# Tenta extrair anos dos nomes das pastas, tratando erros e casos onde o nome não segue o padrão esperado
years = []
data_dir = os.path.join(os.path.dirname(__file__), 'arquivos_csv')
for folder in os.listdir(data_dir):
    if folder.startswith("inf_trimestral_fii_"):  # Garante que só processa pastas relevantes
        try:
            year = int(folder.split("_")[-1]) # Extrai o ano corretamente
            years.append(year)
        except (ValueError, IndexError):
            # Lidar com pastas que não seguem o padrão 'inf_trimestral_fii_ANO'
            print(f"Aviso: Pasta '{folder}' não segue o padrão 'inf_trimestral_fii_ANO' e será ignorada para filtro de ano.")
            pass  # Ignora pastas que não seguem o padrão
years = sorted(list(set(years))) # Remove duplicatas e ordena
print(f"Anos detectados: {years}")

# layout
app_layout = dbc.Container(fluid=True, children=[
    dbc.Row([
        dbc.Col(md=3, children=[ # Use md para telas médias e grandes
            html.H2('Filtros'),
            html.Label('Coluna de Data'),
            dcc.Dropdown(
                id='date-col-dropdown',
                options=[{'label': c, 'value': c} for c in date_cols],
                value=date_cols[0] if date_cols else None
            ),
            html.Br(),
            html.Label('Fundos'),
            dcc.Dropdown(
                id='fundos-dropdown',
                options=[{'label': f, 'value': f} for f in fundos],
                value=[],  # Inicialmente, nenhum fundo selecionado
                multi=True
            ),
            html.Br(),
            html.Label('Ano'),
            dcc.Dropdown(
                id='ano-dropdown',
                options=[{'label': y, 'value': y} for y in years],
                value=years[-1] if years else None # Seleciona o ano mais recente por padrão
            ),
        ]),
        dbc.Col(md=9, children=[ # Use md para telas médias e grandes
            html.H1('Dashboard Dinâmico de FIIs'),
            html.Hr(),
            html.P(f"DEBUG UI: registros={len(df_data)}, date_cols={len(date_cols)}, fundos={len(fundos)}, anos={years}", style={'color':'gray','fontSize':'0.8em'}),
            html.Div(id='dashboard-content')
        ])
    ])
])
app.layout = app_layout

#@cache.memoize(timeout=TIMEOUT) # removendo o cache para teste
def filter_data(date_col, fundos_key, ano_sel):
    start_time = time.time()
    print(f"filter_data: date_col={date_col}, fundos_key={fundos_key}, ano_sel={ano_sel}")
    df = df_data.copy()
    print(f"filter_data: Tamanho do DataFrame original: {len(df)}")

    if fundos_key:
        selected_fundos = fundos_key.split(',')
        print(f"filter_data: Número de fundos selecionados: {len(selected_fundos)}")
        if fundo_id_col:
            print(f"filter_data: Coluna de ID do fundo: {fundo_id_col}")
            df = df[df[fundo_id_col].isin(selected_fundos)]
            print(f"filter_data: Tamanho do DataFrame após filtro de fundos: {len(df)}")
        else:
            print("filter_data: Coluna de identificação do fundo não detectada. Filtro de fundos ignorado.")
    else:
        print("filter_data: Nenhum fundo selecionado. Ignorando filtro de fundos.")

    if ano_sel:
        print(f"filter_data: Ano selecionado: {ano_sel}")
        df = df[df['source_folder'].str.endswith(str(ano_sel))]
        print(f"filter_data: Tamanho do DataFrame após filtro de ano: {len(df)}")

    end_time = time.time()
    total_time = end_time - start_time
    print(f"filter_data: Tempo total para executar a função: {total_time:.2f} segundos")
    print(f"filter_data: Tamanho do DataFrame final: {len(df)}")
    return df

@app.callback(
    Output('dashboard-content', 'children'),
    [Input('date-col-dropdown', 'value'),
     Input('fundos-dropdown', 'value'),
     Input('ano-dropdown', 'value')]
)
def update_dashboard(date_col, selected_fundos, selected_year):
    start_time = time.time()
    print(f"update_dashboard: Iniciando com date_col={date_col}, selected_fundos={selected_fundos}, selected_year={selected_year}")

    if df_data.empty:
        return html.Div('Nenhum dado carregado. Verifique arquivos em arquivos_csv/.', className="alert alert-danger")

    if not date_col:
        return html.Div('Selecione uma coluna de data.', className="alert alert-warning")

    # Removendo a validação que forçava a seleção de fundos
    # if not selected_fundos and fundos:
    #    return html.Div('Selecione pelo menos um fundo.', className="alert alert-warning")

    if not selected_year and years:
        return html.Div('Selecione um ano.', className="alert alert-warning")

    fundos_key = ','.join(selected_fundos) if selected_fundos else ''
    print(f"update_dashboard: fundos_key: {fundos_key}")

    print(f"update_dashboard: Chamando filter_data...")
    df = filter_data(date_col, fundos_key, selected_year)
    print(f"update_dashboard: filter_data retornou um DataFrame de tamanho: {len(df)}")

    if df.empty:
        return html.Div("Nenhum dado encontrado com os filtros selecionados.", className="alert alert-info")

    # Exporta o DataFrame para CSV (Removido para focar na performance)
    # output_file = "dados_fii.csv"  # Nome do arquivo CSV
    # df.to_csv(output_file, index=False, encoding='utf-8')
    # print(f"update_dashboard: Dados exportados para {output_file}")

    children = []

    try:  # Bloco try para capturar erros durante a geração dos gráficos
        # Portfólio
        port_metrics = [c for c in df.columns if any(tok in c.upper() for tok in ['CRI','IMOB','ACOES'])]
        if port_metrics:
            children.append(html.H3('Portfólio'))
            for m in port_metrics:
                try:
                    # Converte a coluna para float antes de somar
                    if ptypes.is_categorical_dtype(df[m]):
                        df[m] = df[m].astype('float64')
                        print(f"Coluna {m} convertida para float64") # Debug
                    start_group_time = time.time()
                    tmp = df.groupby(date_col)[m].sum().reset_index()

                    group_time = time.time() - start_group_time
                    print(f"Tempo para agrupar por {m}: {group_time:.2f} segundos")

                    if not tmp.empty:
                        fig = px.line(tmp, x=date_col, y=m, title=f'Evolução de {m}')
                        children.append(dcc.Graph(figure=fig))
                    else:
                        children.append(html.Div(f"Sem dados para {m} com os filtros selecionados.", className="alert alert-secondary"))
                except Exception as e:
                    print(f"Erro ao gerar gráfico de portfólio para {m}: {e}")
                    children.append(html.Div(f"Erro ao gerar gráfico de portfólio para {m}: {e}", className="alert alert-danger"))

        # Financeiro / Operacional
        fin_metrics = [c for c in df.columns if any(tok in c.upper() for tok in ['REC','CUST','VAC','INADIM'])]
        if fin_metrics:
            children.append(html.H3('Financeiro / Operacional'))
            for m in fin_metrics:
                try:
                    # Converte a coluna para float antes de somar
                    if ptypes.is_categorical_dtype(df[m]):
                        df[m] = df[m].astype('float64')
                        print(f"Coluna {m} convertida para float64") # Debug
                    start_group_time = time.time()
                    tmp = df.groupby(date_col)[m].sum().reset_index()
                    group_time = time.time() - start_group_time
                    print(f"Tempo para agrupar por {m}: {group_time:.2f} segundos")
                    if not tmp.empty:
                        fig = px.area(tmp, x=date_col, y=m, title=m)
                        children.append(dcc.Graph(figure=fig))
                    else:
                        children.append(html.Div(f"Sem dados para {m} com os filtros selecionados.", className="alert alert-secondary"))
                except Exception as e:
                    print(f"Erro ao gerar gráfico financeiro para {m}: {e}")
                    children.append(html.Div(f"Erro ao gerar gráfico financeiro para {m}: {e}", className="alert alert-danger"))

        # Qualitativo
        qual_cols = [c for c in df.columns if any(tok in c.upper() for tok in ['MERC','PUBLIC'])]
        children.append(html.H3('Qualitativo'))
        idcol = fundo_id_col if fundo_id_col else df.columns[0]
        if idcol in df.columns and qual_cols:
            try:
                # Remove linhas onde as colunas qualitativas são todas NaN
                df_qual = df[[idcol] + qual_cols].drop_duplicates()
                df_qual = df_qual.dropna(subset=qual_cols, how='all')
                if not df_qual.empty:
                    table = dash_table.DataTable(
                        columns=[{'name': idcol, 'id': idcol}] + [{'name': c, 'id': c} for c in qual_cols],
                        data=df_qual.to_dict('records'),
                        style_table={'overflowX': 'auto'}
                    )
                    children.append(table)
                else:
                    children.append(html.Div('Sem dados qualitativos disponíveis com os filtros selecionados.', className="alert alert-secondary"))
            except Exception as e:
                print(f"Erro ao gerar tabela qualitativa: {e}")
                children.append(html.Div(f"Erro ao gerar tabela qualitativa: {e}", className="alert alert-danger"))
        else:
            children.append(html.Div('Sem dados qualitativos disponíveis.', className="alert alert-secondary"))

    except Exception as e:
        print(f"Erro geral no callback update_dashboard: {e}")
        children.append(html.Div(f"Erro geral no callback update_dashboard: {e}", className="alert alert-danger"))

    end_time = time.time()
    total_time = end_time - start_time
    print(f"Tempo total para executar o callback: {total_time:.2f} segundos")
    return children

if __name__ == '__main__':
    app.run(debug=True)