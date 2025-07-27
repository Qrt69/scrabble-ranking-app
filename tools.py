import pandas as pd
import numpy as np
from numpy.ma.extras import row_stack
from setuptools.command.bdist_egg import walk_egg

# General settings
pd.options.display.float_format = '{:.2f}'.format


def calculate_summer_percentage(df_received):
    """
    Calculate percentage for summer competition using best 5 games rule.
    For players with 5 games or fewer: use all games
    For players with 6+ games: use average of best 5 percentage scores
    """
    # Filter out players without valid class (A, B, or C)
    valid_classes = ['A', 'B', 'C']
    df_filtered = df_received[df_received['KLASSE'].isin(valid_classes)].copy()
    
    summer_percentages = []
    
    for _, player_data in df_filtered.groupby('Naam'):
        games_played = len(player_data)
        
        # Calculate normal percentage (all games)
        total_score = player_data['Totaal'].sum()
        total_max = player_data['TheoMax'].sum()
        normal_percentage = (total_score / total_max) * 100 if total_max > 0 else 0
        
        # Calculate summer rule percentage
        if games_played <= 5:
            # Use all games (same as normal)
            summer_percentage = normal_percentage
        else:
            # Use best 5 games
            game_percentages = (player_data['Totaal'] / player_data['TheoMax'] * 100).fillna(0)
            best_5_percentages = game_percentages.sort_values(ascending=False).head(5)
            summer_percentage = best_5_percentages.mean()
        
        summer_percentages.append({
            'Naam': player_data['Naam'].iloc[0],
            'Klasse': player_data['KLASSE'].iloc[0],
            'Wedstrijden': games_played,
            'Tot. T. MAX': player_data['TheoMax'].sum(),
            'Tot. Score': player_data['Totaal'].sum(),
            '% (Alle)': round(normal_percentage, 2),
            '% (Beste 5)': round(summer_percentage, 2),
            'Gem. RP': player_data['RP'].mean(),
            'Tot. punten': player_data['Punten'].sum(),
            'Scrabbles': player_data['Scrabbles'].sum(),
            "Solo's": player_data["Solo's"].sum(),
            'S.scr': player_data['Soloscrabbles'].sum(),
            'Nulscores': player_data['Nulscores'].sum(),
            'Tot. beurten': player_data['Beurten'].sum(),
            'Max. scores': player_data['Maxes'].sum(),
            '% max.': round((player_data['Maxes'].sum() / player_data['Beurten'].sum()) * 100, 2) if player_data['Beurten'].sum() > 0 else 0
        })
    
    return pd.DataFrame(summer_percentages)


def process_uitgebreid(dfp_uitgebreid,row_wedstrijdinfo, dfp_leden, pwedstrijd):

    df_to_return = dfp_uitgebreid.copy()

    columns_to_change = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9', 'B10', 'B11', 'B12', 'B13', 'B14', 'B15', 'B16',
                         'B17', 'B18', 'B19', 'B20', 'B21', 'B22', 'Totaal', 'Scrabbles', 'Nulscores', "Solo's", 'Soloscrabbles']
    for col in columns_to_change:
        if col in df_to_return.columns:
            df_to_return[col] = df_to_return[col].astype('Int64')
    df_to_return['TheoMax'] = max(df_to_return['Totaal'])
    df_to_return['Datum'] = pd.to_datetime(row_wedstrijdinfo['Datum'], dayfirst=True)
    df_to_return['Datum'] = df_to_return['Datum'].dt.strftime('%d/%m/%Y')
    df_to_return['Percent'] = df_to_return['Totaal'] / df_to_return['TheoMax'] * 100

    # Dynamically select columns that start with 'B' (i.e., the turn columns)

    df_to_return = df_to_return.set_index('Naam')
    turn_columns = [col for col in df_to_return.columns if col.startswith('B')]

    # Extract the maximum scores row for only the turn columns
    maximum_scores = df_to_return.loc['MAXIMUM', turn_columns]

    # Calculate the "Maxes" column by comparing only the identified turn columns
    df_to_return['Maxes'] = (df_to_return[turn_columns]
                               .apply(lambda row: (row == maximum_scores).value_counts().get(True, 0), axis=1))
    df_to_return['Maxes'] = df_to_return['Maxes'].astype('Int64')

    # We no longer need the MAXIMUM row, and will drop it to avoid errors or miscalculations further on
    df_to_return.drop('MAXIMUM', axis=0, inplace=True)

    # Calculation of Ranking Points
    mediaan = df_to_return['Percent'].median()
    pct_winnaar = df_to_return['Percent'].max()
    winnaar_vs_mediaan = pct_winnaar - mediaan
    df_to_return['RP'] = 100 - ((pct_winnaar - df_to_return['Percent']) * 22 / winnaar_vs_mediaan )

    # We add column 'KLASSE' from dfp_leden
    df_to_return = df_to_return.merge(dfp_leden[['Naam', 'KLASSE']], on='Naam', how='left')

    # We add 'Volgnummer' to the dataframe to return
    df_to_return['Volgnummer'] = pwedstrijd

    # We add 'Beurten' to the dataframe to return
    df_to_return['Beurten'] = row_wedstrijdinfo['Beurten']

    # We add 'Punten' to the dataframe to return
    df_to_return['Nr'] = df_to_return['Nr'].astype('int')
    df_to_return['Punten'] = df_to_return['Nr'].max() - df_to_return['Nr'] + 1

    # We delete column Ntsvnr, since we don't need it for further analysis.
    del df_to_return['Ntsvnr']

    return df_to_return

def give_gen_info(df_received):
    # Filter out players without valid class (A, B, or C)
    valid_classes = ['A', 'B', 'C']
    df_filtered = df_received[df_received['KLASSE'].isin(valid_classes)].copy()
    
    df_grouped_algemeen = (df_filtered
                           .groupby(['Naam', 'KLASSE'])
                           .agg(games_played = ('Totaal', 'count'),
                                total_max = ('TheoMax', 'sum'),
                                total_score = ('Totaal', 'sum'),
                                scrabbles_found = ('Scrabbles', 'sum'),
                                avg_ranking  = ('RP', 'mean'),
                                zeros = ('Nulscores', 'sum'),
                                solos = ("Solo's", 'sum'),
                                sscr = ('Soloscrabbles', 'sum'),
                                beurten = ('Beurten', 'sum'),
                                maxes = ('Maxes', 'sum'),
                                punten = ('Punten', 'sum'))
                           .assign(Percentage=lambda x: round((x['total_score'] / x['total_max']) * 100, 2))
                           .assign(maxperc=lambda x: round((x['maxes'] / x['beurten']) * 100, 2) )
                           .reset_index()
                           .rename(columns={
                                    'KLASSE' : 'Klasse',
                                    'games_played' : 'Wedstrijden',
                                    'total_max' : 'Tot. T. MAX',
                                    'total_score' : 'Tot. Score',
                                    'scrabbles_found' : 'Scrabbles',
                                    'avg_ranking' : 'Gem. RP',
                                    'zeros' : 'Nulscores',
                                    'solos' : "Solo's",
                                    'sscr' : 'S.scr',
                                    'beurten' : 'Tot. beurten',
                                    'maxes' : 'Max. scores',
                                    'maxperc' : '% max.',
                                    'punten' : 'Tot. punten',
                                    'Percentage' : '%'})
                           [['Naam', 'Klasse', 'Wedstrijden', 'Tot. T. MAX', 'Tot. Score', '%', 'Gem. RP',
                             'Tot. punten', 'Scrabbles', "Solo's", 'S.scr', 'Nulscores', 'Tot. beurten', 'Max. scores', '% max.']]
                           )

    return df_grouped_algemeen

def make_pivot(dfp, pindex, pcols, pvalues, force_int=False, fill_blank=True):
    """
    Create a pivot table with optional formatting for integers and blank filling.

    Args:
        dfp (pd.DataFrame): Input DataFrame.
        pindex (str): Column to use as the index in the pivot table.
        pcols (str): Column to use as columns in the pivot table.
        pvalues (str): Column to use as values in the pivot table.
        force_int (bool): If True, cast non-NaN values to integers and fill NaN with blanks.
        fill_blank (bool): If True, replace NaN with blanks ('') regardless of data type.

    Returns:
        pd.DataFrame: Pivot table.
    """
    # Create the pivot table
    pivot_to_return = dfp.pivot(index=pindex, columns=pcols, values=pvalues)

    # Convert column headers to datetime for sorting
    pivot_to_return.columns = pd.to_datetime(pivot_to_return.columns, dayfirst=True)

    # Sort columns in ascending order
    pivot_to_return = pivot_to_return.sort_index(axis=1)

    # Format the column names back to desired format
    pivot_to_return.columns = pivot_to_return.columns.strftime('%d/%m/%Y')

    # Replace NaN with blanks or integers as needed
    if force_int:
        # Replace NaN with blanks and cast only non-empty cells to integers
        pivot_to_return = pivot_to_return.applymap(
            lambda x: int(x) if pd.notna(x) else ''
        )
    elif fill_blank:
        # Round numeric values to 2 decimal places and format as strings before filling blanks
        pivot_to_return = pivot_to_return.round(2)
        pivot_to_return = pivot_to_return.applymap(lambda x: f"{float(x):.2f}" if pd.notnull(x) and x != '' and str(x).replace('.', '').replace('-', '').isdigit() else x)
        pivot_to_return = pivot_to_return.fillna('')  # Replace NaN with blank strings

    return pivot_to_return


def process_final_df(df_global, pivot_df, columns, sort_by):
    df_for_processing = df_global[columns]
    result = (pd.merge(df_for_processing, pivot_df, on='Naam', how='left')
              .sort_values(by=sort_by, ascending=False)
              .reset_index(drop=True)
              .assign(index=lambda dfx: dfx.index + 1)
              .set_index('index')
              .rename(columns={'index':'P'}))
    return result