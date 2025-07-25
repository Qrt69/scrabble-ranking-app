# Persistent Storage Fix for Render.com Deployment

## Problem Description
When the application was deployed on Render.com, uploaded games (CSV files) would disappear after the application went to sleep and woke up again. This happened because:

1. **Non-persistent storage**: Files were being saved to the current working directory (`/opt/render/project/src`), which is not persistent across application restarts.
2. **Application sleep**: Render.com puts applications to sleep when they're not actively being used, and when they wake up, they start fresh without access to previously saved files.

## Solution Implemented

### 1. Persistent Data Directory Function
Added `get_persistent_data_dir()` function that:
- On Render.com: Uses `/opt/render/project/src/data` (persistent directory)
- Locally: Uses `./data` (local development)
- Automatically creates the directory if it doesn't exist

### 2. Modified File Operations

#### CSV Upload (`process_upload`)
- **Before**: Saved files to current working directory
- **After**: Saves files to persistent data directory using `get_season_filename()`

#### PDF Upload (`process_pdf_upload`)
- **Before**: Saved PDFs only to `assets/Wedstrijdverslagen` and `Wedstrijdverslagen`
- **After**: Also saves to persistent data directory (`data/Wedstrijdverslagen`)

#### File Loading (`get_available_seasons`)
- **Before**: Only looked in current directory for season files
- **After**: Looks in both current directory and persistent data directory

#### PDF Loading (`get_available_pdf_reports`)
- **Before**: Only looked in `Wedstrijdverslagen` directory
- **After**: Looks in both current and persistent PDF directories

### 3. File Path Handling

#### Season Filename Generation (`get_season_filename`)
- **Before**: Returned relative filenames
- **After**: Returns full paths in persistent data directory

#### Current Season Detection (`get_current_season_filename`)
- **Before**: Only checked current directory
- **After**: Checks current directory first, then persistent directory, defaults to persistent for new uploads

### 4. PDF Display (`handle_game_pdf_selection`)
- **Before**: Expected files in `assets/Wedstrijdverslagen`
- **After**: Handles full paths, copies files to assets if needed for web display

## Files Modified

1. **`dash_app.py`**:
   - Added `get_persistent_data_dir()` function
   - Modified `get_season_filename()` to use persistent directory
   - Modified `get_available_seasons()` to check both directories
   - Modified `get_current_season_filename()` to prioritize existing files
   - Modified `process_upload()` to save to persistent location
   - Modified `process_pdf_upload()` to save to persistent location
   - Modified `get_available_pdf_reports()` to check both directories
   - Modified `handle_game_pdf_selection()` to handle full paths
   - Modified `delete_game()` to save to persistent location

## Testing

Created and ran `test_persistent_storage.py` to verify:
- ✅ Persistent data directory creation
- ✅ Season filename generation
- ✅ Available seasons detection
- ✅ File creation in persistent directory

## Benefits

1. **Data Persistence**: Uploaded games and PDFs now persist across application restarts
2. **Backward Compatibility**: Existing files in current directory are still accessible
3. **Automatic Migration**: New uploads go to persistent location automatically
4. **Environment Awareness**: Works correctly both locally and on Render.com

## Deployment Notes

- The persistent data directory (`/opt/render/project/src/data`) is automatically created on first use
- Existing files in the current directory will continue to work
- New uploads will be saved to the persistent location
- No manual migration of existing data is required

## Verification

To verify the fix is working:
1. Upload a new game result
2. Check that the file appears in the tables
3. Wait for the application to go to sleep (or restart it manually)
4. Verify the uploaded game is still visible after the application wakes up 