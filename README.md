# Scrabble Koksijde - Ranking System

A modern web application for managing and displaying Scrabble club rankings, statistics, and member information.

## 🎯 What It Does

- **Track game results** and calculate rankings
- **Manage club members** with classes (A, B, C)
- **Summer competition rules** (best 5 of 9 games)
- **Upload new results** via CSV files
- **View match reports** via PDF integration
- **Export data** to Excel files
- **Print rankings** for club meetings

## 🚀 Quick Start

### Local Development
```bash
pip install -r requirements.txt
python dash_app.py
```
Then open: http://127.0.0.1:8050

### Production Deployment
See [DEPLOYMENT.md](DEPLOYMENT.md) for Render.com deployment instructions.

## 📊 Features

- **Multi-season support** (regular + summer competitions)
- **Smart game numbering** (preserves order when games are deleted)
- **Admin authentication** (password-protected uploads)
- **Member management** (add/edit/remove members)
- **Performance graphs** and detailed analytics
- **PDF report viewing** with automatic date extraction
- **Excel exports** for all tables
- **Print functionality** for paper copies

## 📁 Files

- `dash_app.py` - Main application
- `tools.py` - Data processing functions
- `members.json` - Member database
- `requirements.txt` - Python dependencies
- `render.yaml` - Deployment configuration

## 🎮 Usage

1. **View Rankings** - Check current standings
2. **Upload Results** - Add new game data (admin only)
3. **Manage Members** - Update member information (admin only)
4. **Export Data** - Download Excel files
5. **Print Rankings** - Generate paper copies

## 🛠️ Built With

- **Dash** - Web framework
- **Pandas** - Data processing
- **Plotly** - Interactive charts
- **Bootstrap** - UI styling

---

**For Scrabble Club Koksijde**  
**Version 3.0** - Production Ready 🚀 
