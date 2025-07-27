#!/usr/bin/env python3
"""
Simple Dropbox token test
"""

import os
import dropbox

def test_token():
    """Test if the Dropbox token works"""
    
    # Get token from environment
    token = os.environ.get("DROPBOX_TOKEN", "")
    
    if not token:
        print("❌ No DROPBOX_TOKEN found in environment")
        return False
    
    print(f"✅ Found token: {token[:10]}...")
    
    try:
        # Create Dropbox client
        dbx = dropbox.Dropbox(token)
        print("✅ Dropbox client created")
        
        # Test connection
        account = dbx.users_get_current_account()
        print(f"✅ Connection successful - Account: {account.name.display_name}")
        
        # Test listing files
        result = dbx.files_list_folder("")
        print(f"✅ Can list files - Found {len(result.entries)} items in root")
        
        # Look for Scrabble App folder
        app_folder = None
        for entry in result.entries:
            if hasattr(entry, 'name') and entry.name == "Scrabble App":
                app_folder = entry
                break
        
        if app_folder:
            print("✅ Found 'Scrabble App' folder")
            
            # List files in the app folder
            app_files = dbx.files_list_folder("/Scrabble App")
            print(f"✅ Can access app folder - {len(app_files.entries)} files")
            
            for entry in app_files.entries:
                if hasattr(entry, 'size'):
                    print(f"   - {entry.name} ({entry.size} bytes)")
        else:
            print("❌ 'Scrabble App' folder not found")
            print("   Available folders:")
            for entry in result.entries:
                if not hasattr(entry, 'size'):
                    print(f"   - {entry.name}")
        
        return True
        
    except dropbox.exceptions.AuthError as e:
        print(f"❌ Authentication error: {e}")
        print("   Your token might be expired or invalid")
        return False
    except dropbox.exceptions.ApiError as e:
        print(f"❌ API error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Simple Dropbox Token Test")
    print("=" * 30)
    
    success = test_token()
    
    if success:
        print("\n🎉 Token is working correctly!")
    else:
        print("\n🚨 Token has issues - check the errors above") 