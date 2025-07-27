import dash
from dash import dcc, html, dash_table, Input, Output, State, callback, ctx, no_update
import dash_bootstrap_components as dbc
import pandas as pd
import tools
import importlib
import plotly.express as px
import os
from datetime import datetime
import base64
import io
import glob
import hashlib
import PyPDF2
import re
import json
import logging
import dropbox_integration

from dash.dash_table.Format import Format, Scheme
from dash.dependencies import ALL

print("=== DEBUG: Starting app initialization ===")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("=== DEBUG: Logging configured ===")

# Dropbox configuration
print("=== DEBUG: About to read DROPBOX_TOKEN from environment ===")
DROPBOX_ACCESS_TOKEN = os.environ.get("DROPBOX_TOKEN", "")
print(f"=== DEBUG: DROPBOX_TOKEN from os.environ.get: {'Present' if DROPBOX_ACCESS_TOKEN else 'Missing'} ===")
print(f"=== DEBUG: Token length: {len(DROPBOX_ACCESS_TOKEN)} ===")

USE_DROPBOX = bool(DROPBOX_ACCESS_TOKEN)
print(f"=== DEBUG: USE_DROPBOX calculated: {USE_DROPBOX} ===")

print(f"=== DEBUG: Dropbox configuration ===")
print(f"=== DEBUG: DROPBOX_TOKEN from env: {'Present' if DROPBOX_ACCESS_TOKEN else 'Missing'} ===")
print(f"=== DEBUG: Token length: {len(DROPBOX_ACCESS_TOKEN)} ===")
print(f"=== DEBUG: USE_DROPBOX: {USE_DROPBOX} ===")

if USE_DROPBOX:
    print("=== DEBUG: Entering USE_DROPBOX=True block ===")
    logger.info("Initializing Dropbox integration...")
    print("=== DEBUG: Initializing Dropbox integration ===")
    try:
        print("=== DEBUG: Calling dropbox_integration.initialize_dropbox() ===")
        result = dropbox_integration.initialize_dropbox(DROPBOX_ACCESS_TOKEN)
        print(f"=== DEBUG: initialize_dropbox() returned: {result} ===")
        
        if result:
            logger.info("Dropbox integration successful")
            print("=== DEBUG: Dropbox integration successful ===")
        else:
            logger.error("Dropbox integration failed - falling back to local files")
            print("=== DEBUG: Dropbox integration failed ===")
            USE_DROPBOX = False
            print(f"=== DEBUG: USE_DROPBOX set to: {USE_DROPBOX} ===")
    except Exception as e:
        logger.error(f"Dropbox initialization error: {e} - falling back to local files")
        print(f"=== DEBUG: Dropbox initialization exception: {e} ===")
        import traceback
        print(f"=== DEBUG: Full traceback: {traceback.format_exc()} ===")
        USE_DROPBOX = False
        print(f"=== DEBUG: USE_DROPBOX set to: {USE_DROPBOX} ===")
else:
    print("=== DEBUG: Entering USE_DROPBOX=False block ===")
    logger.info("No Dropbox access token found - using local files only")
    print("=== DEBUG: No Dropbox token found ===")

print(f"=== DEBUG: Final USE_DROPBOX value: {USE_DROPBOX} ===")

importlib.reload(tools)

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
            logger.info(f"Synced: {filename}")
    
    logger.info(f"PDF sync complete. {len(source_files)} files processed.")

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
        logger.error(f"Error extracting date from PDF: {e}")
        import traceback
        traceback.print_exc()
        return None

# Global variable to track if PDFs have been synced
_pdfs_synced = False

def get_available_pdf_reports():
    """Scan Wedstrijdverslagen folder and return mapping of dates to PDF files"""
    global _pdfs_synced
    pdf_mapping = {}
    
    # Sync PDF files from Dropbox only once during app startup
    if USE_DROPBOX and not _pdfs_synced:
        logger.info("Syncing PDF files from Dropbox...")
        dropbox_manager = dropbox_integration.get_dropbox_manager()
        if dropbox_manager:
            # Ensure local directories exist
            for folder in ["Wedstrijdverslagen", "assets/Wedstrijdverslagen"]:
                if not os.path.exists(folder):
                    os.makedirs(folder)
                    logger.info(f"Created directory: {folder}")
            
            # List files in Dropbox
            dropbox_files = dropbox_manager.list_files()
            for file_info in dropbox_files:
                if file_info['name'].endswith('.pdf'):
                    # Download PDF to local folders
                    dropbox_path = file_info['path']
                    local_path = f"Wedstrijdverslagen/{file_info['name']}"
                    assets_path = f"assets/Wedstrijdverslagen/{file_info['name']}"
                    
                    # Download to main folder
                    if dropbox_manager.download_file(dropbox_path, local_path):
                        logger.info(f"Downloaded PDF: {file_info['name']}")
                        
                        # Also copy to assets folder for web serving
                        import shutil
                        try:
                            shutil.copy2(local_path, assets_path)
                            logger.info(f"Copied to assets: {file_info['name']}")
                        except Exception as e:
                            logger.error(f"Error copying to assets: {e}")
            
            # Also check for PDFs in subfolders (Wedstrijdverslagen folder)
            try:
                subfolder_result = dropbox_manager.dbx.files_list_folder(f"{dropbox_manager.app_folder}/Wedstrijdverslagen")
                for entry in subfolder_result.entries:
                    if hasattr(entry, 'size') and entry.name.endswith('.pdf'):
                        dropbox_path = entry.path_display
                        local_path = f"Wedstrijdverslagen/{entry.name}"
                        assets_path = f"assets/Wedstrijdverslagen/{entry.name}"
                        
                        # Download to main folder
                        if dropbox_manager.download_file(dropbox_path, local_path):
                            logger.info(f"Downloaded PDF from subfolder: {entry.name}")
                            
                            # Also copy to assets folder for web serving
                            import shutil
                            try:
                                shutil.copy2(local_path, assets_path)
                                logger.info(f"Copied to assets: {entry.name}")
                            except Exception as e:
                                logger.error(f"Error copying to assets: {e}")
            except Exception as e:
                logger.warning(f"Could not list Wedstrijdverslagen subfolder: {e}")
        
        # Mark PDFs as synced
        _pdfs_synced = True
        logger.info("PDF sync completed")
    
    # Now scan local Wedstrijdverslagen folder
    if not os.path.exists("Wedstrijdverslagen"):
        logger.warning("Wedstrijdverslagen folder not found")
        return pdf_mapping
    
    for filename in os.listdir("Wedstrijdverslagen"):
        if filename.endswith('.pdf'):
            # Parse filename like "zomerwedstrijd 1 van 3-7-25.pdf"
            try:
                # Extract date part after "van "
                if "van " in filename:
                    date_part = filename.split("van ")[1].replace('.pdf', '')
                    # Convert to DD/MM/YYYY format
                    if '-' in date_part:
                        parts = date_part.split('-')
                        if len(parts) == 3:
                            day, month, year = parts
                            # Handle different year formats
                            if len(year) == 2:
                                year = '20' + year
                            elif len(year) == 4:
                                year = year
                            else:
                                continue  # Skip if year format is unknown
                            
                            # Ensure day and month are 2 digits
                            day = day.zfill(2)
                            month = month.zfill(2)
                            
                            date_str = f"{day}/{month}/{year}"
                            pdf_mapping[date_str] = filename
            except Exception as e:
                logger.error(f"Error parsing PDF filename {filename}: {e}")
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
    
    # Look for regular season files (Globaal YYYY-YYYY.xlsx)
    globaal_files = glob.glob("Globaal *.xlsx")
    for file in globaal_files:
        # Extract year range from filename
        try:
            year_range = file.replace("Globaal ", "").replace(".xlsx", "")
            seasons.append({
                "label": f"Seizoen {year_range}",
                "value": file
            })
        except:
            continue
    
    # Look for summer files (Zomer YYYY.xlsx)
    zomer_files = glob.glob("Zomer *.xlsx")
    for file in zomer_files:
        try:
            year = file.replace("Zomer ", "").replace(".xlsx", "")
            seasons.append({
                "label": f"Zomer {year}",
                "value": file
            })
        except:
            continue
    
    # Sort by filename for consistent ordering
    seasons.sort(key=lambda x: x["value"])
    return seasons

def get_current_season_filename():
    """Determine the current season filename based on today's date"""
    today = datetime.now()
    year = today.year
    month = today.month
    
    if month in [7, 8]:
        # Summer competition
        return f'Zomer {year}.xlsx'
    else:
        # Regular season: September (9) to June (6)
        if month >= 9:
            start_year = year
            end_year = year + 1
        else:
            start_year = year - 1
            end_year = year
        return f'Globaal {start_year}-{end_year}.xlsx'

def load_data_for_season(filename):
    """Load data from a specific season file"""
    global df_global, df_gen_info, df_pct_final, df_rp_final, df_pts_final
    
    print(f"=== DEBUG: Inside load_data_for_season({filename}) ===")
    
    if not os.path.exists(filename):
        print(f"=== DEBUG: Season file not found: {filename} ===")
        # No data available
        df_global = pd.DataFrame()
        df_gen_info = pd.DataFrame()
        df_pct_final = pd.DataFrame()
        df_rp_final = pd.DataFrame()
        df_pts_final = pd.DataFrame()
        return
    
    try:
        print(f"=== DEBUG: Loading data from {filename} ===")
        # Try both "Globaal" and "globaal" (case sensitive)
        try:
            df_global = pd.read_excel(filename, sheet_name="Globaal")
            print(f"=== DEBUG: Successfully read {filename} with {len(df_global)} rows ===")
        except Exception as e:
            print(f"=== DEBUG: Error reading with 'Globaal': {e} ===")
            df_global = pd.read_excel(filename, sheet_name="globaal")
            print(f"=== DEBUG: Successfully read {filename} with 'globaal' sheet: {len(df_global)} rows ===")
        
        print(f"=== DEBUG: Columns in df_global: {list(df_global.columns)} ===")
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
        
        logger.info(f"Successfully loaded data: {len(df_global)} rows")
        
    except Exception as e:
        logger.error(f"Error loading data from {filename}: {e}")
        import traceback
        traceback.print_exc()
        # Initialize empty dataframes
        df_global = pd.DataFrame()
        df_gen_info = pd.DataFrame()
        df_pct_final = pd.DataFrame()
        df_rp_final = pd.DataFrame()
        df_pts_final = pd.DataFrame()

def load_current_data():
    """Load data from the current season file"""
    global df_global, df_gen_info, df_pct_final, df_rp_final, df_pts_final, current_filename, available_seasons
    
    print("=== DEBUG: Inside load_current_data() ===")
    print(f"=== DEBUG: USE_DROPBOX = {USE_DROPBOX} ===")
    print(f"=== DEBUG: DROPBOX_ACCESS_TOKEN present = {bool(DROPBOX_ACCESS_TOKEN)} ===")
    
    # For online app, we MUST have Dropbox for persistent storage
    if not USE_DROPBOX:
        logger.error("No Dropbox integration available - app cannot function without persistent storage")
        print("=== DEBUG: Dropbox integration disabled - app cannot function ===")
        # Initialize with empty data and show error message
        df_global = pd.DataFrame()
        df_gen_info = pd.DataFrame()
        df_pct_final = pd.DataFrame()
        df_rp_final = pd.DataFrame()
        df_pts_final = pd.DataFrame()
        return
    
    # Sync with Dropbox - this is required for online app
    logger.info("Syncing Excel files from Dropbox...")
    print("=== DEBUG: Starting Dropbox sync ===")
    try:
        required_files = ["Globaal 2024-2025.xlsx", "Zomer 2025.xlsx", "Info.xlsx"]
        print(f"=== DEBUG: Required files: {required_files} ===")
        
        dropbox_manager = dropbox_integration.get_dropbox_manager()
        print(f"=== DEBUG: Dropbox manager available: {dropbox_manager is not None} ===")
        
        if dropbox_manager:
            synced_files = dropbox_manager.sync_excel_files(required_files)
            logger.info(f"Synced {len(synced_files)} files from Dropbox: {synced_files}")
            print(f"=== DEBUG: Synced files: {synced_files} ===")
            
            if not synced_files:
                logger.error("No files synced from Dropbox - app cannot function")
                print("=== DEBUG: No files synced from Dropbox - app cannot function ===")
                # Initialize with empty data
                df_global = pd.DataFrame()
                df_gen_info = pd.DataFrame()
                df_pct_final = pd.DataFrame()
                df_rp_final = pd.DataFrame()
                df_pts_final = pd.DataFrame()
                return
        else:
            logger.error("Dropbox manager not available - app cannot function")
            print("=== DEBUG: Dropbox manager is None - app cannot function ===")
            # Initialize with empty data
            df_global = pd.DataFrame()
            df_gen_info = pd.DataFrame()
            df_pct_final = pd.DataFrame()
            df_rp_final = pd.DataFrame()
            df_pts_final = pd.DataFrame()
            return
    except Exception as e:
        logger.error(f"Dropbox sync error: {e} - app cannot function without data")
        print(f"=== DEBUG: Dropbox sync exception: {e} - app cannot function ===")
        # Initialize with empty data
        df_global = pd.DataFrame()
        df_gen_info = pd.DataFrame()
        df_pct_final = pd.DataFrame()
        df_rp_final = pd.DataFrame()
        df_pts_final = pd.DataFrame()
        return
    
    # Get available seasons
    available_seasons = get_available_seasons()
    print(f"=== DEBUG: Available seasons: {[s['value'] for s in available_seasons]} ===")
    
    current_filename = get_current_season_filename()
    print(f"=== DEBUG: Current filename determined: {current_filename} ===")
    
    # Check if current season file exists
    if os.path.exists(current_filename):
        filename = current_filename
        print(f"=== DEBUG: Using current season file: {filename} ===")
    elif available_seasons:
        filename = available_seasons[0]["value"]
        current_filename = filename
        print(f"=== DEBUG: Using first available season: {filename} ===")
    else:
        print("=== DEBUG: No data files found - initializing with empty data ===")
        # No data available
        df_global = pd.DataFrame()
        df_gen_info = pd.DataFrame()
        df_pct_final = pd.DataFrame()
        df_rp_final = pd.DataFrame()
        df_pts_final = pd.DataFrame()
        return
    
    print(f"=== DEBUG: About to load data from: {filename} ===")
    load_data_for_season(filename)

# Debug: Check what files exist
print("=== DEBUG: Checking files ===")
print(f"Current directory: {os.getcwd()}")
files = os.listdir('.')
excel_files = [f for f in files if f.endswith('.xlsx')]
print(f"Excel files found: {excel_files}")

for file in excel_files:
    if os.path.exists(file):
        print(f"  {file} exists ({os.path.getsize(file)} bytes)")
        try:
            xl = pd.ExcelFile(file)
            print(f"    Sheets: {xl.sheet_names}")
        except Exception as e:
            print(f"    Error reading: {e}")

# Load initial data
print("=== DEBUG: About to call load_current_data() ===")
try:
    load_current_data()
    print("=== DEBUG: load_current_data() completed successfully ===")
except Exception as e:
    print(f"=== DEBUG: Error in load_current_data(): {e} ===")
    import traceback
    print(f"=== DEBUG: Traceback: {traceback.format_exc()} ===")

# Member management functions
def load_member_data():
    """Load member data from JSON file or create from Excel if not exists"""
    json_file = "members.json"
    
    # For online app, we need Dropbox to have any data
    if not USE_DROPBOX:
        logger.error("No Dropbox integration - cannot load member data")
        return pd.DataFrame()
    
    if os.path.exists(json_file):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"Loaded {len(data)} members from JSON")
            return pd.DataFrame(data)
        except Exception as e:
            logger.error(f"Error loading members.json: {e}")
    
    # If JSON doesn't exist, create from Excel file (which should be synced from Dropbox)
    if os.path.exists("Info.xlsx"):
        try:
            df_leden = pd.read_excel("Info.xlsx", sheet_name="Leden")
            df_leden.rename(columns={'NAAM': 'Naam'}, inplace=True)
            
            # Save to JSON for future use
            save_member_data(df_leden)
            logger.info(f"Created members.json from Excel with {len(df_leden)} members")
            return df_leden
        except Exception as e:
            logger.error(f"Error loading from Info.xlsx: {e}")
    
    # No data available
    logger.warning("No member data available")
    return pd.DataFrame()

def save_member_data(df):
    """Save member data to JSON file"""
    try:
        with open("members.json", 'w', encoding='utf-8') as f:
            json.dump(df.to_dict('records'), f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(df)} members to JSON")
        return True
    except Exception as e:
        logger.error(f"Error saving members.json: {e}")
        return False

# Load member data
df_leden = load_member_data()
logger.info(f"Loaded {len(df_leden)} members from data source")
if not df_leden.empty:
    logger.info(f"Sample members: {df_leden.head(3).to_dict('records')}")
else:
    logger.info("No member data found - creating sample data for testing")
    # Create some sample data for testing
    sample_members = [
        {'Naam': 'Jan Janssens', 'CLUB': 'COXHYDE, Koksijde', 'KLASSE': 'A'},
        {'Naam': 'Piet Pieters', 'CLUB': 'COXHYDE, Koksijde', 'KLASSE': 'B'},
        {'Naam': 'Marie Maes', 'CLUB': 'COXHYDE, Koksijde', 'KLASSE': 'A'}
    ]
    df_leden = pd.DataFrame(sample_members)
    save_member_data(df_leden)
    logger.info(f"Created sample data with {len(df_leden)} members")

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
        return f'Zomer {year}.xlsx'
    else:
        # Regular season: September (9) to June (6)
        if month >= 9:
            start_year = year
            end_year = year + 1
        else:
            start_year = year - 1
            end_year = year
        return f'Globaal {start_year}-{end_year}.xlsx'

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
        
        return html.Div([
            html.Div([
                html.Button("Download Excel", id="download-info-btn", className="btn btn-success me-2"),
                html.Button("Print", id="print-info-btn", className="btn btn-primary", 
                          **{"data-print": "true"}),
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
    
    try:
        # Convert date from ISO to DD/MM/YYYY
        dt = datetime.strptime(date[:10], '%Y-%m-%d')
        date_str = dt.strftime('%d/%m/%Y')
        logger.info(f"Processing upload for date: {date_str}")
        
        # Read uploaded CSV
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        try:
            try:
                df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), sep=';')
            except Exception:
                df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), sep=',')
        except Exception as e:
            logger.error(f"CSV read error: {e}")
            return f'Fout bij het lezen van het CSV-bestand: {e}'
        
        # Read supporting Excel file for leden
        global df_leden  # Move global declaration to the top
        try:
            if os.path.exists('Info.xlsx'):
                df_leden = pd.read_excel('Info.xlsx', sheet_name='Leden')
                df_leden.rename(columns={'NAAM': 'Naam'}, inplace=True)
            else:
                # Use global member data if Info.xlsx doesn't exist
                logger.warning("Info.xlsx not found, using global member data")
                # df_leden is already global, so we can use it directly
        except Exception as e:
            logger.error(f"Error reading member data: {e}")
            return f'Fout bij het lezen van leden data: {e}'
        
        # Always determine the season filename based on the uploaded date
        season_filename = get_season_filename(date_str)
        logger.info(f"Season filename: {season_filename}")
        
        # Check for duplicates and assign volgnummer
        if os.path.exists(season_filename):
            try:
                df_season = pd.read_excel(season_filename, sheet_name='Globaal')
                logger.info(f"Loaded existing season file with {len(df_season)} rows")
            except Exception as e:
                logger.error(f"Error reading season file: {e}")
                return f'Fout bij het lezen van {season_filename}: {e}'
            # Check if this date already exists
            if (df_season['Datum'] == date_str).any():
                return f'Deze uitslag voor {date_str} werd al ingelezen in {season_filename}.'
            # Assign volgnummer as one more than the number of unique dates (sorted chronologically)
            unique_dates = sorted(pd.to_datetime(df_season['Datum'], dayfirst=True).unique())
            volgnummer = len(unique_dates) + 1
        else:
            df_season = None
            volgnummer = 1
            logger.info(f"Creating new season file: {season_filename}")
        
        # Prepare row_wedstrijdinfo
        row_wedstrijdinfo = {'Datum': date_str, 'Beurten': len([col for col in df.columns if col.startswith('B') and col[1:].isdigit()])}
        
        # Process the data
        try:
            df_processed = tools.process_uitgebreid(df, row_wedstrijdinfo, df_leden, volgnummer)
            logger.info(f"Processed data with {len(df_processed)} rows")
        except Exception as e:
            logger.error(f"Data processing error: {e}")
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
            df_new.to_excel(season_filename, sheet_name='Globaal', index=False)
            logger.info(f"Successfully saved {len(df_new)} rows to {season_filename}")
            
            # Backup to Dropbox - required for online app
            if USE_DROPBOX:
                try:
                    dropbox_manager = dropbox_integration.get_dropbox_manager()
                    if dropbox_manager:
                        if dropbox_manager.backup_excel_file(season_filename):
                            logger.info(f"Successfully backed up {season_filename} to Dropbox")
                        else:
                            logger.error(f"Failed to backup {season_filename} to Dropbox - data may be lost on restart")
                    else:
                        logger.error("Dropbox manager not available for backup - data may be lost on restart")
                except Exception as e:
                    logger.error(f"Dropbox backup error: {e} - data may be lost on restart")
            else:
                logger.error("No Dropbox integration - data will be lost on restart")
            
        except Exception as e:
            logger.error(f"Error saving file: {e}")
            return f'Fout bij het opslaan van {season_filename}: {e}'
        
        # Reload data
        load_current_data()
        
        # Get the actual game number that was assigned
        actual_game_nr = df_new[df_new['Datum'] == date_str]['GameNr'].iloc[0]
        
        return f'Uitslag voor {date_str} (wedstrijd {actual_game_nr}) succesvol toegevoegd aan {season_filename}!'
        
    except Exception as e:
        logger.error(f"Unexpected error in upload processing: {e}")
        import traceback
        traceback.print_exc()
        return f'Onverwachte fout bij upload: {e}'

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
    logger.info(f"PDF upload callback triggered - n_clicks: {n_clicks}, filename: {filename}")
    
    # Prevent processing if no clicks or contents
    if not n_clicks:
        logger.info("No clicks, returning empty")
        return ''
    
    if not contents:
        logger.info("No contents, returning empty")
        return ''
    
    # Prevent multiple processing
    if n_clicks == 0:
        logger.info("Zero clicks, returning empty")
        return ''
    
    try:
        # Try to extract date from PDF content first
        logger.info("Extracting date from PDF content...")
        date_str = extract_date_from_pdf_content(contents)
        logger.info(f"Extracted date: {date_str}")
        
        # If automatic extraction failed, we need to handle this differently
        # For now, we'll require automatic extraction to work
        if not date_str:
            logger.error("Date extraction failed")
            return 'Fout: Kon datum niet automatisch detecteren uit het PDF-bestand. Zorg ervoor dat het PDF-bestand de juiste datum bevat.'
        
        # Check if PDF already exists for this date
        pdf_mapping = get_available_pdf_reports()
        if date_str in pdf_mapping:
            return f'⚠️ Er bestaat al een PDF-verslag voor {date_str}. Upload geannuleerd.'
        
        # Generate filename based on date (matching existing pattern)
        dt_obj = datetime.strptime(date_str, '%d/%m/%Y')
        if dt_obj.month in [7, 8]:
            # Summer competition - use DD-M-YY format like existing files
            filename_new = f"zomerwedstrijd van {dt_obj.day}-{dt_obj.month}-{str(dt_obj.year)[2:]}.pdf"
        else:
            # Regular season - use DD-M-YYYY format like existing files
            filename_new = f"wedstrijd van {dt_obj.day}-{dt_obj.month}-{dt_obj.year}.pdf"
        
        # Save PDF to assets folder
        try:
            # Decode base64 content
            content_type, content_string = contents.split(',')
            decoded = base64.b64decode(content_string)
            
            # Ensure assets directory exists
            assets_dir = "assets/Wedstrijdverslagen"
            if not os.path.exists(assets_dir):
                os.makedirs(assets_dir)
                logger.info(f"Created assets directory: {assets_dir}")
            
            # Save file
            pdf_path = os.path.join(assets_dir, filename_new)
            logger.info(f"Saving to assets: {pdf_path}")
            with open(pdf_path, 'wb') as f:
                f.write(decoded)
            
            # Also save to main Wedstrijdverslagen folder for consistency
            main_dir = "Wedstrijdverslagen"
            if not os.path.exists(main_dir):
                os.makedirs(main_dir)
                logger.info(f"Created main directory: {main_dir}")
            
            main_pdf_path = os.path.join(main_dir, filename_new)
            logger.info(f"Saving to main: {main_pdf_path}")
            with open(main_pdf_path, 'wb') as f:
                f.write(decoded)
            
            # Also save to assets folder for immediate web serving
            assets_dir = "assets/Wedstrijdverslagen"
            if not os.path.exists(assets_dir):
                os.makedirs(assets_dir)
                logger.info(f"Created assets directory: {assets_dir}")
            
            assets_pdf_path = os.path.join(assets_dir, filename_new)
            logger.info(f"Saving to assets: {assets_pdf_path}")
            with open(assets_pdf_path, 'wb') as f:
                f.write(decoded)
            
            # Upload to Dropbox - required for online app
            if USE_DROPBOX:
                try:
                    dropbox_manager = dropbox_integration.get_dropbox_manager()
                    if dropbox_manager:
                        if dropbox_manager.upload_pdf_report(main_pdf_path, date_str):
                            logger.info(f"Successfully uploaded PDF to Dropbox")
                        else:
                            logger.error(f"Failed to upload PDF to Dropbox - file may be lost on restart")
                    else:
                        logger.error("Dropbox manager not available for PDF upload - file may be lost on restart")
                except Exception as e:
                    logger.error(f"Dropbox PDF upload error: {e} - file may be lost on restart")
            else:
                logger.error("No Dropbox integration - PDF will be lost on restart")
            
            # Verify files were saved correctly
            if not os.path.exists(pdf_path):
                logger.error(f"PDF not found in assets after save: {pdf_path}")
                return f'❌ Fout: PDF kon niet worden opgeslagen in assets folder'
            if not os.path.exists(main_pdf_path):
                logger.error(f"PDF not found in main after save: {main_pdf_path}")
                return f'❌ Fout: PDF kon niet worden opgeslagen in hoofdmap'
            
            # Note: PDF mapping will be refreshed on next app load
            logger.info("PDF files saved successfully")
            
            logger.info(f"PDF upload successful: {date_str} -> {filename_new}")
            
            # Add a small delay to prevent callback conflicts
            import time
            time.sleep(0.1)
            
            return f'✅ PDF-verslag voor {date_str} succesvol geüpload!'
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"PDF upload error: {error_details}")
            return f'❌ Fout bij uploaden van PDF: {e}'
            
    except Exception as e:
        logger.error(f"Unexpected error in PDF upload: {e}")
        import traceback
        traceback.print_exc()
        return f'Onverwachte fout bij PDF upload: {e}'

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
        pdf_filename = pdf_mapping[selected_date]
        pdf_path = f"Wedstrijdverslagen/{pdf_filename}"
        
        if os.path.exists(pdf_path):
            # Create a download link for the PDF
            return html.Div([
                html.H5(f"Wedstrijdverslag voor {selected_date}", className="mb-3"),
                html.Iframe(
                    src=f"/assets/Wedstrijdverslagen/{pdf_filename}",
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
                html.P(f"PDF bestand niet gevonden: {pdf_path}", className="text-danger")
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