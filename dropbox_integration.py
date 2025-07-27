import dropbox
import os
import tempfile
import logging
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)

class DropboxManager:
    def __init__(self, access_token):
        """Initialize Dropbox connection with access token"""
        self.dbx = dropbox.Dropbox(access_token)
        self.app_folder = "/Scrabble App"  # Your app folder name
        
    def test_connection(self):
        """Test if Dropbox connection works"""
        try:
            print("=== DEBUG: test_connection: calling users_get_current_account() ===")
            account = self.dbx.users_get_current_account()
            print(f"=== DEBUG: test_connection: got account: {account.name.display_name} ===")
            logger.info("Dropbox connection successful")
            return True
        except Exception as e:
            print(f"=== DEBUG: test_connection exception: {e} ===")
            import traceback
            print(f"=== DEBUG: test_connection traceback: {traceback.format_exc()} ===")
            logger.error(f"Dropbox connection failed: {e}")
            return False
    
    def list_files(self):
        """List all files in the app folder"""
        try:
            result = self.dbx.files_list_folder(self.app_folder)
            files = []
            for entry in result.entries:
                # Only process files, not folders
                if hasattr(entry, 'size'):
                    files.append({
                        'name': entry.name,
                        'path': entry.path_display,
                        'size': entry.size,
                        'modified': entry.server_modified
                    })
            logger.info(f"Found {len(files)} files in Dropbox")
            return files
        except Exception as e:
            logger.error(f"Error listing Dropbox files: {e}")
            return []
    
    def download_file(self, dropbox_path, local_path):
        """Download a file from Dropbox to local path"""
        try:
            with open(local_path, 'wb') as f:
                metadata, response = self.dbx.files_download(dropbox_path)
                f.write(response.content)
            logger.info(f"Downloaded {dropbox_path} to {local_path}")
            return True
        except Exception as e:
            logger.error(f"Error downloading {dropbox_path}: {e}")
            return False
    
    def upload_file(self, local_path, dropbox_path):
        """Upload a file from local path to Dropbox"""
        try:
            with open(local_path, 'rb') as f:
                self.dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
            logger.info(f"Uploaded {local_path} to {dropbox_path}")
            return True
        except Exception as e:
            logger.error(f"Error uploading {local_path}: {e}")
            return False
    
    def file_exists(self, dropbox_path):
        """Check if a file exists in Dropbox"""
        try:
            self.dbx.files_get_metadata(dropbox_path)
            return True
        except dropbox.exceptions.ApiError as e:
            if e.error.is_not_found():
                return False
            else:
                raise e
    
    def sync_excel_files(self, required_files):
        """Sync Excel files from Dropbox to local storage"""
        synced_files = []
        
        for filename in required_files:
            dropbox_path = f"{self.app_folder}/{filename}"
            local_path = filename
            
            if self.file_exists(dropbox_path):
                if self.download_file(dropbox_path, local_path):
                    synced_files.append(filename)
                    logger.info(f"Synced {filename} from Dropbox")
            else:
                logger.warning(f"File {filename} not found in Dropbox")
        
        return synced_files
    
    def backup_excel_file(self, local_filename):
        """Backup an Excel file to Dropbox after updates"""
        dropbox_path = f"{self.app_folder}/{local_filename}"
        
        if os.path.exists(local_filename):
            if self.upload_file(local_filename, dropbox_path):
                logger.info(f"Backed up {local_filename} to Dropbox")
                return True
            else:
                logger.error(f"Failed to backup {local_filename} to Dropbox")
                return False
        else:
            logger.error(f"Local file {local_filename} not found for backup")
            return False
    
    def upload_pdf_report(self, local_pdf_path, date_str):
        """Upload a PDF report to Dropbox"""
        # Generate filename based on date
        dt_obj = datetime.strptime(date_str, '%d/%m/%Y')
        if dt_obj.month in [7, 8]:
            # Summer competition
            filename = f"zomerwedstrijd van {dt_obj.day}-{dt_obj.month}-{str(dt_obj.year)[2:]}.pdf"
        else:
            # Regular season
            filename = f"wedstrijd van {dt_obj.day}-{dt_obj.month}-{dt_obj.year}.pdf"
        
        dropbox_path = f"{self.app_folder}/{filename}"
        
        if self.upload_file(local_pdf_path, dropbox_path):
            logger.info(f"Uploaded PDF report {filename} to Dropbox")
            return True
        else:
            logger.error(f"Failed to upload PDF report {filename} to Dropbox")
            return False

# Global Dropbox manager instance
dropbox_manager = None

def initialize_dropbox(access_token):
    """Initialize the global Dropbox manager"""
    global dropbox_manager
    
    print(f"=== DEBUG: initialize_dropbox called with token length: {len(access_token)} ===")
    
    try:
        print("=== DEBUG: Creating DropboxManager instance ===")
        dropbox_manager = DropboxManager(access_token)
        print("=== DEBUG: DropboxManager created successfully ===")
        
        print("=== DEBUG: Testing connection ===")
        connection_result = dropbox_manager.test_connection()
        print(f"=== DEBUG: test_connection returned: {connection_result} ===")
        
        return connection_result
    except Exception as e:
        print(f"=== DEBUG: Exception in initialize_dropbox: {e} ===")
        import traceback
        print(f"=== DEBUG: Full traceback: {traceback.format_exc()} ===")
        return False

def get_dropbox_manager():
    """Get the global Dropbox manager instance"""
    return dropbox_manager 