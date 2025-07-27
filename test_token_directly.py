#!/usr/bin/env python3
"""
Direct Dropbox token test
"""

import os
import dropbox

def test_token_directly():
    """Test the Dropbox token directly"""
    
    print("=== DIRECT TOKEN TEST ===")
    
    # Get token from environment
    token = os.environ.get("DROPBOX_TOKEN", "")
    
    print(f"1. Token from environment:")
    print(f"   Present: {'Yes' if token else 'No'}")
    print(f"   Length: {len(token)}")
    print(f"   Starts with: {token[:10] if token else 'N/A'}...")
    print(f"   Is empty string: {token == ''}")
    print(f"   Is whitespace only: {token.strip() == '' if token else 'N/A'}")
    
    if not token:
        print("❌ No token found")
        return False
    
    if token.strip() == '':
        print("❌ Token is empty or whitespace only")
        return False
    
    # Test token format
    if not token.startswith('sl.'):
        print("❌ Token doesn't start with 'sl.' - invalid format")
        return False
    
    print("✅ Token format looks correct")
    
    # Test direct Dropbox connection
    try:
        print("\n2. Testing direct Dropbox connection...")
        dbx = dropbox.Dropbox(token)
        print("✅ Dropbox client created")
        
        # Test connection
        account = dbx.users_get_current_account()
        print(f"✅ Connection successful - Account: {account.name.display_name}")
        print(f"   Email: {account.email}")
        
        # Test listing files
        result = dbx.files_list_folder("")
        print(f"✅ Can list files - Found {len(result.entries)} items")
        
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
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    print("🔍 Direct Dropbox Token Test")
    print("=" * 40)
    
    success = test_token_directly()
    
    if success:
        print("\n🎉 Token is working correctly!")
        print("   The issue might be in the app initialization code.")
    else:
        print("\n🚨 Token has issues - check the errors above")
        print("   You may need to regenerate your Dropbox access token.") 