import dash
from dash import dcc, html, dash_table, Input, Output, State, callback, ctx, no_update
import dash_bootstrap_components as dbc
import pandas as pd
import tools
import importlib
import plotly.express as px
import os
from datetime import datetime, timedelta
import base64
import io
import glob
import hashlib
import PyPDF2
import re
import json

from dash.dash_table.Format import Format, Scheme
from dash.dependencies import ALL

importlib.reload(tools)

def get_persistent_data_dir():
    """Get the persistent data directory for storing uploaded files"""
    # On Render.com, use /opt/render/project/src/data
    # Locally, use ./data
    if os.environ.get("RENDER"):
        # We're on Render
        data_dir = "/opt/render/project/src/data"
    else:
        # We're running locally
        data_dir = "./data"
    
    # Create the directory if it doesn't exist
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def sync_pdf_files():
    """Sync PDF files from Wedstrijdverslagen to assets/Wedstrijdverslagen"""
    import shutil
    import glob
    
    source_dir = "Wedstrijdverslagen"
    target_dir = "assets/Wedstrijdverslagen"
    
    # Create target directory if it doesn't exist
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    
    # Get all PDF files from source directory
    source_files = glob.glob(os.path.join(source_dir, "*.pdf"))
    
    # Copy each file to target directory
    for source_file in source_files:
        filename = os.path.basename(source_file)
        target_file = os.path.join(target_dir, filename)
        
        # Only copy if target doesn't exist or source is newer
        if not os.path.exists(target_file) or os.path.getmtime(source_file) > os.path.getmtime(target_file):
            shutil.copy2(source_file, target_file)
            print(f"Synced: {filename}")
    
    print(f"PDF sync complete. {len(source_files)} files processed.")

def encode_image(image_path):
    """Encode image to base64 for embedding in HTML"""
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        return f"data:image/png;base64,{encoded_string}"
    except FileNotFoundError:
        print(f"Warning: Image file {image_path} not found")
        return None

# Sync PDF files on startup
sync_pdf_files()

# Global variables to store current data
df_global = None
df_gen_info = None
df_pct_final = None
df_rp_final = None
df_pts_final = None
current_filename = None
available_seasons = []

# Authentication state
is_authenticated = False
ADMIN_PASSWORD = "scrabble2025"  # You can change this password

def hash_password(password):
    """Hash password for comparison"""
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(input_password):
    """Check if input password matches admin password"""
    return hash_password(input_password) == hash_password(ADMIN_PASSWORD)

def assign_smart_game_numbers(df):
    """Assign game numbers intelligently, preserving original positions when possible"""
    if df.empty:
        return df
    
    # Sort by date first
    df = df.sort_values('Datum_dt').copy()
    
    # Get unique dates and their chronological order
    unique_dates = df['Datum_dt'].unique()
    date_to_position = {date: i+1 for i, date in enumerate(unique_dates)}
    
    # Assign game numbers based on chronological position
    df['GameNr'] = df['Datum_dt'].map(date_to_position)
    
    return df

def extract_date_from_pdf_content(pdf_content):
    """Extract date from PDF content using PyPDF2"""
    try:
        # Decode base64 content
        content_type, content_string = pdf_content.split(',')
        decoded = base64.b64decode(content_string)
        
        # Create a temporary file-like object
        pdf_file = io.BytesIO(decoded)
        
        # Read PDF
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        if len(pdf_reader.pages) > 0:
            first_page = pdf_reader.pages[0]
            text = first_page.extract_text()
            
            # Look for date pattern: "Clubwedstrijd - COXHYDE, Koksijde - DD/MM/YYYY"
            # The date is always in DD/MM/YYYY format
            date_pattern = r'Clubwedstrijd - COXHYDE, Koksijde - (\d{2})/(\d{2})/(\d{4})'
            match = re.search(date_pattern, text)
            
            if match:
                day, month, year = match.groups()
                return f"{day}/{month}/{year}"
            
            # Fallback: look for any DD/MM/YYYY pattern
            fallback_pattern = r'(\d{2})/(\d{2})/(\d{4})'
            fallback_match = re.search(fallback_pattern, text)
            
            if fallback_match:
                day, month, year = fallback_match.groups()
                return f"{day}/{month}/{year}"
        
        return None
        
    except Exception as e:
        print(f"Error extracting date from PDF: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_available_pdf_reports():
    """Scan Wedstrijdverslagen folder and return mapping of dates to PDF files"""
    pdf_mapping = {}
    
    # Get persistent data directory
    data_dir = get_persistent_data_dir()
    
    # Check both current directory and persistent data directory
    pdf_dirs = ["Wedstrijdverslagen"]
    persistent_pdf_dir = os.path.join(data_dir, "Wedstrijdverslagen")
    if os.path.exists(persistent_pdf_dir):
        pdf_dirs.append(persistent_pdf_dir)
    
    for pdf_dir in pdf_dirs:
        if not os.path.exists(pdf_dir):
            continue
        
        for filename in os.listdir(pdf_dir):
            if filename.endswith('.pdf'):
                # Parse filename like "zomerwedstrijd 1 van 3-7-25.pdf"
                try:
                    # Extract date part after "van "
                    if "van " in filename:
                        date_part = filename.split("van ")[1].replace('.pdf', '')
                        # Convert to DD/MM/YYYY format
                        if '-' in date_part:
                            day, month, year = date_part.split('-')
                            # Add 20 prefix to year if it's 2 digits
                            if len(year) == 2:
                                year = '20' + year
                            date_str = f"{day.zfill(2)}/{month.zfill(2)}/{year}"
                            # Use full path for the filename
                            full_path = os.path.join(pdf_dir, filename)
                            pdf_mapping[date_str] = full_path
                except Exception as e:
                    continue
    
    return pdf_mapping

def get_summer_highlighting_data():
    """Get highlighting data for summer competition best 5 rule"""
    if df_global is None or df_global.empty:
        return []
    
    highlighting = []
    
    # Get date columns from the pivot table (these are the actual column names in the table)
    # We need to get this from the pivot table that's used in the Ranking Percent table
    try:
        df_rankingpct = tools.make_pivot(df_global, 'Naam', 'Datum', 'Percent')
        date_columns = df_rankingpct.columns.tolist()
    except:
        return []
    
    for _, player_data in df_global.groupby('Naam'):
        games_played = len(player_data)
        
        if games_played <= 5:
            # All games count - no highlighting needed
            continue
        
        # Player has 6+ games, need to identify which 5 count
        game_percentages = (player_data['Totaal'] / player_data['TheoMax'] * 100).fillna(0)
        
        # Get the dates of the best 5 games
        best_5_indices = game_percentages.sort_values(ascending=False).head(5).index
        best_5_dates = player_data.loc[best_5_indices, 'Datum'].tolist()
        
        # Get the dates of games that don't count
        worst_dates = player_data[~player_data.index.isin(best_5_indices)]['Datum'].tolist()
        
        # Add highlighting for games that don't count (gray them out)
        for date in worst_dates:
            if date in date_columns:
                highlighting.append({
                    "if": {
                        "filter_query": f"{{Naam}} = '{player_data['Naam'].iloc[0]}'",
                        "column_id": date
                    },
                    "color": "#999999",  # Gray color for non-counting games
                    "fontStyle": "italic"
                })
    
    return highlighting

def get_available_seasons():
    """Get list of available season files"""
    seasons = []
    
    # Get persistent data directory
    data_dir = get_persistent_data_dir()
    
    # Create a dictionary to track the best version of each file
    file_versions = {}
    
    # Look for regular season files (Globaal YYYY-YYYY.xlsx) in both current dir and data dir
    globaal_files = glob.glob("Globaal *.xlsx") + glob.glob(os.path.join(data_dir, "Globaal *.xlsx"))
    for file in globaal_files:
        # Extract year range from filename
        try:
            filename = os.path.basename(file)  # Get just the filename, not the full path
            year_range = filename.replace("Globaal ", "").replace(".xlsx", "")
            
            # Prioritize persistent data directory over current directory
            if filename not in file_versions or file.startswith(data_dir):
                file_versions[filename] = {
                    "label": f"Seizoen {year_range}",
                    "value": file,  # Keep full path for loading
                    "year_range": year_range
                }
        except:
            continue
    
    # Look for summer files (Zomer YYYY.xlsx) in both current dir and data dir
    zomer_files = glob.glob("Zomer *.xlsx") + glob.glob(os.path.join(data_dir, "Zomer *.xlsx"))
    for file in zomer_files:
        try:
            filename = os.path.basename(file)  # Get just the filename, not the full path
            year = filename.replace("Zomer ", "").replace(".xlsx", "")
            
            # Prioritize persistent data directory over current directory
            if filename not in file_versions or file.startswith(data_dir):
                file_versions[filename] = {
                    "label": f"Zomer {year}",
                    "value": file,  # Keep full path for loading
                    "year": year
                }
        except:
            continue
    
    # Convert dictionary values to list
    seasons = list(file_versions.values())
    
    # Sort by filename for consistent ordering
    seasons.sort(key=lambda x: os.path.basename(x["value"]))
    return seasons

def get_current_season_filename():
    """Determine the current season filename based on today's date"""
    today = datetime.now()
    year = today.year
    month = today.month
    
    if month in [7, 8]:
        # Summer competition
        filename = f'Zomer {year}.xlsx'
    else:
        # Regular season: September (9) to June (6)
        if month >= 9:
            start_year = year
            end_year = year + 1
        else:
            start_year = year - 1
            end_year = year
        filename = f'Globaal {start_year}-{end_year}.xlsx'
    
    # PRIORITY: Check persistent data directory first (most up-to-date)
    data_dir = get_persistent_data_dir()
    persistent_path = os.path.join(data_dir, filename)
    if os.path.exists(persistent_path):
        return persistent_path
    
    # Fall back to current directory
    if os.path.exists(filename):
        return filename
    
    # If file doesn't exist anywhere, return the persistent path for new uploads
    return persistent_path

def load_data_for_season(filename):
    """Load data from a specific season file"""
    global df_global, df_gen_info, df_pct_final, df_rp_final, df_pts_final
    
    if not os.path.exists(filename):
        # No data available
        df_global = pd.DataFrame()
        df_gen_info = pd.DataFrame()
        df_pct_final = pd.DataFrame()
        df_rp_final = pd.DataFrame()
        df_pts_final = pd.DataFrame()
        return
    
    try:
        df_global = pd.read_excel(filename, sheet_name="Globaal")
        df_global['Datum_dt'] = pd.to_datetime(df_global['Datum'], dayfirst=True)
        df_global = df_global.sort_values('Datum_dt').copy()
        
        # Smart game numbering: preserve original positions when possible
        df_global = assign_smart_game_numbers(df_global)
        
        df_global['Datum'] = df_global['Datum_dt'].dt.strftime('%d/%m/%Y')
        
        # Check if this is a summer competition file
        is_summer = filename.startswith('Zomer')
        
        if is_summer:
            # Use special summer percentage calculation
            df_gen_info = tools.calculate_summer_percentage(df_global)
        else:
            # Use regular calculation for regular season
            df_gen_info = tools.give_gen_info(df_global)
        
        df_rankingpct = tools.make_pivot(df_global, 'Naam', 'Datum', 'Percent')
        # Use the appropriate percentage column based on season type
        if current_filename and current_filename.startswith('Zomer'):
            columns_pct = ['Naam', 'Klasse', 'Tot. T. MAX', 'Tot. Score', '% (Alle)', '% (Beste 5)'] 
            df_pct_final = tools.process_final_df(df_gen_info, df_rankingpct, columns_pct, '% (Beste 5)')
        else:
            columns_pct = ['Naam', 'Klasse', 'Tot. T. MAX', 'Tot. Score', '%'] 
            df_pct_final = tools.process_final_df(df_gen_info, df_rankingpct, columns_pct, '%')
        df_rp = tools.make_pivot(df_global, 'Naam', 'Datum', 'RP')
        columns_rp = ['Naam', 'Klasse', 'Gem. RP']
        df_rp_final = tools.process_final_df(df_gen_info, df_rp, columns_rp, 'Gem. RP')
        df_global['Punten'] = df_global['Punten'].astype('int64')
        df_rankingpts = tools.make_pivot(df_global, 'Naam', 'Datum', 'Punten', True)
        columns_rankingpts = ['Naam', 'Klasse', 'Tot. punten']
        df_pts_final = tools.process_final_df(df_gen_info, df_rankingpts, columns_rankingpts, 'Tot. punten')
        
    except Exception as e:
        print(f"Error loading data from {filename}: {e}")
        # Initialize empty dataframes
        df_global = pd.DataFrame()
        df_gen_info = pd.DataFrame()
        df_pct_final = pd.DataFrame()
        df_rp_final = pd.DataFrame()
        df_pts_final = pd.DataFrame()

def load_current_data():
    """Load data from the current season file"""
    global df_global, df_gen_info, df_pct_final, df_rp_final, df_pts_final, current_filename, available_seasons
    
    print("=== Loading Current Data ===")
    
    # Get available seasons
    available_seasons = get_available_seasons()
    print(f"Available seasons: {[s['label'] for s in available_seasons]}")
    
    current_filename = get_current_season_filename()
    print(f"Current filename: {current_filename}")
    
    # PRIORITY: Always check persistent data directory first for current season
    data_dir = get_persistent_data_dir()
    current_season_name = os.path.basename(current_filename)
    persistent_path = os.path.join(data_dir, current_season_name)
    
    print(f"Persistent path: {persistent_path}")
    print(f"Persistent exists: {os.path.exists(persistent_path)}")
    print(f"Current exists: {os.path.exists(current_filename)}")
    
    if os.path.exists(persistent_path):
        # Use the persistent data directory version (most up-to-date)
        filename = persistent_path
        current_filename = persistent_path
        print(f"✓ Using persistent file: {filename}")
    elif os.path.exists(current_filename):
        # Fall back to current directory
        filename = current_filename
        print(f"✓ Using current file: {filename}")
    elif available_seasons:
        # Fall back to first available season
        filename = available_seasons[0]["value"]
        current_filename = filename
        print(f"✓ Using first available season: {filename}")
    elif os.path.exists("Globaal.xlsx"):
        # Final fallback
        filename = "Globaal.xlsx"
        current_filename = "Globaal.xlsx"
        print(f"✓ Using fallback file: {filename}")
    else:
        # No data available
        print("✗ No data files found!")
        df_global = pd.DataFrame()
        df_gen_info = pd.DataFrame()
        df_pct_final = pd.DataFrame()
        df_rp_final = pd.DataFrame()
        df_pts_final = pd.DataFrame()
        return
    
    print(f"Loading data from: {filename}")
    load_data_for_season(filename)

# Load initial data
load_current_data()

# Test Render.com storage on startup
def test_render_storage():
    """Test if Render.com storage is working"""
    print("=== Testing Render.com Storage ===")
    
    is_render = os.environ.get("RENDER")
    print(f"Running on Render: {is_render}")
    
    if is_render:
        data_dir = "/opt/render/project/src/data"
    else:
        data_dir = "./data"
    
    print(f"Data directory: {data_dir}")
    
    try:
        os.makedirs(data_dir, exist_ok=True)
        test_file = os.path.join(data_dir, "startup_test.txt")
        
        with open(test_file, 'w') as f:
            f.write(f"App started at {datetime.now()}")
        
        with open(test_file, 'r') as f:
            content = f.read()
        
        print(f"✓ Storage test successful: {content}")
        os.remove(test_file)
        
    except Exception as e:
        print(f"✗ Storage test failed: {e}")
        print("⚠️  WARNING: Uploaded games may not persist!")

# Run storage test
test_render_storage()

# Sync existing data to persistent storage
def sync_existing_data_to_persistent():
    """Copy existing Excel files to persistent storage if they don't exist there"""
    print("=== Syncing Data to Persistent Storage ===")
    
    data_dir = get_persistent_data_dir()
    
    # Files to sync
    files_to_sync = [
        "Zomer 2025.xlsx",
        "Globaal 2024-2025.xlsx", 
        "Globaal.xlsx"
    ]
    
    for filename in files_to_sync:
        if os.path.exists(filename):
            persistent_path = os.path.join(data_dir, filename)
            
            if not os.path.exists(persistent_path):
                try:
                    import shutil
                    shutil.copy2(filename, persistent_path)
                    print(f"✓ Synced {filename} to persistent storage")
                except Exception as e:
                    print(f"✗ Error syncing {filename}: {e}")
            else:
                print(f"✓ {filename} already exists in persistent storage")

# Sync data on startup
sync_existing_data_to_persistent()

# Member management functions
def load_member_data():
    """Load member data from JSON file or create from Excel if not exists"""
    json_file = "members.json"
    
    if os.path.exists(json_file):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return pd.DataFrame(data)
        except Exception as e:
            print(f"Error loading members.json: {e}")
    
    # If JSON doesn't exist, create sample data
    print("No members.json found, creating sample data")
    sample_members = [
        {'Naam': 'TORREELE Ronald', 'CLUB': 'COXHYDE, Koksijde', 'KLASSE': 'A'},
        {'Naam': 'VANDENBERGHE Riet', 'CLUB': 'COXHYDE, Koksijde', 'KLASSE': 'A'},
        {'Naam': 'FARASYN Kurt', 'CLUB': 'COXHYDE, Koksijde', 'KLASSE': 'A'}
    ]
    df_leden = pd.DataFrame(sample_members)
    
    # Save to JSON for future use
    save_member_data(df_leden)
    return df_leden

def save_member_data(df):
    """Save member data to JSON file"""
    try:
        with open("members.json", 'w', encoding='utf-8') as f:
            json.dump(df.to_dict('records'), f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving members.json: {e}")
        return False

# Load member data
df_leden = load_member_data()
print(f"Loaded {len(df_leden)} members from data source")
if not df_leden.empty:
    print(f"Sample members: {df_leden.head(3).to_dict('records')}")
else:
    print("No member data found - creating sample data for testing")
    # Create some sample data for testing
    sample_members = [
        {'Naam': 'Jan Janssens', 'CLUB': 'COXHYDE, Koksijde', 'KLASSE': 'A'},
        {'Naam': 'Piet Pieters', 'CLUB': 'COXHYDE, Koksijde', 'KLASSE': 'B'},
        {'Naam': 'Marie Maes', 'CLUB': 'COXHYDE, Koksijde', 'KLASSE': 'A'}
    ]
    df_leden = pd.DataFrame(sample_members)
    save_member_data(df_leden)
    print(f"Created sample data with {len(df_leden)} members")

def make_table(df, table_id, title, klasse_filter_id=None):
    if df.empty:
        return html.Div([
            html.H3(title, className="mb-3", style={"color": "#2c3e50"}),
            html.P("Geen data beschikbaar", className="text-muted")
        ])
    
    int_cols = [
        'Tot. T. MAX', 'Tot. Score', 'Tot. punten', 'Wedstrijden', 'Scrabbles',
        "Solo's", 'S.scr', 'Nulscores', 'Tot. beurten', 'Max. scores'
    ]
    float_cols = [col for col in df.columns if pd.api.types.is_float_dtype(df[col]) and col not in int_cols]

    if "Gem. RP" in df.columns:
        df["Gem. RP"] = pd.to_numeric(df["Gem. RP"], errors="coerce").astype(float)

    columns = []
    for col in df.columns:
        if col in int_cols:
            columns.append({
                "name": col,
                "id": col,
                "type": "numeric",
                "format": Format(precision=0, scheme=Scheme.fixed)
            })
        elif col == 'Gem. RP' or col in float_cols or col == '%' or col == '% (Alle)' or col == '% (Beste 5)':
            columns.append({
                "name": col,
                "id": col,
                "type": "numeric",
                "format": Format(precision=2, scheme=Scheme.fixed)
            })
        else:
            columns.append({
                "name": col,
                "id": col,
                "type": "text"
            })

    style_cell = {
        "padding": "8px",
        "fontFamily": "Arial",
        "fontSize": "14px",
        "border": "1px solid #bdc3c7",
        "minWidth": "0px",
        "width": "auto",
        "maxWidth": "180px",
        "whiteSpace": "normal",
    }
    style_cell_conditional = [
        {"if": {"column_id": "Naam"}, "textAlign": "left", "fontWeight": "bold", "width": "240px", "maxWidth": "240px", "whiteSpace": "nowrap"},
        {"if": {"column_id": "Klasse"}, "textAlign": "center", "fontWeight": "bold", "width": "60px"},
    ]
    for col in df.columns:
        if col in int_cols or col in float_cols or col in ['%', '% (Alle)', '% (Beste 5)', 'Gem. RP', 'Tot. punten']:
            style_cell_conditional.append({
                "if": {"column_id": col},
                "textAlign": "right",
                "fontWeight": "bold" if col in ['%', '% (Alle)', '% (Beste 5)', 'Gem. RP', 'Tot. punten'] else "normal"
            })

    style_header = {
        "fontWeight": "bold",
        "backgroundColor": "#2c3e50",
        "color": "white",
        "textAlign": "center",
        "border": "1px solid #34495e",
        "cursor": "pointer !important",
        "userSelect": "none"
    }
    
    # Initialize header conditional styling
    style_header_conditional = [
        {
            "if": {"state": "selected"},
            "backgroundColor": "#34495e",
            "color": "white"
        }
    ]
    style_data_conditional = [
        {"if": {"row_index": "odd"}, "backgroundColor": "#f2f2f2"},
        {"if": {"row_index": "even"}, "backgroundColor": "#fff9c4"},
    ]

    # Add summer rule highlighting for Ranking Percent table
    if table_id == "table-pct" and current_filename and current_filename.startswith('Zomer'):
        # Get the summer highlighting data
        summer_highlighting = get_summer_highlighting_data()
        if summer_highlighting:
            style_data_conditional.extend(summer_highlighting)

    button_group = []
    if klasse_filter_id:
        button_group = [
            dbc.ButtonGroup([
                dbc.Button("A", id=f"{klasse_filter_id}-A", color="primary", outline=True, size="sm", className="me-1"),
                dbc.Button("B", id=f"{klasse_filter_id}-B", color="primary", outline=True, size="sm", className="me-1"),
                dbc.Button("Alle", id=f"{klasse_filter_id}-All", color="secondary", outline=True, size="sm"),
            ], className="mb-3")
        ]

    datatable_kwargs = dict(
        id=table_id,
        columns=columns,
        data=df.to_dict("records"),
        filter_action="native",
        sort_action="native",
        sort_mode="single",
        page_size=25,
        style_cell=style_cell,
        style_cell_conditional=style_cell_conditional,
        style_header=style_header,
        style_header_conditional=style_header_conditional,
        style_data_conditional=style_data_conditional,
        style_table={"width": "100%", "overflowX": "auto"},
        # Ensure sorting works properly
        sort_by=[],
    )
    
    # Add click event for Ranking Percent table
    if table_id == "table-pct":
        datatable_kwargs["active_cell"] = None
        datatable_kwargs["selected_cells"] = []
        
        # Get available PDF reports for clickable headers
        pdf_mapping = get_available_pdf_reports()
        
        # Add clickable styling for date columns that have PDF reports
        for col in df.columns:
            if col in pdf_mapping:
                style_header_conditional.append({
                    "if": {"column_id": col},
                    "cursor": "pointer",
                    "backgroundColor": "#34495e",  # Slightly different color to indicate clickable
                    "color": "#ffffff"
                })

    return html.Div([
        html.H3(title, className="mb-3", style={"color": "#2c3e50"}),
        *button_group,
        dash_table.DataTable(**datatable_kwargs)
    ], className="mb-4")

def make_graphs_tab(df_global):
    if df_global.empty:
        return html.Div([
            html.H3("Grafieken", className="mb-4", style={"color": "#2c3e50"}),
            html.P("Geen data beschikbaar voor grafieken", className="text-muted")
        ])
    
    df_filtered = df_global[~df_global['Naam'].str.upper().eq('MAXIMUM')].copy()
    turn_columns = [col for col in df_filtered.columns if col.startswith('B') and col[1:].isdigit()]

    # 1. Bar chart: Number of players per game (purple)
    players_per_game = df_filtered.groupby('GameNr')['Naam'].nunique().reset_index()
    fig_players = px.bar(
        players_per_game,
        x='GameNr',
        y='Naam',
        text='Naam',
        title='Aantal spelers per wedstrijd',
        labels={'Naam': 'Aantal spelers', 'GameNr': 'Wedstrijdnummer'},
        color_discrete_sequence=['#8e24aa'],
        text_auto=True
    )
    fig_players.update_traces(texttemplate='%{text:.0f}')

    # 2. Bar chart: Theoretical maximum per game
    theo_max_per_game = (
        df_filtered.groupby('GameNr')[turn_columns]
        .max()
        .sum(axis=1)
        .reset_index(name='TheoMax')
    )
    fig_max = px.bar(
        theo_max_per_game,
        x='GameNr',
        y='TheoMax',
        text='TheoMax',
        title='Theoretisch maximum per wedstrijd',
        labels={'TheoMax': 'Theoretisch maximum', 'GameNr': 'Wedstrijdnummer'},
        color_discrete_sequence=['#fbc02d'],
        text_auto=True
    )
    fig_max.update_traces(texttemplate='%{text:.0f}')

    # 3. Line chart: Scores of selected players per game
    player_options = [
        {"label": naam, "value": naam}
        for naam in sorted(df_filtered['Naam'].unique())
    ]

    return html.Div([
        html.H3("Grafieken", className="mb-4", style={"color": "#2c3e50"}),
        dbc.Row([dbc.Col(dcc.Graph(figure=fig_players), md=12)], className="mb-4"),
        dbc.Row([dbc.Col(dcc.Graph(figure=fig_max), md=12)], className="mb-4"),
        html.Div([
            html.Label("Kies spelers (max. 5):", style={"fontWeight": "bold", "marginRight": "10px"}),
            dcc.Dropdown(
                id="score-player-dropdown",
                options=player_options,
                value=[],  # No default selection
                multi=True,
                maxHeight=200,
                placeholder="Selecteer spelers...",
                style={"width": "100%", "marginBottom": "20px"}
            ),
            dcc.Graph(id="score-player-graph")
        ])
    ])

def make_upload_tab():
    return html.Div([
        html.H3("Upload nieuwe uitslag (CSV)", className="mb-4", style={"color": "#2c3e50"}),
        html.Div([
            html.P(f"Huidig bestand: {current_filename if current_filename else 'Geen bestand geselecteerd'}", className="text-muted mb-3"),
            html.P("Upload een CSV-bestand met de uitslag van een nieuwe wedstrijd.", className="mb-3")
        ]),
        dcc.Upload(
            id="upload-csv",
            children=html.Div([
                "Sleep een CSV-bestand hierheen of ",
                html.A("klik om te selecteren")
            ]),
            style={
                "width": "100%",
                "height": "60px",
                "lineHeight": "60px",
                "borderWidth": "1px",
                "borderStyle": "dashed",
                "borderRadius": "5px",
                "textAlign": "center",
                "marginBottom": "20px",
                "backgroundColor": "#f8f9fa"
            },
            multiple=False,
            accept=".csv"
        ),
        html.Div(id="upload-extra-form"),
        html.Div(id="upload-status", className="mt-3"),
        
        # PDF Upload Section
        html.Hr(className="my-4"),
        html.H4("Upload wedstrijdverslag (PDF)", className="mb-3", style={"color": "#2c3e50"}),
        html.P("Upload een PDF-bestand met het wedstrijdverslag. De datum wordt automatisch uit het document gehaald.", className="mb-3"),
        dcc.Upload(
            id="upload-pdf",
            children=html.Div([
                "Sleep een PDF-bestand hierheen of ",
                html.A("klik om te selecteren")
            ]),
            style={
                "width": "100%",
                "height": "60px",
                "lineHeight": "60px",
                "borderWidth": "1px",
                "borderStyle": "dashed",
                "borderRadius": "5px",
                "textAlign": "center",
                "marginBottom": "20px",
                "backgroundColor": "#f8f9fa"
            },
            multiple=False,
            accept=".pdf"
        ),
        html.Div(id="upload-pdf-form"),
        html.Div(id="upload-pdf-status", className="mt-3"),
        
        # Hidden date picker for upload processing
        dcc.DatePickerSingle(
            id='upload-date-picker', 
            display_format='DD/MM/YYYY', 
            placeholder='Selecteer datum',
            style={'display': 'none'}
        ),

    ])

def make_management_tab():
    return html.Div([
        html.H3("Beheer", className="mb-4", style={"color": "#2c3e50"}),
        
        # Game Management Section
        html.H4("🎮 Wedstrijd Beheer", className="mb-3", style={"color": "#2c3e50"}),
        html.P(f"Huidig bestand: {current_filename if current_filename else 'Geen bestand geselecteerd'}", className="text-muted mb-3"),
        
        html.Div([
            html.Label("Selecteer wedstrijd om te verwijderen:", className="mb-2"),
            dcc.Dropdown(
                id="delete-game-dropdown",
                options=[] if df_global.empty else [
                    {"label": f"Wedstrijd {row['GameNr']} - {row['Datum']}", "value": row['GameNr']}
                    for _, row in df_global[['Datum', 'GameNr']].drop_duplicates().sort_values('GameNr').iterrows()
                ],
                placeholder="Kies een wedstrijd...",
                style={"marginBottom": "20px"}
            ),
            html.Button(
                "Verwijder geselecteerde wedstrijd",
                id="delete-game-btn",
                className="btn btn-danger",
                disabled=True
            ),
            html.Div(id="delete-status", className="mt-3")
        ], className="mb-4"),
        
        html.Hr(className="my-4"),
        
        # Member Management Section
        html.H4("👥 Leden Beheer", className="mb-3", style={"color": "#2c3e50"}),
        html.P("Beheer de leden van de club. Je kunt leden toevoegen, verwijderen en hun klasse wijzigen.", className="text-muted mb-3"),
        html.Div([
            html.H6("Hoe te gebruiken:", className="mb-2"),
            html.Ul([
                html.Li("📝 Klik op een naam om deze te bewerken"),
                html.Li("🏢 Klik op de club cel om de hoofdclub te wijzigen"),
                html.Li("📋 Klik op de klasse cel en typ 'A', 'B' of 'C' (hoofdletter)"),
                html.Li("💾 Klik 'Wijzigingen opslaan' om wijzigingen permanent op te slaan"),
                html.Li("🔄 Ververs de pagina om niet-opgeslagen wijzigingen te annuleren"),
                html.Li("🗑️ Klik op het prullenbak-icoon om een lid te verwijderen")
            ], className="text-muted mb-3")
        ]),
        
        html.Div([
            html.Button("Voeg nieuw lid toe", id="add-member-btn", className="btn btn-success me-2"),
            html.Button("Export leden", id="export-members-btn", className="btn btn-info me-2"),
            html.Button("Print leden", id="print-members-btn", className="btn btn-primary me-2", 
                      **{"data-print": "true"}),
            html.Button("Wijzigingen opslaan", id="save-changes-btn", className="btn btn-primary me-2"),
            dcc.Download(id="download-members-xlsx"),
        ], className="mb-3"),
        
        html.Div(id="member-table-container"),
        
        # Add Member Modal
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Nieuw lid toevoegen")),
            dbc.ModalBody([
                dbc.Input(
                    id="new-member-name",
                    placeholder="Naam",
                    className="mb-3"
                ),
                dbc.Input(
                    id="new-member-club",
                    placeholder="Club (bijv. COXHYDE, Koksijde)",
                    className="mb-3"
                ),
                dbc.Select(
                    id="new-member-class",
                    options=[
                        {"label": "Klasse A", "value": "A"},
                        {"label": "Klasse B", "value": "B"},
                        {"label": "Klasse C", "value": "C"}
                    ],
                    value="B",
                    className="mb-3"
                ),
                html.Div(id="add-member-status", className="text-danger mb-3"),
            ]),
            dbc.ModalFooter([
                dbc.Button("Toevoegen", id="confirm-add-member-btn", color="success"),
                dbc.Button("Annuleren", id="cancel-add-member-btn", color="secondary")
            ])
        ], id="add-member-modal", is_open=False),
        
        html.Div(id="member-management-status", className="mt-3")
    ])

def get_season_filename(date_str):
    dt = datetime.strptime(date_str, '%d/%m/%Y')
    year = dt.year
    month = dt.month
    if month in [7, 8]:
        # Summer competition
        filename = f'Zomer {year}.xlsx'
    else:
        # Regular season: September (9) to June (6)
        if month >= 9:
            start_year = year
            end_year = year + 1
        else:
            start_year = year - 1
            end_year = year
        filename = f'Globaal {start_year}-{end_year}.xlsx'
    
    # Use persistent data directory for saving uploaded files
    data_dir = get_persistent_data_dir()
    return os.path.join(data_dir, filename)

app = dash.Dash(__name__, external_stylesheets=[
    dbc.themes.BOOTSTRAP,
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css"
], suppress_callback_exceptions=True, assets_folder='assets')

# Add print styles
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="stylesheet" href="/assets/print.css">
        <script>
            // Add click handlers for print buttons
            document.addEventListener('DOMContentLoaded', function() {
                document.addEventListener('click', function(e) {
                    if (e.target && e.target.getAttribute('data-print')) {
                        window.print();
                    }
                });
                

            });
        </script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

app.layout = dbc.Container([
    html.Div([
        html.H1("Scrabble Koksijde - Rangschikking",
                className="text-center mb-4",
                style={"color": "#2c3e50", "fontWeight": "bold"}),
        html.Hr(className="mb-4"),
    ]),
    dbc.Row([
        dbc.Col([
            html.Label("Selecteer seizoen:", className="mb-2", style={"fontWeight": "bold"}),
            dcc.Dropdown(
                id="season-selector",
                options=available_seasons,
                value=current_filename if current_filename else None,
                placeholder="Kies een seizoen...",
                style={"marginBottom": "20px"}
            )
        ], md=6),
        dbc.Col([
            html.Div(id="current-season-info", className="text-muted")
        ], md=6)
    ], className="mb-4"),
    dbc.Row([
        dbc.Col([
            html.Div([
                html.I(className="fas fa-lock me-2"),
                html.Span("Niet ingelogd", className="text-muted"),
                html.Button("Admin Login", id="admin-login-btn", className="btn btn-sm btn-primary ms-2")
            ], id="admin-status", className="text-end")
        ], md=12)
    ], className="mb-2"),
    dcc.Tabs(id="tabs", value="tab-info", children=[
        dcc.Tab(label="Globaal Overzicht", value="tab-info", className="tab-label"),
        dcc.Tab(label="Ranking Percent", value="tab-pct", className="tab-label"),
        dcc.Tab(label="Ranking RP", value="tab-rp", className="tab-label"),
        dcc.Tab(label="Ranking Punten", value="tab-pts", className="tab-label"),
        dcc.Tab(label="Grafieken", value="tab-graphs", className="tab-label"),
        dcc.Tab(label="Upload", value="tab-upload", className="tab-label", disabled=True),
        dcc.Tab(label="Beheer", value="tab-management", className="tab-label", disabled=True),
    ], className="mb-4"),
    html.Div(id="tab-content"),
    
    # Login Modal
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Admin Login")),
        dbc.ModalBody([
            html.P("Voer het wachtwoord in om toegang te krijgen tot de beheerfuncties:", className="mb-3"),
            dbc.Input(
                id="password-input",
                type="password",
                placeholder="Wachtwoord",
                className="mb-3",
                n_submit=0
            ),
            html.Div(id="login-error", className="text-danger mb-3"),
            dbc.Button("Inloggen", id="login-btn", color="primary", className="me-2"),
            dbc.Button("Annuleren", id="cancel-login-btn", color="secondary")
        ])
    ], id="login-modal", is_open=False),
    
    # Print trigger div (hidden)
    html.Div(id="print-trigger", style={"display": "none"}),
    
], fluid=True, className="mt-4")

@app.callback(
    Output("current-season-info", "children"),
    Input("season-selector", "value")
)
def update_season_info(selected_season):
    if selected_season:
        # Extract season name for display
        if selected_season.startswith("Globaal "):
            year_range = selected_season.replace("Globaal ", "").replace(".xlsx", "")
            return f"Huidig seizoen: {year_range}"
        elif selected_season.startswith("Zomer "):
            year = selected_season.replace("Zomer ", "").replace(".xlsx", "")
            return html.Div([
                f"Huidig seizoen: Zomer {year}",
                html.Br(),
                html.Small("📊 Zomerregel: Beste 5 van 9 wedstrijden voor Ranking Percent", 
                          className="text-info")
            ])
    return "Geen seizoen geselecteerd"

@app.callback(
    Output("tab-content", "children"),
    [Input("tabs", "value"),
     Input("season-selector", "value")],
)
def render_tab(tab, selected_season):
    global df_global, df_gen_info, df_pct_final, df_rp_final, df_pts_final, current_filename
    
    # Load data for selected season if it changed
    if selected_season and selected_season != current_filename:
        current_filename = selected_season
        load_data_for_season(selected_season)
    
    if tab == "tab-info":
        # Get unique games for the current season
        if df_global is not None and not df_global.empty:
            games = df_global[['Datum', 'GameNr']].drop_duplicates().sort_values('GameNr')
            
            # Get available PDF reports
            pdf_mapping = get_available_pdf_reports()
            
            # Filter to only include games that have PDF reports
            game_options = [
                {"label": f"Wedstrijd {row['GameNr']} - {row['Datum']}", "value": row['Datum']}
                for _, row in games.iterrows()
                if row['Datum'] in pdf_mapping
            ]
            
            pdf_section = html.Div([
                html.H4("📄 Wedstrijdverslagen", className="mb-3", style={"color": "#2c3e50"}),
                html.Div([
                    html.Label("Selecteer een wedstrijd om het verslag te bekijken:", className="mb-2"),
                    dcc.Dropdown(
                        id="game-pdf-dropdown",
                        options=game_options,
                        placeholder="Kies een wedstrijd...",
                        style={"marginBottom": "20px"}
                    ),
                    html.Div(id="selected-game-pdf", className="mt-3")
                ])
            ])
        else:
            pdf_section = ""
        
        # Encode the chocolate image
        chocolate_image = encode_image("EAfscw4r9o.png")
        
        return html.Div([
            # Header with chocolate image in upper right corner
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Button("Download Excel", id="download-info-btn", className="btn btn-success me-2"),
                        html.Button("Print", id="print-info-btn", className="btn btn-primary", 
                                  **{"data-print": "true"}),
                    ], className="mb-3"),
                ], md=8),
                dbc.Col([
                    html.Div([
                        html.Img(
                            src=chocolate_image,
                            style={
                                "height": "60px",
                                "width": "auto",
                                "float": "right",
                                "marginTop": "10px"
                            },
                            title="🍫 Solo Achievement - Hoogste score in een beurt en alleen!"
                        ) if chocolate_image else html.Div()
                    ], className="text-end")
                ], md=4)
            ], className="mb-3"),
            dcc.Download(id="download-info-xlsx"),
            make_table(df_gen_info, "table-info", "Globaal Overzicht"),
            pdf_section
        ])
    elif tab == "tab-pct":
        return html.Div([
            html.Div([
                html.Button("Download Excel", id="download-pct-btn", className="btn btn-success me-2"),
                html.Button("Print", id="print-pct-btn", className="btn btn-primary", 
                          **{"data-print": "true"}),
            ], className="mb-3"),
            dcc.Download(id="download-pct-xlsx"),
            make_table(df_pct_final, "table-pct", "Ranking Percent", "filter-pct"),
            html.Div(id="drilldown-content", className="mt-4")
        ])
    elif tab == "tab-rp":
        return html.Div([
            html.Div([
                html.Button("Download Excel", id="download-rp-btn", className="btn btn-success me-2"),
                html.Button("Print", id="print-rp-btn", className="btn btn-primary", 
                          **{"data-print": "true"}),
            ], className="mb-3"),
            dcc.Download(id="download-rp-xlsx"),
            make_table(df_rp_final, "table-rp", "Ranking RP", "filter-rp")
        ])
    elif tab == "tab-pts":
        return html.Div([
            html.Div([
                html.Button("Download Excel", id="download-pts-btn", className="btn btn-success me-2"),
                html.Button("Print", id="print-pts-btn", className="btn btn-primary", 
                          **{"data-print": "true"}),
            ], className="mb-3"),
            dcc.Download(id="download-pts-xlsx"),
            make_table(df_pts_final, "table-pts", "Ranking Punten", "filter-pts")
        ])
    elif tab == "tab-graphs":
        return make_graphs_tab(df_global)
    elif tab == "tab-upload":
        return make_upload_tab()
    elif tab == "tab-management":
        return make_management_tab()
    return "Onbekend tabblad"

# Excel export callbacks for each table
def dataframe_to_xlsx_bytes(df):
    import io
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return output.read()





@app.callback(
    Output("download-info-xlsx", "data"),
    Input("download-info-btn", "n_clicks"),
    prevent_initial_call=True,
)
def download_info(n):
    def writer(buf):
        df_gen_info.to_excel(buf, index=False)
    return dcc.send_bytes(writer, "Globaal_Overzicht.xlsx")

@app.callback(
    Output("download-pct-xlsx", "data"),
    Input("download-pct-btn", "n_clicks"),
    prevent_initial_call=True,
)
def download_pct(n):
    def writer(buf):
        df_pct_final.to_excel(buf, index=False)
    return dcc.send_bytes(writer, "Ranking_Percent.xlsx")

@app.callback(
    Output("download-rp-xlsx", "data"),
    Input("download-rp-btn", "n_clicks"),
    prevent_initial_call=True,
)
def download_rp(n):
    def writer(buf):
        df_rp_final.to_excel(buf, index=False)
    return dcc.send_bytes(writer, "Ranking_RP.xlsx")

@app.callback(
    Output("download-pts-xlsx", "data"),
    Input("download-pts-btn", "n_clicks"),
    prevent_initial_call=True,
)
def download_pts(n):
    def writer(buf):
        df_pts_final.to_excel(buf, index=False)
    return dcc.send_bytes(writer, "Ranking_Punten.xlsx")

@app.callback(
    Output("table-pct", "data"),
    [Input("filter-pct-A", "n_clicks"),
     Input("filter-pct-B", "n_clicks"),
     Input("filter-pct-All", "n_clicks")],
    State("table-pct", "data"),
    prevent_initial_call=True
)
def filter_klasse_pct(n_a, n_b, n_all, current_data):
    ctx = dash.callback_context
    if not ctx.triggered:
        return df_pct_final.to_dict("records")
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if button_id.endswith("-A"):
        return df_pct_final[df_pct_final["Klasse"] == "A"].to_dict("records")
    elif button_id.endswith("-B"):
        return df_pct_final[df_pct_final["Klasse"] == "B"].to_dict("records")
    else:
        return df_pct_final.to_dict("records")

@app.callback(
    Output("table-rp", "data"),
    [Input("filter-rp-A", "n_clicks"),
     Input("filter-rp-B", "n_clicks"),
     Input("filter-rp-All", "n_clicks")],
    State("table-rp", "data"),
    prevent_initial_call=True
)
def filter_klasse_rp(n_a, n_b, n_all, current_data):
    ctx = dash.callback_context
    if not ctx.triggered:
        return df_rp_final.to_dict("records")
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if button_id.endswith("-A"):
        return df_rp_final[df_rp_final["Klasse"] == "A"].to_dict("records")
    elif button_id.endswith("-B"):
        return df_rp_final[df_rp_final["Klasse"] == "B"].to_dict("records")
    else:
        return df_rp_final.to_dict("records")

@app.callback(
    Output("table-pts", "data"),
    [Input("filter-pts-A", "n_clicks"),
     Input("filter-pts-B", "n_clicks"),
     Input("filter-pts-All", "n_clicks")],
    State("table-pts", "data"),
    prevent_initial_call=True
)
def filter_klasse_pts(n_a, n_b, n_all, current_data):
    ctx = dash.callback_context
    if not ctx.triggered:
        return df_pts_final.to_dict("records")
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if button_id.endswith("-A"):
        return df_pts_final[df_pts_final["Klasse"] == "A"].to_dict("records")
    elif button_id.endswith("-B"):
        return df_pts_final[df_pts_final["Klasse"] == "B"].to_dict("records")
    else:
        return df_pts_final.to_dict("records")

@app.callback(
    Output("drilldown-content", "children"),
    Input("table-pct", "active_cell"),
    State("table-pct", "data"),
)
def update_drilldown(active_cell, table_data):
    if not active_cell or not table_data:
        return ""
    
    row_idx = active_cell['row']
    col_idx = active_cell['column']
    if row_idx >= len(table_data) or col_idx >= len(table_data[0]):
        return ""
    
    player_name = table_data[row_idx]['Naam']
    column_name = list(table_data[row_idx].keys())[col_idx]
    
    # Only show drilldown for date columns (not for player name, class, etc.)
    if column_name in ['Naam', 'Klasse', 'Tot. T. MAX', 'Tot. Score', '%']:
        return ""
    
    # Extract date from column name (assuming format like "05/09/2024")
    try:
        date_str = column_name
        # Find the game data for this player and date
        game_data = df_global[(df_global['Naam'] == player_name) & (df_global['Datum'] == date_str)]
        
        if game_data.empty:
            return html.Div(f"Geen data gevonden voor {player_name} op {date_str}.")
        
        # Get the single row for this player and date
        game_row = game_data.iloc[0]
        
        # Get turn columns (B1, B2, B3, etc.) and sort them properly
        turn_columns = [col for col in df_global.columns if col.startswith('B') and col[1:].isdigit()]
        turn_columns.sort(key=lambda x: int(x[1:]))  # Sort by turn number (B1, B2, B3, etc.)
        
        # Filter to only include turns that have data for this player
        available_turns = []
        for turn_col in turn_columns:
            if turn_col in game_row and pd.notna(game_row[turn_col]):
                available_turns.append(turn_col)
        
        # Get maximum scores for each turn from the same game
        # Since MAXIMUM row is removed during processing, we need to get max scores differently
        # Get all data for this specific date/game
        game_data_all = df_global[df_global['Datum'] == date_str]
        
        # Calculate maximum scores for each turn from all players in this game
        max_scores = {}
        for turn_col in turn_columns:
            if turn_col in game_data_all.columns:
                # Get the maximum score for this turn from all players in this game
                max_score = game_data_all[turn_col].max()
                if pd.notna(max_score):
                    max_scores[turn_col] = max_score
        
        # Create turn-by-turn data
        turn_data = []
        for turn_col in available_turns:
            player_score = game_row[turn_col]
            max_score = max_scores.get(turn_col, 0)
            percentage = (player_score / max_score * 100) if max_score > 0 else 0
            
            turn_data.append({
                'Beurt': turn_col,
                'Score': player_score,
                'Max Score': max_score,
                'Percentage': round(percentage, 2)
            })
        
        if not turn_data:
            last_drilldown_turn_data = None
            return html.Div(f"Geen beurtdata gevonden voor {player_name} op {date_str}.")
        
        # Create table
        columns = [
            {"name": "Beurt", "id": "Beurt", "type": "text"},
            {"name": "Score", "id": "Score", "type": "numeric", "format": Format(precision=0, scheme=Scheme.fixed)},
            {"name": "Max Score", "id": "Max Score", "type": "numeric", "format": Format(precision=0, scheme=Scheme.fixed)},
            {"name": "Percentage", "id": "Percentage", "type": "numeric", "format": Format(precision=2, scheme=Scheme.fixed)}
        ]
        
        # Create horizontal bar chart
        df_turns = pd.DataFrame(turn_data)
        beurt_order = [row['Beurt'] for row in turn_data]  # Use the same order as the table
        fig_bar = px.bar(
            df_turns,
            x='Score',
            y='Beurt',
            orientation='h',
            labels={'Score': 'Score', 'Beurt': 'Beurt'},
            color='Percentage',
            color_continuous_scale='RdYlGn',
            text='Score',
            hover_data=['Max Score', 'Percentage']
        )
        fig_bar.update_traces(texttemplate='%{text}', textposition='outside')
        fig_bar.update_layout(
            title_text=None,  # Explicitly clear any title
            xaxis_title="Score",
            yaxis_title="Beurt",
            height=700,
            width=900,
            margin=dict(l=0, r=0, t=0, b=0),  # Remove extra margins for alignment
            yaxis={
                'categoryorder': 'array',
                'categoryarray': beurt_order[::-1]  # Reverse so B1 is at the top
            }
        )
        
        return html.Div([
            # Remove the duplicate title above the graph
            # html.H4(f"Beurten voor {player_name} op {date_str}", className="mb-3"),
            html.Button("Download Beurten (Excel)", id="download-drilldown-btn", className="mb-2 btn btn-success"),
            dcc.Download(id="download-drilldown-xlsx"),
            dbc.Row([
                dbc.Col([
                    dash_table.DataTable(
                        id="drilldown-table",
                        columns=columns,
                        data=turn_data,
                        style_table={"overflowX": "auto"},
                        style_cell={
                            "padding": "8px",
                            "fontFamily": "Arial",
                            "fontSize": "14px",
                            "border": "1px solid #bdc3c7",
                            "textAlign": "center"
                        },
                        style_header={
                            "fontWeight": "bold",
                            "backgroundColor": "#2c3e50",
                            "color": "white",
                            "textAlign": "center"
                        },
                        style_data_conditional=[
                            {"if": {"row_index": "odd"}, "backgroundColor": "#f2f2f2"},
                            {"if": {"row_index": "even"}, "backgroundColor": "#fff9c4"},
                        ]
                    )
                ], md=6, style={"display": "flex", "alignItems": "flex-start"}),
                dbc.Col([
                    dcc.Graph(figure=fig_bar, style={"marginTop": 0, "height": "100%", "marginLeft": "-150px"})
                ], md=6, style={"display": "flex", "alignItems": "flex-start"})
            ])
        ])
        
    except Exception as e:
        return html.Div(f"Fout bij het laden van de data: {e}")

@app.callback(
    Output("score-player-graph", "figure"),
    Input("score-player-dropdown", "value"),
)
def update_score_line_chart(selected_players):
    if df_global.empty:
        return px.line(title="Geen data beschikbaar")
    
    df_filtered = df_global[~df_global['Naam'].str.upper().eq('MAXIMUM')].copy()
    if not selected_players:
        return px.line(title="Selecteer spelers om percentages te tonen")
    
    # Limit to 5 players
    selected_players = selected_players[:5]
    
    # Get turn columns for theoretical max calculation
    turn_columns = [col for col in df_filtered.columns if col.startswith('B') and col[1:].isdigit()]
    
    # Calculate theoretical maximum per game
    theo_max_per_game = (
        df_filtered.groupby('GameNr')[turn_columns]
        .max()
        .sum(axis=1)
        .reset_index(name='TheoMax')
    )
    
    # Filter data for selected players
    df_plot = df_filtered[df_filtered['Naam'].isin(selected_players)].copy()
    
    # Ensure GameNr is the same data type in both dataframes
    df_plot['GameNr'] = df_plot['GameNr'].astype(int)
    theo_max_per_game['GameNr'] = theo_max_per_game['GameNr'].astype(int)
    
    # Merge with theoretical max to calculate percentages
    df_plot = df_plot.merge(theo_max_per_game, on='GameNr', how='left')
    
    # Check if merge was successful
    if 'TheoMax' not in df_plot.columns:
        # Fallback: calculate percentage directly for each game
        df_plot['Percentage'] = 0.0
        for game_nr in df_plot['GameNr'].unique():
            game_data = df_filtered[df_filtered['GameNr'] == game_nr]
            theo_max = game_data[turn_columns].max().sum()
            mask = df_plot['GameNr'] == game_nr
            df_plot.loc[mask, 'Percentage'] = (df_plot.loc[mask, 'Totaal'] / theo_max * 100).round(2)
    else:
        df_plot['Percentage'] = (df_plot['Totaal'] / df_plot['TheoMax'] * 100).round(2)
    
    fig = px.line(
        df_plot,
        x="GameNr",
        y="Percentage",
        color="Naam",
        markers=True,
        title="Percentage van theoretisch maximum per wedstrijd voor geselecteerde spelers",
        labels={"Percentage": "Percentage (%)", "GameNr": "Wedstrijdnummer", "Naam": "Speler"},
    )
    fig.update_traces(mode="lines+markers")
    fig.update_layout(yaxis_tickformat='.2f')
    return fig

@app.callback(
    Output('upload-extra-form', 'children'),
    [Input('upload-csv', 'contents')],
    [State('upload-csv', 'filename')]
)
def handle_csv_upload(contents, filename):
    if contents is None:
        return ''
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    try:
        # Try to read as CSV (semicolon or comma separated)
        try:
            df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), sep=';')
        except Exception:
            df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), sep=',')
    except Exception as e:
        return f'Fout bij het lezen van het CSV-bestand: {e}'

    # Deduce number of turns
    turn_columns = [col for col in df.columns if col.startswith('B') and col[1:].isdigit()]
    num_turns = len(turn_columns)

    # Show preview and date picker
    preview_table = dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in df.columns],
        data=df.head(10).to_dict('records'),
        style_table={"overflowX": "auto", "maxHeight": "300px", "overflowY": "auto"},
        page_size=10
    )
    form = html.Div([
        html.P(f"Aantal beurten (turns) gedetecteerd: {num_turns}"),
        html.Label("Kies de datum van de wedstrijd:"),
        dcc.DatePickerSingle(
            id='upload-date-picker-visible',
            display_format='DD/MM/YYYY',
            placeholder='Selecteer datum',
            style={'marginBottom': '20px'}
        ),
        html.Div(preview_table, style={"marginTop": "20px"})
    ])
    return form

@app.callback(
    Output('upload-status', 'children'),
    [Input('upload-date-picker-visible', 'date')],
    [State('upload-csv', 'contents'), State('upload-csv', 'filename')]
)
def process_upload(date, contents, filename):
    if not date or not contents:
        return ''
    
    # Convert date from ISO to DD/MM/YYYY
    dt = datetime.strptime(date[:10], '%Y-%m-%d')
    date_str = dt.strftime('%d/%m/%Y')
    
    # Read uploaded CSV
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    try:
        try:
            df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), sep=';')
        except Exception:
            df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), sep=',')
    except Exception as e:
        return f'Fout bij het lezen van het CSV-bestand: {e}'
    
    # Use the global member data (loaded from JSON)
    df_leden = load_member_data()
    
    # Always determine the season filename based on the uploaded date
    season_filename = get_season_filename(date_str)
    
    # Check for duplicates and assign volgnummer
    # Load and merge data from both locations to ensure we have all games
    filename_only = os.path.basename(season_filename)
    current_dir_file = filename_only
    persistent_file = season_filename
    
    # Try to load existing data from both locations and merge them
    df_season = None
    df_current = None
    df_persistent = None
    
    # Load from current directory
    if os.path.exists(current_dir_file):
        try:
            df_current = pd.read_excel(current_dir_file, sheet_name='Globaal')
            print(f"Loaded {len(df_current)} rows from current directory")
        except Exception as e:
            print(f"Error reading from current directory: {e}")
    
    # Load from persistent directory
    if os.path.exists(persistent_file):
        try:
            df_persistent = pd.read_excel(persistent_file, sheet_name='Globaal')
            print(f"Loaded {len(df_persistent)} rows from persistent directory")
        except Exception as e:
            print(f"Error reading from persistent directory: {e}")
    
    # Merge data from both locations, prioritizing persistent directory for duplicates
    if df_current is not None and df_persistent is not None:
        # Combine both dataframes, removing duplicates based on date
        df_combined = pd.concat([df_current, df_persistent], ignore_index=True)
        # Remove duplicates based on date, keeping the last occurrence (from persistent)
        df_season = df_combined.drop_duplicates(subset=['Datum'], keep='last')
        print(f"Merged data: {len(df_season)} rows after removing duplicates")
    elif df_current is not None:
        df_season = df_current
        print(f"Using current directory data: {len(df_season)} rows")
    elif df_persistent is not None:
        df_season = df_persistent
        print(f"Using persistent directory data: {len(df_season)} rows")
    
    existing_file_path = persistent_file  # Always use persistent as the target
    
    if df_season is not None:
        # Check if this date already exists
        if (df_season['Datum'] == date_str).any():
            return f'Deze uitslag voor {date_str} werd al ingelezen in {existing_file_path}.'
        # Assign volgnummer as one more than the number of unique dates (sorted chronologically)
        unique_dates = sorted(pd.to_datetime(df_season['Datum'], dayfirst=True).unique())
        volgnummer = len(unique_dates) + 1
    else:
        volgnummer = 1
    
    # Prepare row_wedstrijdinfo
    row_wedstrijdinfo = {'Datum': date_str, 'Beurten': len([col for col in df.columns if col.startswith('B') and col[1:].isdigit()])}
    
    # Process the data
    try:
        df_processed = tools.process_uitgebreid(df, row_wedstrijdinfo, df_leden, volgnummer)
    except Exception as e:
        return f'Fout bij verwerken van de uitslag: {e}'
    
    # Append and save
    if df_season is not None:
        df_new = pd.concat([df_season, df_processed.reset_index()], ignore_index=True)
    else:
        df_new = df_processed.reset_index()
    
    # Apply smart numbering to the new dataset
    df_new['Datum_dt'] = pd.to_datetime(df_new['Datum'], dayfirst=True)
    df_new = assign_smart_game_numbers(df_new)
    
    try:
        # Always save to persistent location first
        df_new.to_excel(season_filename, sheet_name='Globaal', index=False)
        print(f"✓ Saved {len(df_new)} rows to persistent location: {season_filename}")
        
        # Also update the current directory file to keep them in sync
        if os.path.exists(current_dir_file) or len(df_new) > 0:
            df_new.to_excel(current_dir_file, sheet_name='Globaal', index=False)
            print(f"✓ Also saved to current directory: {current_dir_file}")
        
        # Verify the file was actually saved
        if os.path.exists(season_filename):
            print(f"✓ Verified: persistent file exists after save")
            # Check file size
            file_size = os.path.getsize(season_filename)
            print(f"✓ File size: {file_size} bytes")
        else:
            print(f"✗ ERROR: persistent file does not exist after save!")
            
    except Exception as e:
        print(f"✗ Error saving file: {e}")
        return f'Fout bij het opslaan van {season_filename}: {e}'
    
    # Reload data
    load_current_data()
    
    # Get the actual game number that was assigned
    actual_game_nr = df_new[df_new['Datum'] == date_str]['GameNr'].iloc[0]
    
    return f'Uitslag voor {date_str} (wedstrijd {actual_game_nr}) succesvol toegevoegd aan {season_filename}!'

# PDF Upload Callbacks
@app.callback(
    Output('upload-pdf-form', 'children'),
    [Input('upload-pdf', 'contents')],
    [State('upload-pdf', 'filename')]
)
def handle_pdf_upload(contents, filename):
    if contents is None:
        return ''
    
    # Extract date from PDF content
    extracted_date = extract_date_from_pdf_content(contents)
    
    if extracted_date:
        # Show confirmation with extracted date
        return html.Div([
            html.P(f"✅ Datum automatisch gedetecteerd: {extracted_date}", className="text-success mb-2"),
            html.P(f"Bestand: {filename}", className="text-muted mb-2"),
            html.Button(
                "Bevestig upload",
                id="confirm-pdf-upload-btn",
                className="btn btn-primary"
            )
        ])
    else:
        # Show error if automatic extraction failed
        return html.Div([
            html.P("❌ Kon datum niet automatisch detecteren uit het PDF-bestand.", className="text-danger mb-2"),
            html.P("Zorg ervoor dat het PDF-bestand de juiste datum bevat in het formaat: 'Clubwedstrijd - COXHYDE, Koksijde - DD/MM/YYYY'", className="text-muted mb-2"),
            html.P(f"Bestand: {filename}", className="text-muted mb-2")
        ])

@app.callback(
    Output('upload-pdf-status', 'children'),
    [Input('confirm-pdf-upload-btn', 'n_clicks')],
    [State('upload-pdf', 'contents'),
     State('upload-pdf', 'filename')],
    prevent_initial_call=True
)
def process_pdf_upload(n_clicks, contents, filename):
    print(f"PDF upload callback triggered - n_clicks: {n_clicks}, filename: {filename}")
    
    # Prevent processing if no clicks or contents
    if not n_clicks:
        print("No clicks, returning empty")
        return ''
    
    if not contents:
        print("No contents, returning empty")
        return ''
    
    # Prevent multiple processing
    if n_clicks == 0:
        print("Zero clicks, returning empty")
        return ''
    
    # Try to extract date from PDF content first
    print("Extracting date from PDF content...")
    date_str = extract_date_from_pdf_content(contents)
    print(f"Extracted date: {date_str}")
    
    # If automatic extraction failed, we need to handle this differently
    # For now, we'll require automatic extraction to work
    if not date_str:
        print("Date extraction failed")
        return 'Fout: Kon datum niet automatisch detecteren uit het PDF-bestand. Zorg ervoor dat het PDF-bestand de juiste datum bevat.'
    
    # Check if PDF already exists for this date
    pdf_mapping = get_available_pdf_reports()
    print(f"Checking for existing PDF for date: {date_str}")
    print(f"Available PDFs: {list(pdf_mapping.keys())}")
    if date_str in pdf_mapping:
        existing_file = pdf_mapping[date_str]
        print(f"Found existing file: {existing_file}")
        return f'⚠️ Er bestaat al een PDF-verslag voor {date_str} ({existing_file}). Upload geannuleerd.'
    
    # Generate filename based on date (matching existing pattern)
    dt_obj = datetime.strptime(date_str, '%d/%m/%Y')
    
    # Check existing files to determine the next game number
    existing_files = [f for f in os.listdir("Wedstrijdverslagen") if f.endswith('.pdf')]
    
    if dt_obj.month in [7, 8]:
        # Summer competition - find next game number
        summer_files = [f for f in existing_files if f.startswith('zomerwedstrijd')]
        if summer_files:
            # Extract game numbers from existing summer files
            game_numbers = []
            for file in summer_files:
                try:
                    # Extract number from "zomerwedstrijd X van"
                    parts = file.split(' van ')[0].split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        game_numbers.append(int(parts[1]))
                except:
                    continue
            next_game_number = max(game_numbers) + 1 if game_numbers else 1
        else:
            next_game_number = 1
        
        # Summer format: "zomerwedstrijd X van DD-M-YY.pdf"
        filename_new = f"zomerwedstrijd {next_game_number} van {dt_obj.day}-{dt_obj.month}-{str(dt_obj.year)[2:]}.pdf"
        print(f"Generated summer filename: {filename_new} (game number: {next_game_number})")
    else:
        # Regular season - use DD-M-YYYY format like existing files
        filename_new = f"wedstrijd van {dt_obj.day}-{dt_obj.month}-{dt_obj.year}.pdf"
        print(f"Generated regular filename: {filename_new}")
    
    # Save PDF to assets folder
    try:
        # Decode base64 content
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        # Get persistent data directory
        data_dir = get_persistent_data_dir()
        
        # Ensure assets directory exists
        assets_dir = "assets/Wedstrijdverslagen"
        if not os.path.exists(assets_dir):
            os.makedirs(assets_dir)
        
        # Save file to assets (for immediate access)
        pdf_path = os.path.join(assets_dir, filename_new)
        print(f"Saving to assets: {pdf_path}")
        with open(pdf_path, 'wb') as f:
            f.write(decoded)
        
        # Also save to main Wedstrijdverslagen folder for consistency
        main_dir = "Wedstrijdverslagen"
        if not os.path.exists(main_dir):
            os.makedirs(main_dir)
        
        main_pdf_path = os.path.join(main_dir, filename_new)
        print(f"Saving to main: {main_pdf_path}")
        with open(main_pdf_path, 'wb') as f:
            f.write(decoded)
        
        # Save to persistent data directory for long-term storage
        persistent_pdf_dir = os.path.join(data_dir, "Wedstrijdverslagen")
        if not os.path.exists(persistent_pdf_dir):
            os.makedirs(persistent_pdf_dir)
        
        persistent_pdf_path = os.path.join(persistent_pdf_dir, filename_new)
        print(f"Saving to persistent: {persistent_pdf_path}")
        with open(persistent_pdf_path, 'wb') as f:
            f.write(decoded)
        
        # Verify files were saved correctly
        if not os.path.exists(pdf_path):
            return f'❌ Fout: PDF kon niet worden opgeslagen in assets folder'
        if not os.path.exists(main_pdf_path):
            return f'❌ Fout: PDF kon niet worden opgeslagen in hoofdmap'
        if not os.path.exists(persistent_pdf_path):
            return f'❌ Fout: PDF kon niet worden opgeslagen in persistente map'
        
        # Note: PDF mapping will be refreshed on next app load
        print("PDF files saved successfully")
        
        print(f"PDF upload successful: {date_str} -> {filename_new}")
        
        # Add a small delay to prevent callback conflicts
        import time
        time.sleep(0.1)
        
        return f'✅ PDF-verslag voor {date_str} succesvol geüpload!'
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"PDF upload error: {error_details}")
        return f'❌ Fout bij uploaden van PDF: {e}'

@app.callback(
    Output('delete-game-btn', 'disabled'),
    Input('delete-game-dropdown', 'value')
)
def enable_delete_button(selected_game):
    return selected_game is None

@app.callback(
    [Output('delete-status', 'children'),
     Output('delete-game-dropdown', 'value'),
     Output('delete-game-dropdown', 'options', allow_duplicate=True)],
    [Input('delete-game-btn', 'n_clicks')],
    [State('delete-game-dropdown', 'value')],
    prevent_initial_call=True
)
def delete_game(n_clicks, game_nr):
    if not n_clicks or game_nr is None:
        return '', None, []
    
    try:
        # Remove all rows for this game
        df_updated = df_global[df_global['GameNr'] != game_nr].copy()
        
        # Renumber remaining games using smart numbering
        df_updated['Datum_dt'] = pd.to_datetime(df_updated['Datum'], dayfirst=True)
        df_updated = assign_smart_game_numbers(df_updated)
        
        # Save updated file
        if current_filename:
            df_updated.to_excel(current_filename, sheet_name='Globaal', index=False)
            
            # Also save to persistent data directory if not already there
            data_dir = get_persistent_data_dir()
            filename_only = os.path.basename(current_filename)
            persistent_path = os.path.join(data_dir, filename_only)
            
            if current_filename != persistent_path:
                df_updated.to_excel(persistent_path, sheet_name='Globaal', index=False)
        else:
            return 'Geen bestand geselecteerd voor opslag.', None, []
        
        # Reload data
        load_current_data()
        
        # Update dropdown options with the fresh data
        if df_global is None or df_global.empty:
            game_options = []
        else:
            games = df_global[['Datum', 'GameNr']].drop_duplicates().sort_values('GameNr')
            game_options = [
                {"label": f"Wedstrijd {row['GameNr']} - {row['Datum']}", "value": row['GameNr']}
                for _, row in games.iterrows()
            ]
        
        return f'Wedstrijd {game_nr} succesvol verwijderd en wedstrijden hernummerd.', None, game_options
        
    except Exception as e:
        return f'Fout bij verwijderen van wedstrijd: {e}', None, []

# Add a callback for the drilldown export
@app.callback(
    Output("download-drilldown-xlsx", "data"),
    Input("download-drilldown-btn", "n_clicks"),
    prevent_initial_call=True,
)
def download_drilldown(n):
    if last_drilldown_turn_data is not None:
        def writer(buf):
            last_drilldown_turn_data.to_excel(buf, index=False)
        return dcc.send_bytes(writer, "Beurten_Drilldown.xlsx")
    return no_update





# Callback to handle game PDF dropdown selection
@app.callback(
    Output("selected-game-pdf", "children"),
    Input("game-pdf-dropdown", "value"),
    prevent_initial_call=True
)
def handle_game_pdf_selection(selected_date):
    if not selected_date:
        return ""
    
    # Check if this date has a PDF report
    pdf_mapping = get_available_pdf_reports()
    
    if selected_date in pdf_mapping:
        pdf_full_path = pdf_mapping[selected_date]
        pdf_filename = os.path.basename(pdf_full_path)
        
        # Check if file exists
        if os.path.exists(pdf_full_path):
            # Determine the correct path for the iframe
            # If it's in the persistent data directory, we need to copy it to assets for web access
            if "assets" not in pdf_full_path:
                # Copy to assets if not already there
                assets_pdf_path = f"assets/Wedstrijdverslagen/{pdf_filename}"
                if not os.path.exists(assets_pdf_path):
                    import shutil
                    os.makedirs("assets/Wedstrijdverslagen", exist_ok=True)
                    shutil.copy2(pdf_full_path, assets_pdf_path)
                iframe_src = f"/assets/Wedstrijdverslagen/{pdf_filename}"
            else:
                iframe_src = f"/assets/Wedstrijdverslagen/{pdf_filename}"
            
            # Create a download link for the PDF
            return html.Div([
                html.H5(f"Wedstrijdverslag voor {selected_date}", className="mb-3"),
                html.Iframe(
                    src=iframe_src,
                    width="100%",
                    height="600px",
                    style={"border": "1px solid #ddd", "borderRadius": "5px"}
                ),
                html.Br(),
                html.Small("PDF wordt direct getoond. Gebruik Ctrl+S of rechtermuisklik → 'Opslaan als' om het bestand te downloaden.", className="text-muted")
            ])
        else:
            return html.Div([
                html.H5(f"Wedstrijd {selected_date}", className="mb-3"),
                html.P(f"PDF bestand niet gevonden: {pdf_full_path}", className="text-danger")
            ])
    else:
        return html.Div([
            html.H5(f"Wedstrijd {selected_date}", className="mb-3"),
            html.P("Geen PDF-verslag beschikbaar voor deze wedstrijd.", className="text-muted")
        ])



# Callback to update dropdown options when data changes
@app.callback(
    Output("delete-game-dropdown", "options", allow_duplicate=True),
    [Input("tabs", "value"),
     Input("season-selector", "value")],
    prevent_initial_call=True
)
def update_delete_dropdown_options(tab_value, season_value):
    # Update dropdown options for management tab
    if df_global is None or df_global.empty:
        return []
    
    games = df_global[['Datum', 'GameNr']].drop_duplicates().sort_values('GameNr')
    game_options = [
        {"label": f"Wedstrijd {row['GameNr']} - {row['Datum']}", "value": row['GameNr']}
        for _, row in games.iterrows()
    ]
    return game_options

# Authentication callbacks
@app.callback(
    [Output("login-modal", "is_open"),
     Output("login-error", "children"),
     Output("password-input", "value")],
    [Input("login-btn", "n_clicks"),
     Input("password-input", "n_submit"),
     Input("cancel-login-btn", "n_clicks"),
     Input("tabs", "value")],
    [State("password-input", "value"),
     State("login-modal", "is_open")],
    prevent_initial_call=True
)
def handle_login(login_clicks, password_submit, cancel_clicks, tab_value, password, modal_open):
    global is_authenticated
    
    ctx = dash.callback_context
    if not ctx.triggered:
        return modal_open, "", ""
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if button_id == "login-btn" or button_id == "password-input":
        if check_password(password):
            is_authenticated = True
            return False, "", ""  # Close modal, clear error, clear password
        else:
            return True, "Onjuist wachtwoord. Probeer opnieuw.", ""  # Keep modal open, show error, clear password
    
    elif button_id == "cancel-login-btn":
        return False, "", ""  # Close modal, clear error, clear password
    
    elif button_id == "tabs" and tab_value in ["tab-upload", "tab-management"]:
        if not is_authenticated:
            return True, "", ""  # Open modal if trying to access admin tabs
    
    return modal_open, "", ""

@app.callback(
    Output("login-modal", "is_open", allow_duplicate=True),
    Input("admin-login-btn", "n_clicks"),
    prevent_initial_call=True
)
def open_login_modal(admin_login_clicks):
    if admin_login_clicks:
        return True
    return no_update

@app.callback(
    Output("tabs", "children"),
    [Input("login-btn", "n_clicks"),
     Input("password-input", "n_submit")],
    [State("password-input", "value")],
    prevent_initial_call=True
)
def update_tab_access(login_clicks, password_submit, password):
    global is_authenticated
    
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if (button_id == "login-btn" or button_id == "password-input") and check_password(password):
        is_authenticated = True
        # Re-enable admin tabs
        return [
            dcc.Tab(label="Globaal Overzicht", value="tab-info", className="tab-label"),
            dcc.Tab(label="Ranking Percent", value="tab-pct", className="tab-label"),
            dcc.Tab(label="Ranking RP", value="tab-rp", className="tab-label"),
            dcc.Tab(label="Ranking Punten", value="tab-pts", className="tab-label"),
            dcc.Tab(label="Grafieken", value="tab-graphs", className="tab-label"),
            dcc.Tab(label="Upload", value="tab-upload", className="tab-label"),
            dcc.Tab(label="Beheer", value="tab-management", className="tab-label"),
        ]
    
    return no_update

@app.callback(
    Output("admin-status", "children"),
    [Input("login-btn", "n_clicks"),
     Input("password-input", "n_submit")],
    [State("password-input", "value")]
)
def update_admin_status(login_clicks, password_submit, password):
    global is_authenticated
    
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if (button_id == "login-btn" or button_id == "password-input") and check_password(password):
        is_authenticated = True
        return html.Div([
            html.I(className="fas fa-user-shield me-2"),
            html.Span("Admin ingelogd", className="text-success fw-bold"),
            html.Button("Uitloggen", id="logout-btn", className="btn btn-sm btn-outline-secondary ms-2")
        ])
    
    return no_update

@app.callback(
    [Output("admin-status", "children", allow_duplicate=True),
     Output("tabs", "children", allow_duplicate=True)],
    Input("logout-btn", "n_clicks"),
    prevent_initial_call=True
)
def handle_logout(logout_clicks):
    global is_authenticated
    
    if logout_clicks:
        is_authenticated = False
        # Disable admin tabs and update status
        return html.Div([
            html.I(className="fas fa-lock me-2"),
            html.Span("Niet ingelogd", className="text-muted"),
            html.Button("Admin Login", id="admin-login-btn", className="btn btn-sm btn-primary ms-2")
        ]), [
            dcc.Tab(label="Globaal Overzicht", value="tab-info", className="tab-label"),
            dcc.Tab(label="Ranking Percent", value="tab-pct", className="tab-label"),
            dcc.Tab(label="Ranking RP", value="tab-rp", className="tab-label"),
            dcc.Tab(label="Ranking Punten", value="tab-pts", className="tab-label"),
            dcc.Tab(label="Grafieken", value="tab-graphs", className="tab-label"),
            dcc.Tab(label="Upload Uitslag", value="tab-upload", className="tab-label", disabled=True),
            dcc.Tab(label="Wedstrijd Beheer", value="tab-management", className="tab-label", disabled=True),
        ]
    
    return no_update, no_update

# Global variables to store member data
original_member_data = None
current_member_data = None  # Store current unsaved changes

# Member Management Callbacks
@app.callback(
    Output("member-table-container", "children"),
    [Input("tabs", "value")],
    prevent_initial_call=False
)
def update_member_table(tab_value):
    if tab_value != "tab-management":
        return no_update
    
    global df_leden, original_member_data, current_member_data
    
    print(f"Tab changed to management. Member data: {len(df_leden)} members")
    
    if df_leden.empty:
        return html.P("Geen leden data beschikbaar", className="text-muted")
    
    # Store original data from JSON file
    original_member_data = df_leden.to_dict("records")
    # Initialize current data as original data
    current_member_data = original_member_data.copy()
    
    columns = [
        {"name": "Naam", "id": "Naam", "editable": True},
        {"name": "Club", "id": "CLUB", "editable": True},
        {"name": "Klasse", "id": "KLASSE", "editable": True}
    ]
    
    # Add some debugging info
    print(f"Creating member table with {len(df_leden)} members")
    print(f"Member data: {df_leden.to_dict('records')[:2]}")  # Show first 2 records
    
    return dash_table.DataTable(
        id="member-table",
        columns=columns,
        data=current_member_data,
        editable=True,
        row_deletable=True,
        style_table={"overflowX": "auto"},
        style_cell={
            "padding": "8px",
            "fontFamily": "Arial",
            "fontSize": "14px",
            "border": "1px solid #bdc3c7",
            "textAlign": "left"
        },
        style_header={
            "fontWeight": "bold",
            "backgroundColor": "#2c3e50",
            "color": "white",
            "textAlign": "center"
        },
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": "#f2f2f2"},
            {"if": {"row_index": "even"}, "backgroundColor": "#fff9c4"},
        ]
    )

@app.callback(
    Output("add-member-modal", "is_open"),
    [Input("add-member-btn", "n_clicks"),
     Input("confirm-add-member-btn", "n_clicks"),
     Input("cancel-add-member-btn", "n_clicks")],
    [State("add-member-modal", "is_open")],
    prevent_initial_call=True
)
def toggle_add_member_modal(add_clicks, confirm_clicks, cancel_clicks, is_open):
    ctx = dash.callback_context
    if not ctx.triggered:
        return is_open
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if button_id == "add-member-btn":
        return True
    elif button_id in ["confirm-add-member-btn", "cancel-add-member-btn"]:
        return False
    
    return is_open

@app.callback(
    [Output("member-management-status", "children"),
     Output("add-member-modal", "is_open", allow_duplicate=True),
     Output("new-member-name", "value"),
     Output("new-member-club", "value"),
     Output("new-member-class", "value")],
    [Input("confirm-add-member-btn", "n_clicks")],
    [State("new-member-name", "value"),
     State("new-member-club", "value"),
     State("new-member-class", "value")],
    prevent_initial_call=True
)
def add_new_member(confirm_clicks, name, club, klasse):
    if not confirm_clicks or not name:
        return no_update, no_update, "", "", "B"
    
    if not club:
        return "❌ Vul een club in!", True, name, club, klasse
    
    global current_member_data
    
    # Check if member already exists
    if current_member_data:
        existing_names = [member['Naam'] for member in current_member_data]
        if name in existing_names:
            return "❌ Lid bestaat al!", True, name, club, klasse
    
    # Add new member to current data
    new_member = {
        'Naam': name,
        'CLUB': club,
        'KLASSE': klasse
    }
    
    if current_member_data is None:
        current_member_data = []
    
    current_member_data.append(new_member)
    
    # Don't auto-save, let user save manually
    return f"✅ {name} toegevoegd - klik 'Wijzigingen opslaan' om op te slaan", False, "", "", "B"

@app.callback(
    Output("member-management-status", "children", allow_duplicate=True),
    [Input("member-table", "data_timestamp")],
    [State("member-table", "data")],
    prevent_initial_call=True
)
def track_member_changes(timestamp, data):
    """Track changes but don't auto-save"""
    if not data:
        return no_update
    
    global current_member_data, original_member_data
    
    print(f"Member table data changed. New data: {len(data)} rows")
    print(f"Current data: {len(current_member_data) if current_member_data else 0} rows")
    
    # Validate class values
    new_df = pd.DataFrame(data)
    invalid_classes = new_df[~new_df['KLASSE'].isin(['A', 'B', 'C'])]['KLASSE'].unique()
    if len(invalid_classes) > 0:
        return f"❌ Ongeldige klasse waarden: {', '.join(invalid_classes)}. Gebruik alleen A, B of C."
    
    # Check if this is the initial load (data matches original)
    if original_member_data and len(data) == len(original_member_data):
        # Compare the data to see if there are actual changes
        data_sorted = sorted(data, key=lambda x: x['Naam'])
        original_sorted = sorted(original_member_data, key=lambda x: x['Naam'])
        
        if data_sorted == original_sorted:
            # No actual changes, just initial load
            current_member_data = data
            print("Initial load detected, no changes")
            return no_update
    
    # Update current data but don't save to global df_leden yet
    current_member_data = data
    print("Data has changed, updating current data...")
    return "📝 Wijzigingen gemaakt - klik 'Wijzigingen opslaan' om op te slaan"

# Callback to handle save changes button
@app.callback(
    Output("member-management-status", "children", allow_duplicate=True),
    [Input("save-changes-btn", "n_clicks")],
    prevent_initial_call=True
)
def save_changes(n_clicks):
    """Save changes to JSON file"""
    global df_leden, current_member_data
    
    if not n_clicks or not current_member_data:
        return no_update
    
    print("Saving changes to JSON file...")
    
    # Update global df_leden with current changes
    df_leden = pd.DataFrame(current_member_data)
    
    # Save to JSON
    if save_member_data(df_leden):
        return "✅ Wijzigingen opgeslagen!"
    else:
        return "❌ Fout bij opslaan van wijzigingen!"





@app.callback(
    Output("download-members-xlsx", "data"),
    Input("export-members-btn", "n_clicks"),
    prevent_initial_call=True
)
def export_members(export_clicks):
    if not export_clicks:
        return no_update
    
    def writer(buf):
        df_leden.to_excel(buf, index=False)
    return dcc.send_bytes(writer, "Leden.xlsx")

# Additional callback to handle row deletions specifically
@app.callback(
    Output("member-management-status", "children", allow_duplicate=True),
    [Input("member-table", "data_previous")],
    [State("member-table", "data")],
    prevent_initial_call=True
)
def handle_member_deletions(previous_data, current_data):
    if not previous_data or not current_data:
        return no_update
    
    global current_member_data
    
    # Check if a row was deleted
    if len(previous_data) > len(current_data):
        print(f"Row deletion detected: {len(previous_data)} -> {len(current_data)} rows")
        
        # Update current data but don't save yet
        current_member_data = current_data
        
        return "🗑️ Lid verwijderd - klik 'Wijzigingen opslaan' om permanent op te slaan"
    
    return no_update

# Print functionality is now handled by JavaScript in the HTML template

if __name__ == "__main__":
    print("Starting Dash app...")
    # Use environment variable for port (Render requirement)
    port = int(os.environ.get("PORT", 8050))
    debug = os.environ.get("DEBUG", "False").lower() == "true"  # Default to False for production
    
    print(f"Starting server on port {port}")
    app.run(debug=debug, host="0.0.0.0", port=port)